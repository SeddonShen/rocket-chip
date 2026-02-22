#!/usr/bin/env python3
"""
BMC depth test script for standalone rocket-chip modules.

Tests how deep BMC must unroll to cover each cover point,
identifying modules where BMC hits a depth bottleneck.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable

# ── Module configuration ─────────────────────────────────────────────
# Maps module key → (sv_filename, top_module_name)
# Derived from generator/chisel3/src/main/scala/ModuleGenTop.scala
MODULE_CONFIG: Dict[str, Tuple[str, str]] = {
    "broadcast":   ("StandaloneBroadcast.sv",  "StandaloneBroadcast"),
    "xbar":        ("StandaloneXbar.sv",       "StandaloneXbar"),
    "plic":        ("StandalonePLIC.sv",       "StandalonePLIC"),
    "sram_ecc":    ("StandaloneSRAMECC.sv",    "StandaloneSRAMECC"),
    "toaxi4":      ("StandaloneToAXI4.sv",     "StandaloneToAXI4"),
    "fragmenter":  ("StandaloneFragmenter.sv", "StandaloneFragmenter"),
    "atomic":      ("StandaloneAtomic.sv",     "StandaloneAtomic"),
    "timer":       ("Timer.sv",                "Timer"),
    "idpool":      ("IDPool.sv",               "IDPool"),
    "jtag_fsm":    ("JtagStateMachine.sv",     "JtagStateMachine"),
    "arbiter":     ("HellaCountingArbiter.sv", "HellaCountingArbiter"),
    "reorder_q":   ("ReorderQueue.sv",         "ReorderQueue"),
    "ecc":         ("ECCModule.sv",            "ECCModule"),
    "async_queue": ("AsyncQueue.sv",           "AsyncQueue"),
    "replacement": ("ReplacementModule.sv",    "ReplacementModule"),
}

# MemRWHelper.v allocates 2 GB RAM under SYNTHESIS — formal tools cannot handle it
EXCLUDED_MODULES = {"axi4xbar"}

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


# ── RTL processing ───────────────────────────────────────────────────

def process_rtl(
    module_key: str,
    build_dir: Path,
    work_dir: Path,
    cover_type: str = "toggle",
    mode: str = "smt",
) -> List[int]:
    """
    Read, instrument, and write RTL for formal verification.

    1. Copy auxiliary .v files (GEN_w*_*.v, plusarg_reader.v) and write define.sv
    2. Unify clocks: ``posedge <anything>`` → ``posedge glb_clk``
    3. Parse ``GEN_w<N>_{cover_type}`` instances, extract reset / valid signals
    4. Insert ``cover`` (SMT) or negated ``assert`` (SAT) for each cover-point bit
    5. Insert ``initial assume(!reg)`` for uninitialized single and array regs

    Args:
        module_key: Key in MODULE_CONFIG (e.g. "timer").
        build_dir:  Path to ``build/modules/<module_key>/``.
        work_dir:   Path to ``bmctest/work/<module_key>/``.
        cover_type: Coverage instrumentation type (default "toggle").
        mode:       "smt" inserts ``cover()``; "sat" inserts ``assert(~...)``.

    Returns:
        Sorted list of cover-point indices.
    """
    sv_filename, _ = MODULE_CONFIG[module_key]
    sv_path = build_dir / sv_filename
    rtl_out = work_dir / "rtl"
    rtl_out.mkdir(parents=True, exist_ok=True)

    # ── 0. Copy black-box .v files & create define.sv ────────────────
    for vf in build_dir.glob("GEN_w*_*.v"):
        shutil.copy2(vf, rtl_out)
    plusarg = build_dir / "plusarg_reader.v"
    if plusarg.exists():
        shutil.copy2(plusarg, rtl_out)

    (rtl_out / "define.sv").write_text(
        "`define SYNTHESIS\n`define sfuzz_rand_reg rand reg\n"
    )

    # ── 1. Read source SV ────────────────────────────────────────────
    with open(sv_path) as f:
        lines = f.readlines()

    # ── 2. Clock unification ─────────────────────────────────────────
    clk_re = re.compile(r"\(posedge (\w+)\)")
    lines = [clk_re.sub("(posedge glb_clk)", ln) for ln in lines]

    # ── 3-4. Parse GEN instances & insert cover / assert ─────────────
    cover_indices: List[int] = []

    esc = re.escape(cover_type)
    inst_begin_re = re.compile(rf"GEN_w(\d+)_{esc}.*{esc}_(\d+)")
    inst_end_re = re.compile(r"\);")
    reset_re = re.compile(r"\.reset\(([^)]*)\)")
    valid_re = re.compile(r"\.valid\(([^)]*)\)")

    new_lines: List[str] = []
    in_inst = False
    width = 0
    base_idx = 0
    rst = "reset"
    val = ""

    for ln in lines:
        new_lines.append(ln)

        m = inst_begin_re.search(ln)
        if m:
            in_inst = True
            width = int(m.group(1))
            base_idx = int(m.group(2))

        if in_inst:
            mr = reset_re.search(ln)
            if mr:
                rst = mr.group(1)
            mv = valid_re.search(ln)
            if mv:
                val = mv.group(1)

            if inst_end_re.search(ln):
                in_inst = False
                new_lines.append("  always @(posedge glb_clk) begin\n")
                new_lines.append(f"    if (!{rst}) begin\n")
                if width > 1:
                    for bit in range(width):
                        idx = base_idx + bit
                        cover_indices.append(idx)
                        lbl = f"cov_count_{idx}"
                        if mode == "smt":
                            new_lines.append(
                                f"      {lbl}: cover({val}[{bit}]);\n"
                            )
                        else:
                            new_lines.append(
                                f"      {lbl}: assert(~{val}[{bit}]);\n"
                            )
                else:
                    cover_indices.append(base_idx)
                    lbl = f"cov_count_{base_idx}"
                    if mode == "smt":
                        new_lines.append(f"      {lbl}: cover({val});\n")
                    else:
                        new_lines.append(f"      {lbl}: assert(~{val});\n")
                new_lines.append("    end\n")
                new_lines.append("  end\n")

    # ── 5. Initial assume for uninitialized regs ─────────────────────
    single_re = re.compile(
        r"^\s*reg\s*(\[\d+:\d+\])?\s+(\w+)(\s*=\s*[^;]+)?;"
    )
    array_re = re.compile(
        r"^\s*reg\s*(\[\d+:\d+\])?\s+(\w+)\s*\[(\d+):(\d+)\];"
    )

    final: List[str] = []
    for ln in new_lines:
        final.append(ln)

        # Array regs: initial assume each element (skip arrays > 16 entries)
        am = array_re.search(ln)
        if am:
            name = am.group(2)
            hi, lo = int(am.group(3)), int(am.group(4))
            if abs(hi - lo) + 1 > 16:
                continue
            for i in range(max(hi, lo), min(hi, lo) - 1, -1):
                final.append(f"  initial assume(!{name}[{i}]);\n")
            continue

        # Single regs: skip RAND helpers and regs with explicit initializers
        sm = single_re.search(ln)
        if sm:
            name = sm.group(2)
            if "RAND" in name:
                continue
            if sm.group(3) is not None:
                continue
            final.append(f"  initial assume(!{name});\n")

    # ── Write instrumented SV ────────────────────────────────────────
    with open(rtl_out / sv_filename, "w") as f:
        f.writelines(final)

    cover_indices.sort()
    print(
        f"[{module_key}] {len(cover_indices)} cover points extracted, "
        f"RTL written to {rtl_out}"
    )
    return cover_indices


# ── SBY generation ───────────────────────────────────────────────────

def generate_sby_files(
    module_key: str,
    cover_indices: List[int],
    work_dir: Path,
    mode: str = "smt",
    depth: int = 50,
    timeout: int = 3600,
) -> Path:
    """
    Generate one .sby file per cover point, isolating each via chformal.

    Args:
        module_key:    Key in MODULE_CONFIG.
        cover_indices: Sorted cover-point indices from process_rtl().
        work_dir:      ``bmctest/work/<module>/``.
        mode:          "smt" → cover mode + smtbmc; "sat" → bmc mode + aiger rIC3.
        depth:         BMC unrolling depth.
        timeout:       Per-task wall-clock timeout in seconds.

    Returns:
        Path to the tasks directory containing the generated .sby files.
    """
    _, top_module = MODULE_CONFIG[module_key]
    rtl_dir = work_dir / "rtl"
    tasks_dir = work_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    sv_files = sorted(f for f in rtl_dir.glob("*.sv") if f.name != "define.sv")
    v_files = sorted(rtl_dir.glob("*.v"))
    rtl_files = sv_files + v_files

    formal_reads = "\n".join(f"read -formal {f.name}" for f in rtl_files)
    file_paths = "\n".join(str(f) for f in rtl_files)

    if mode == "smt":
        sby_mode = "cover"
        engine = "smtbmc bitwuzla"
    else:
        sby_mode = "bmc"
        engine = "aiger rIC3"

    for idx in cover_indices:
        label = f"cov_count_{idx}"

        if mode == "smt":
            chformal = (
                f"chformal -remove -cover c:{label} %n\n"
                f"chformal -remove -assert"
            )
        else:
            chformal = (
                f"chformal -remove -assert c:{label} %n\n"
                f"chformal -remove -cover"
            )

        sby_content = (
            f"[options]\n"
            f"mode {sby_mode}\n"
            f"depth {depth}\n"
            f"timeout {timeout}\n"
            f"\n"
            f"[engines]\n"
            f"{engine}\n"
            f"\n"
            f"[script]\n"
            f"read -formal define.sv\n"
            f"{formal_reads}\n"
            f"prep -top {top_module}\n"
            f"{chformal}\n"
            f"\n"
            f"[files]\n"
            f"{file_paths}\n"
            f"\n"
            f"[file define.sv]\n"
            f"`define SYNTHESIS\n"
            f"`define sfuzz_rand_reg rand reg\n"
        )

        (tasks_dir / f"cover_{idx}.sby").write_text(sby_content)

    print(
        f"[{module_key}] {len(cover_indices)} .sby files written to {tasks_dir}"
    )
    return tasks_dir


# ── Parallel execution ───────────────────────────────────────────────

def _find_env_path() -> str:
    """Locate the OSS CAD Suite ``environment`` script."""
    env = os.environ.get("OSS_CAD_SUITE_HOME", "")
    if env and Path(env).exists():
        return env
    for candidate in [
        PROJECT_ROOT.parent / "oss-cad-suite" / "environment",
        Path("/mnt/sda/oss-cad-suite/environment"),
    ]:
        if candidate.exists():
            return str(candidate)
    return ""


def _find_sby_cmd() -> str:
    """Return the sby command — prefer the project-local custom build."""
    custom = PROJECT_ROOT / "ccover" / "sby" / "sbysrc" / "sby.py"
    if custom.exists():
        return str(custom)
    if shutil.which("sby"):
        return "sby"
    return "sby"


def run_bmc(
    module_key: str,
    work_dir: Path,
    cover_indices: List[int],
    mode: str = "smt",
    workers: int = 64,
    ric3_path: Optional[str] = None,
) -> List[dict]:
    """
    Execute sby tasks in parallel and parse results.

    Returns:
        List of dicts, each with keys:
        ``cover_id``, ``status``, ``depth``, ``elapsed_secs``.
    """
    tasks_dir = work_dir / "tasks"
    env_path = _find_env_path()
    sby_cmd = _find_sby_cmd()

    if not env_path:
        print(
            "WARNING: OSS_CAD_SUITE_HOME not found — "
            "sby tasks may fail if tools are not in PATH",
            file=sys.stderr,
        )

    def _run_single(idx: int) -> dict:
        sby_file = tasks_dir / f"cover_{idx}.sby"
        cmd = ""
        if env_path:
            cmd += f"source {env_path} && "
        cmd += f"{sby_cmd} -f {sby_file}"
        if mode == "sat" and ric3_path:
            cmd += f" --rIC3 {ric3_path}"

        t0 = time.time()
        try:
            proc = subprocess.run(
                ["bash", "-c", cmd],
                capture_output=True, text=True,
            )
            rc = proc.returncode
        except Exception as e:
            return {
                "cover_id": idx,
                "status": "ERROR",
                "depth": 0,
                "elapsed_secs": round(time.time() - t0, 2),
            }

        elapsed = round(time.time() - t0, 2)

        # ── Parse sby logfile ────────────────────────────────────
        log_path = tasks_dir / f"cover_{idx}" / "logfile.txt"
        depth = 0
        status = "ERROR"

        if log_path.exists():
            log_text = log_path.read_text()

            if mode == "smt":
                steps = re.findall(
                    r"Checking cover reachability in step (\d+)\.\.", log_text,
                )
            else:
                steps = re.findall(r"bmc depth: (\d+)", log_text)
            if steps:
                depth = int(steps[-1])

            done = re.search(r"DONE \((\S+),\s*rc=(\d+)\)", log_text)
            if done:
                result_str = done.group(1)
                if result_str == "TIMEOUT":
                    status = "TIMEOUT"
                elif result_str == "ERROR":
                    status = "ERROR"
                elif mode == "smt":
                    status = "PASS" if result_str == "PASS" else "FAIL"
                else:
                    status = "PASS" if result_str == "FAIL" else "FAIL"
            elif "TIMEOUT" in log_text:
                status = "TIMEOUT"

        return {
            "cover_id": idx,
            "status": status,
            "depth": depth,
            "elapsed_secs": elapsed,
        }

    max_workers = min(workers, os.cpu_count() or 1)
    print(
        f"[{module_key}] Running {len(cover_indices)} tasks "
        f"with {max_workers} workers..."
    )

    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_single, idx): idx for idx in cover_indices
        }
        with tqdm(total=len(futures), desc=f"BMC {module_key}") as pbar:
            for future in as_completed(futures):
                results.append(future.result())
                pbar.update(1)

    results.sort(key=lambda r: r["cover_id"])
    return results


# ── Result analysis ──────────────────────────────────────────────────

def analyze_results(
    module_key: str,
    results: List[dict],
    work_dir: Path,
) -> dict:
    """
    Aggregate per-cover-point results into summary statistics.

    Each element in *results* is a dict with keys:
        cover_id  (int)   – cover point index
        status    (str)   – "PASS" | "FAIL" | "TIMEOUT" | "ERROR"
        depth     (int)   – BMC depth reached (covering depth for PASS)
        elapsed_secs (float) – wall-clock seconds

    Writes ``work_dir/results.json`` and prints a terminal summary.
    Returns the summary dict.
    """
    total = len(results)
    if total == 0:
        print(f"[{module_key}] No results to analyse.")
        return {"module": module_key, "total_cover_points": 0}

    covered = [r for r in results if r["status"] == "PASS"]
    uncovered = [r for r in results if r["status"] == "FAIL"]
    timed_out = [r for r in results if r["status"] == "TIMEOUT"]
    errors = [r for r in results if r["status"] == "ERROR"]

    covered_depths = sorted(r["depth"] for r in covered)

    # ── Depth distribution (buckets of 10) ───────────────────────────
    depth_dist: Dict[str, int] = {}
    if covered_depths:
        max_bucket = (covered_depths[-1] // 10 + 1) * 10
        for lo in range(0, max_bucket, 10):
            hi = lo + 9
            count = sum(1 for d in covered_depths if lo <= d <= hi)
            if count > 0:
                depth_dist[f"{lo}-{hi}"] = count

    # ── Descriptive statistics ───────────────────────────────────────
    avg_depth = sum(covered_depths) / len(covered_depths) if covered_depths else 0.0
    max_depth = covered_depths[-1] if covered_depths else 0
    if covered_depths:
        mid = len(covered_depths) // 2
        if len(covered_depths) % 2 == 0:
            median_depth = (covered_depths[mid - 1] + covered_depths[mid]) / 2
        else:
            median_depth = float(covered_depths[mid])
    else:
        median_depth = 0.0

    # ── BMC bottleneck: (uncovered + timeout) / total > 30% ─────────
    uncoverable_count = len(uncovered) + len(timed_out)
    uncoverable_rate = uncoverable_count / total
    is_bottleneck = uncoverable_rate > 0.3

    total_elapsed = sum(r.get("elapsed_secs", 0) for r in results)

    summary = {
        "module": module_key,
        "total_cover_points": total,
        "covered": len(covered),
        "uncovered": len(uncovered),
        "timeout": len(timed_out),
        "error": len(errors),
        "cover_rate": round(len(covered) / total, 4),
        "uncoverable_rate": round(uncoverable_rate, 4),
        "avg_depth": round(avg_depth, 2),
        "max_depth": max_depth,
        "median_depth": median_depth,
        "depth_distribution": depth_dist,
        "is_bottleneck": is_bottleneck,
        "total_elapsed_secs": round(total_elapsed, 2),
        "details": results,
    }

    # ── Write JSON report ────────────────────────────────────────────
    report_path = work_dir / "results.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)

    # ── Terminal summary ─────────────────────────────────────────────
    W = 60
    print(f"\n{'=' * W}")
    print(f"  Module: {module_key}")
    print(f"{'=' * W}")
    print(f"  Total cover points : {total}")
    print(f"  Covered   (PASS)   : {len(covered)}")
    print(f"  Uncovered (FAIL)   : {len(uncovered)}")
    print(f"  Timeout            : {len(timed_out)}")
    print(f"  Error              : {len(errors)}")
    print(f"  Cover rate         : {summary['cover_rate'] * 100:.1f}%")
    print(f"  Uncoverable rate   : {summary['uncoverable_rate'] * 100:.1f}%")
    if covered_depths:
        print(f"  Avg  depth         : {avg_depth:.1f}")
        print(f"  Max  depth         : {max_depth}")
        print(f"  Med. depth         : {median_depth}")
        print(f"  Depth distribution :")
        for bucket in sorted(depth_dist, key=lambda b: int(b.split("-")[0])):
            cnt = depth_dist[bucket]
            bar = "#" * min(cnt, 50)
            print(f"    {bucket:>8s} | {cnt:>4d}  {bar}")
    print(f"  Total elapsed      : {total_elapsed:.1f}s")
    if is_bottleneck:
        print(
            f"  *** BMC BOTTLENECK: "
            f"{uncoverable_rate * 100:.1f}% uncoverable (>30%) ***"
        )
    print(f"{'=' * W}")
    print(f"  Report: {report_path}")

    return summary


def _print_cross_module_summary(
    summaries: List[dict],
    reports_dir: Path,
) -> None:
    """Print and persist a cross-module comparison table."""
    reports_dir.mkdir(parents=True, exist_ok=True)

    ranked = sorted(
        summaries, key=lambda s: s["uncoverable_rate"], reverse=True
    )
    bottlenecks = [s["module"] for s in ranked if s["is_bottleneck"]]

    W = 70
    hdr = (
        f"  {'Module':<15s} {'Total':>6s} {'Cover':>6s} {'Fail':>6s} "
        f"{'TmOut':>6s} {'Rate':>7s} {'AvgD':>6s} {'MaxD':>6s} {'BN?'}"
    )
    sep = f"  {'-' * 15} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 7} {'-' * 6} {'-' * 6} {'-' * 4}"

    lines: List[str] = []
    lines.append(f"\n{'=' * W}")
    lines.append("  Cross-Module Summary")
    lines.append(f"{'=' * W}")
    lines.append(hdr)
    lines.append(sep)
    for s in ranked:
        tag = "YES" if s["is_bottleneck"] else ""
        lines.append(
            f"  {s['module']:<15s} {s['total_cover_points']:>6d} "
            f"{s['covered']:>6d} {s['uncovered']:>6d} {s['timeout']:>6d} "
            f"{s['cover_rate'] * 100:>6.1f}% {s['avg_depth']:>6.1f} "
            f"{s['max_depth']:>6d} {tag}"
        )
    lines.append(f"\n  Bottleneck modules (>30% uncoverable): "
                 f"{', '.join(bottlenecks) if bottlenecks else 'none'}")
    lines.append(f"{'=' * W}")

    for ln in lines:
        print(ln)

    # ── Save summary.json (without per-cover details) ────────────────
    stripped = [
        {k: v for k, v in s.items() if k != "details"} for s in ranked
    ]
    with open(reports_dir / "summary.json", "w") as f:
        json.dump(stripped, f, indent=2)

    # ── Save summary.txt ─────────────────────────────────────────────
    with open(reports_dir / "summary.txt", "w") as f:
        f.write("BMC Depth Test — Cross-Module Summary\n")
        f.write(f"{'=' * W}\n")
        for s in ranked:
            tag = " [BOTTLENECK]" if s["is_bottleneck"] else ""
            f.write(
                f"{s['module']}: {s['covered']}/{s['total_cover_points']} covered, "
                f"avg depth {s['avg_depth']:.1f}, max depth {s['max_depth']}{tag}\n"
            )
        f.write(
            f"\nBottleneck modules: "
            f"{', '.join(bottlenecks) if bottlenecks else 'none'}\n"
        )

    print(f"  Reports saved to: {reports_dir}")


# ── CLI ──────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="BMC depth test for standalone rocket-chip modules",
    )
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--module", choices=sorted(MODULE_CONFIG.keys()),
        help="Test a single module",
    )
    grp.add_argument(
        "--all", action="store_true",
        help="Test all 15 modules (excluding axi4xbar)",
    )

    p.add_argument("--depth", type=int, default=50,
                   help="BMC unrolling depth (default: 50)")
    p.add_argument("--timeout", type=int, default=3600,
                   help="Per-task timeout in seconds (default: 3600)")
    p.add_argument("--mode", choices=["smt", "sat"], default="smt",
                   help="Verification mode (default: smt)")
    p.add_argument("--workers", type=int, default=64,
                   help="Max parallel workers (default: 64)")
    p.add_argument("--ric3", default=None,
                   help="Path to rIC3 binary (required for SAT mode)")
    p.add_argument("--build-dir", type=Path,
                   default=PROJECT_ROOT / "build" / "modules",
                   help="Module SV root directory (default: build/modules)")
    p.add_argument("--work-dir", type=Path,
                   default=SCRIPT_DIR / "work",
                   help="Working directory (default: bmctest/work)")
    p.add_argument("--cover-type", default="toggle",
                   help="Coverage type to instrument (default: toggle)")
    return p


def main():
    args = build_arg_parser().parse_args()

    if args.mode == "sat" and not args.ric3:
        print("ERROR: --ric3 is required for SAT mode", file=sys.stderr)
        sys.exit(1)

    modules = (
        sorted(k for k in MODULE_CONFIG if k not in EXCLUDED_MODULES)
        if args.all
        else [args.module]
    )

    all_summaries: List[dict] = []

    for mod in modules:
        print(f"\n{'#' * 60}")
        print(f"# Module: {mod}")
        print(f"{'#' * 60}")

        build_path = args.build_dir / mod
        work_path = args.work_dir / mod

        if not build_path.exists():
            print(f"  SKIP: build directory not found — {build_path}")
            continue

        if work_path.exists():
            shutil.rmtree(work_path)
        work_path.mkdir(parents=True, exist_ok=True)

        # Step 1 — instrument RTL
        cover_indices = process_rtl(
            mod, build_path, work_path, args.cover_type, args.mode,
        )
        if not cover_indices:
            print(f"  WARNING: no cover points for {mod}, skipping")
            continue

        print(
            f"  Cover points: {len(cover_indices)}  "
            f"[{cover_indices[0]} .. {cover_indices[-1]}]"
        )

        # Step 2 — generate sby tasks
        generate_sby_files(
            mod, cover_indices, work_path,
            mode=args.mode,
            depth=args.depth,
            timeout=args.timeout,
        )

        # Step 3 — parallel BMC execution
        results = run_bmc(
            mod, work_path, cover_indices,
            mode=args.mode,
            workers=min(args.workers, os.cpu_count() or 1),
            ric3_path=args.ric3,
        )

        # Step 4 — analyse & report
        summary = analyze_results(mod, results, work_path)
        all_summaries.append(summary)

    # Cross-module comparison (when testing multiple modules)
    if len(all_summaries) > 1:
        reports_dir = SCRIPT_DIR / "reports"
        _print_cross_module_summary(all_summaries, reports_dir)
    elif len(all_summaries) == 1:
        print("\nDone. Single-module results written above.")
    else:
        print("\nNo modules were processed.")


if __name__ == "__main__":
    main()
