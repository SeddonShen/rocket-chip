CHISEL_VERSION = 6.5.0

FUZZ_TOP  = freechips.rocketchip.system.FuzzMain
BUILD_DIR = $(abspath ./build)

RTL_DIR    = $(BUILD_DIR)/rtl
RTL_SUFFIX = sv
TOP_V      = $(RTL_DIR)/SimTop.$(RTL_SUFFIX)

MILL_ARGS = --target-dir $(RTL_DIR) \
            --full-stacktrace

ifeq ($(BMCFUZZ),1)
CHISEL_VERSION = 3.6.1
endif

ifeq ($(CHISEL_VERSION),3.6.1)
RTL_SUFFIX = sv
TOP_V      = $(RTL_DIR)/SimTop.$(RTL_SUFFIX)
else
MILL_ARGS += --split-verilog
endif

# sverilog support
ifeq ($(RTL_SUFFIX),sv)
MILL_ARGS += -X sverilog
endif

# Coverage support
ifneq ($(FIRRTL_COVER),)
MILL_ARGS += COVER=$(FIRRTL_COVER)
endif

BOOTROM_DIR = $(abspath ./bootrom)
BOOTROM_SRC = $(BOOTROM_DIR)/bootrom.S
BOOTROM_IMG = $(BOOTROM_DIR)/bootrom.img

$(BOOTROM_IMG): $(BOOTROM_SRC)
	@make -C $(BOOTROM_DIR) all CROSS=riscv64-linux-gnu-

bootrom: $(BOOTROM_IMG)

SCALA_FILE = $(shell find ./src/main/scala -name '*.scala')
$(TOP_V): $(SCALA_FILE) $(BOOTROM_IMG)
	mill -i generator[$(CHISEL_VERSION)].runMain $(FUZZ_TOP) $(MILL_ARGS)
	@cp src/main/resources/vsrc/EICG_wrapper.v $(RTL_DIR)
	@sed -i 's/UNOPTFLAT/LATCH/g' $(RTL_DIR)/EICG_wrapper.v
	@for file in $(RTL_DIR)/*.$(RTL_SUFFIX); do                                  \
		sed -i -e 's/$$fatal/xs_assert_v2(`__FILE__, `__LINE__)/g' "$$file"; \
		sed -i -e "s/\$$error(/\$$fwrite(32\'h80000002, /g" "$$file";        \
	done


sim-verilog: $(TOP_V)

emu: sim-verilog
	@$(MAKE) -C difftest emu WITH_CHISELDB=0 WITH_CONSTANTIN=0 RTL_SUFFIX=$(RTL_SUFFIX) CPU=ROCKET_CHIP

src: sim-verilog

fuzzer: 
	@$(MAKE) -C difftest emu WITH_CHISELDB=0 WITH_CONSTANTIN=0 RTL_SUFFIX=$(RTL_SUFFIX) CPU=ROCKET_CHIP

ccover:
	@$(MAKE) -C ./ccover build

clean:
	rm -rf $(BUILD_DIR)

idea:
	mill -i mill.idea.GenIdea/idea

init:
	git submodule update --init

# Below is the original rocket-chip Makefile
base_dir=$(abspath ./)

MODEL ?= TestHarness
PROJECT ?= freechips.rocketchip.system
CFG_PROJECT ?= $(PROJECT)
CONFIG ?= $(CFG_PROJECT).DefaultConfig
MILL ?= mill

verilog:
	cd $(base_dir) && $(MILL) -i emulator[freechips.rocketchip.system.TestHarness,$(CONFIG)].mfccompiler.compile

clean-all: clean
	rm -rf out/

# === Module Generation (BMCFuzz mode: Chisel 3.6.1 + coverage) ===
MODULE_GEN_TOP = freechips.rocketchip.system.ModuleGenMain
MODULE_RTL_DIR = $(BUILD_DIR)/modules
MODULE_NAMES   = broadcast xbar axi4xbar plic sram_ecc toaxi4 fragmenter atomic \
                 timer idpool jtag_fsm arbiter reorder_q ecc async_queue replacement
MODULE_COVER  ?= mux,control

MODULE_TARGETS = $(addprefix gen-,$(MODULE_NAMES))
.PHONY: gen-modules $(MODULE_TARGETS) module-size

gen-modules: $(MODULE_TARGETS)

$(MODULE_TARGETS): gen-%:
	@mkdir -p $(MODULE_RTL_DIR)/$*
	NOOP_HOME=$(abspath .) mill -i generator[3.6.1].runMain $(MODULE_GEN_TOP) $* \
	  --target-dir $(MODULE_RTL_DIR)/$* \
	  --full-stacktrace \
	  -X sverilog \
	  COVER=$(MODULE_COVER)
	@cp -f $(BUILD_DIR)/generated-src/firrtl-cover.h  $(MODULE_RTL_DIR)/$*/
	@cp -f $(BUILD_DIR)/generated-src/firrtl-cover.cpp $(MODULE_RTL_DIR)/$*/

module-size: gen-modules
	@echo "=== Module SV Size Report (with coverage instrumentation) ==="
	@for name in $(MODULE_NAMES); do \
	  sv_file=$$(ls $(MODULE_RTL_DIR)/$$name/*.sv 2>/dev/null | head -1); \
	  if [ -n "$$sv_file" ]; then \
	    lines=$$(wc -l < "$$sv_file"); \
	    printf "  %-20s %6d lines  (%s)\n" "$$name" "$$lines" "$$sv_file"; \
	  else \
	    printf "  %-20s  [NOT FOUND]\n" "$$name"; \
	  fi; \
	done
