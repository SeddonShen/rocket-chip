/*
 * module_emu.cpp — Shared C++ emulator driver for standalone module fuzzing.
 *
 * Provides:
 *   - fuzz_get_byte() DPI-C: feeds fuzzer input bytes to the SV wrapper
 *   - Two entry modes: FUZZER_LIB (linked with libfuzzer.a) or standalone
 *   - Verilator simulation loop with reset, clock toggle, io_success check
 *   - FIRRTL coverage integration (firrtl-cover.h/cpp)
 *   - Optional VCD trace (VM_TRACE)
 */

#include "verilated.h"

#if VM_TRACE
#include <memory>
#include "verilated_vcd_c.h"
#endif

#ifdef FIRRTL_COVER
#include "firrtl-cover.h"
#endif

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <getopt.h>
#include <signal.h>

#include "VSimTop.h"

// ── Fuzz input buffer ────────────────────────────────────────────────
static const uint8_t *fuzz_buf = nullptr;
static size_t fuzz_buf_len = 0;
static size_t fuzz_buf_pos = 0;

extern "C" unsigned char fuzz_get_byte() {
    if (fuzz_buf && fuzz_buf_pos < fuzz_buf_len) {
        return fuzz_buf[fuzz_buf_pos++];
    }
    return 0;
}

// ── Simulation state ─────────────────────────────────────────────────
static uint64_t trace_count = 0;
static volatile bool sig_exit = false;

double sc_time_stamp() { return trace_count; }

extern "C" int vpi_get_vlog_info(void *arg) { return 0; }

static void handle_sigterm(int) { sig_exit = true; }

// ── Coverage helpers ─────────────────────────────────────────────────
#ifdef FIRRTL_COVER
static const int n_cover_types =
    sizeof(firrtl_cover) / sizeof(FIRRTLCoverPointParam);

static uint32_t get_cover_total() {
    uint32_t total = 0;
    for (int i = 0; i < n_cover_types; i++) {
        total += firrtl_cover[i].cover.total;
    }
    return total;
}

static uint32_t get_cover_hit() {
    uint32_t hit = 0;
    for (int i = 0; i < n_cover_types; i++) {
        for (uint64_t j = 0; j < firrtl_cover[i].cover.total; j++) {
            if (firrtl_cover[i].cover.points[j]) hit++;
        }
    }
    return hit;
}

static void reset_cover() {
    for (int i = 0; i < n_cover_types; i++) {
        memset(firrtl_cover[i].cover.points, 0, firrtl_cover[i].cover.total);
    }
}

static void display_cover() {
    for (int i = 0; i < n_cover_types; i++) {
        uint32_t total = firrtl_cover[i].cover.total;
        uint32_t hit = 0;
        for (uint64_t j = 0; j < total; j++) {
            if (firrtl_cover[i].cover.points[j]) hit++;
        }
        fprintf(stderr, "COVERAGE: %s, %u / %u (%.1f%%)\n",
                firrtl_cover[i].cover.name, hit, total,
                total ? 100.0 * hit / total : 0.0);
    }
}
#endif // FIRRTL_COVER

// ── Accumulative coverage for fuzzer feedback ────────────────────────
#ifdef FIRRTL_COVER
static uint8_t **acc_cover = nullptr;

static void init_acc_cover() {
    acc_cover = new uint8_t *[n_cover_types];
    for (int i = 0; i < n_cover_types; i++) {
        acc_cover[i] = new uint8_t[firrtl_cover[i].cover.total]();
    }
}

static void accumulate_cover() {
    for (int i = 0; i < n_cover_types; i++) {
        for (uint64_t j = 0; j < firrtl_cover[i].cover.total; j++) {
            if (firrtl_cover[i].cover.points[j]) {
                acc_cover[i][j] = 1;
            }
        }
    }
}

static uint32_t get_acc_cover_hit() {
    uint32_t hit = 0;
    for (int i = 0; i < n_cover_types; i++) {
        for (uint64_t j = 0; j < firrtl_cover[i].cover.total; j++) {
            if (acc_cover[i][j]) hit++;
        }
    }
    return hit;
}

static void free_acc_cover() {
    if (acc_cover) {
        for (int i = 0; i < n_cover_types; i++) delete[] acc_cover[i];
        delete[] acc_cover;
        acc_cover = nullptr;
    }
}
#endif // FIRRTL_COVER

// ── Exported interface for fuzzer library ────────────────────────────
#ifdef FUZZER_LIB
extern "C" uint32_t get_cover_number() {
#ifdef FIRRTL_COVER
    return get_cover_total();
#else
    return 0;
#endif
}

extern "C" void update_stats(uint8_t *bytes) {
#ifdef FIRRTL_COVER
    for (int i = 0; i < n_cover_types; i++) {
        memcpy(bytes, firrtl_cover[i].cover.points, firrtl_cover[i].cover.total);
        bytes += firrtl_cover[i].cover.total;
    }
#endif
}
#endif // FUZZER_LIB

// ── Simulation core ──────────────────────────────────────────────────

static int run_sim(const uint8_t *input, size_t input_len,
                   uint64_t max_cycles, const char *vcd_path) {
    fuzz_buf = input;
    fuzz_buf_len = input_len;
    fuzz_buf_pos = 0;
    trace_count = 0;

    Verilated::randReset(2);

    VSimTop *top = new VSimTop;

#if VM_TRACE
    Verilated::traceEverOn(true);
    VerilatedVcdC *tfp = nullptr;
    if (vcd_path) {
        tfp = new VerilatedVcdC;
        top->trace(tfp, 99);
        tfp->open(vcd_path);
    }
#endif

#ifdef FIRRTL_COVER
    reset_cover();
#endif

    int ret = 0;
    bool done_reset = false;

    const int reset_cycles = 10;

    while (trace_count < max_cycles && !sig_exit) {
        if (done_reset && top->io_success)
            break;

        top->clock = 0;
        top->reset = (trace_count < (uint64_t)reset_cycles) ? 1 : 0;
        done_reset = !top->reset;
        top->eval();

#if VM_TRACE
        if (tfp) tfp->dump(static_cast<vluint64_t>(trace_count * 2));
#endif

        top->clock = 1;
        top->eval();

#if VM_TRACE
        if (tfp) tfp->dump(static_cast<vluint64_t>(trace_count * 2 + 1));
#endif

        trace_count++;
    }

    if (trace_count >= max_cycles) {
        ret = 2;
    }

#if VM_TRACE
    if (tfp) {
        tfp->close();
        delete tfp;
    }
#endif

    delete top;
    return ret;
}

// ── Entry points ─────────────────────────────────────────────────────

#ifdef FUZZER_LIB

extern "C" int sim_main(int argc, const char **argv) {
    uint64_t max_cycles = 10000;

    for (int i = 1; i < argc; i++) {
        if (strncmp(argv[i], "--max-cycles=", 13) == 0) {
            max_cycles = strtoull(argv[i] + 13, nullptr, 10);
        } else if (strcmp(argv[i], "-m") == 0 && i + 1 < argc) {
            max_cycles = strtoull(argv[++i], nullptr, 10);
        }
    }

    const uint8_t *input = nullptr;
    size_t input_len = 0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-i") == 0 && i + 1 < argc) {
            FILE *fp = fopen(argv[++i], "rb");
            if (fp) {
                fseek(fp, 0, SEEK_END);
                input_len = ftell(fp);
                fseek(fp, 0, SEEK_SET);
                uint8_t *buf = new uint8_t[input_len];
                if (fread(buf, 1, input_len, fp) == input_len)
                    input = buf;
                fclose(fp);
            }
        }
    }

#ifdef FIRRTL_COVER
    init_acc_cover();
    reset_cover();
#endif

    int ret = run_sim(input, input_len, max_cycles, nullptr);

#ifdef FIRRTL_COVER
    accumulate_cover();
    display_cover();
    free_acc_cover();
#endif

    delete[] input;
    return ret;
}

#else // standalone mode

static void usage(const char *prog) {
    fprintf(stderr,
        "Usage: %s [options]\n"
        "  -i FILE        Input binary file for fuzz bytes\n"
        "  -m CYCLES      Max simulation cycles (default: 100000)\n"
        "  -v FILE        VCD output file\n"
        "  -s SEED        Random seed\n"
        "  -h             Show this help\n",
        prog);
}

int main(int argc, char **argv) {
    uint64_t max_cycles = 100000;
    unsigned seed = 0;
    const char *input_path = nullptr;
    const char *vcd_path = nullptr;
    bool has_seed = false;

    int opt;
    while ((opt = getopt(argc, argv, "i:m:v:s:h")) != -1) {
        switch (opt) {
        case 'i': input_path = optarg; break;
        case 'm': max_cycles = strtoull(optarg, nullptr, 10); break;
        case 'v': vcd_path = optarg; break;
        case 's': seed = atoi(optarg); has_seed = true; break;
        case 'h':
        default:  usage(argv[0]); return (opt == 'h') ? 0 : 1;
        }
    }

    if (has_seed) {
        srand(seed);
        srand48(seed);
    }

    Verilated::commandArgs(argc, argv);

    uint8_t *input = nullptr;
    size_t input_len = 0;
    if (input_path) {
        FILE *fp = fopen(input_path, "rb");
        if (!fp) {
            fprintf(stderr, "ERROR: cannot open %s\n", input_path);
            return 1;
        }
        fseek(fp, 0, SEEK_END);
        input_len = ftell(fp);
        fseek(fp, 0, SEEK_SET);
        input = new uint8_t[input_len];
        if (fread(input, 1, input_len, fp) != input_len) {
            fprintf(stderr, "ERROR: failed to read %s\n", input_path);
            fclose(fp);
            delete[] input;
            return 1;
        }
        fclose(fp);
    }

    signal(SIGTERM, handle_sigterm);

#ifdef FIRRTL_COVER
    init_acc_cover();
#endif

    int ret = run_sim(input, input_len, max_cycles, vcd_path);

#ifdef FIRRTL_COVER
    accumulate_cover();
    display_cover();
    uint32_t total = get_cover_total();
    uint32_t hit = get_acc_cover_hit();
    fprintf(stderr, "COVERAGE TOTAL: %u / %u (%.1f%%)\n",
            hit, total, total ? 100.0 * hit / total : 0.0);
    free_acc_cover();
#endif

    if (ret == 2) {
        fprintf(stderr, "*** TIMEOUT *** after %lu cycles\n", trace_count);
    } else if (ret == 0) {
        fprintf(stderr, "*** PASSED *** after %lu cycles\n", trace_count);
    }

    delete[] input;
    return ret;
}

#endif // FUZZER_LIB
