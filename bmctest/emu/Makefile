# bmctest/emu/Makefile — Build standalone module EMU / fuzzer binaries.
#
# Usage:
#   make emu     MODULE=timer                    # standalone EMU (debug/VCD)
#   make fuzzer  MODULE=timer BMCFUZZ=1          # fuzzer binary (links libfuzzer.a)
#   make emu-all                                 # build EMU for all 14 modules
#   make fuzzer-all BMCFUZZ=1                    # build fuzzer for all 14 modules
#
# Prerequisites:
#   - RTL generated:  make gen-modules  (from project root)
#   - BMCFUZZ_HOME set (for fuzzer mode): export BMCFUZZ_HOME=<path to ccover>

# ── Paths ─────────────────────────────────────────────────────────────
PROJECT_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
BMCTEST_DIR  := $(PROJECT_ROOT)/bmctest
EMU_DIR      := $(BMCTEST_DIR)/emu
MODULE_RTL   := $(PROJECT_ROOT)/build/modules

MODULE      ?= timer
BUILD_BASE  := $(BMCTEST_DIR)/build
BUILD_DIR   := $(BUILD_BASE)/$(MODULE)
BMCFUZZ ?=
ifneq ($(BMCFUZZ),)
COMPILE_DIR := $(BUILD_DIR)/fuzzer-compile
else
COMPILE_DIR := $(BUILD_DIR)/emu-compile
endif

# ── All 14 modules (excluding axi4xbar, async_queue) ─────────────────
ALL_MODULES := broadcast xbar plic sram_ecc toaxi4 fragmenter atomic \
               timer idpool jtag_fsm arbiter reorder_q ecc replacement

# ── Verilator configuration ──────────────────────────────────────────
EMU_TOP := SimTop

VERILATOR_VER_CMD = verilator --version 2>/dev/null | cut -f2 -d' ' | tr -d '.'
VERILATOR_5_000 := $(shell expr `$(VERILATOR_VER_CMD)` \>= 5000 2>/dev/null)

VFLAGS  = --cc --exe
VFLAGS += --top-module $(EMU_TOP)
VFLAGS += +define+VERILATOR=1
VFLAGS += +define+RANDOMIZE_REG_INIT
VFLAGS += +define+PRINTF_COND=1
VFLAGS += +define+DIFFTEST
VFLAGS += -Wno-STMTDLY -Wno-WIDTH
VFLAGS += --assert --x-assign unique
VFLAGS += --output-split 30000
VFLAGS += --output-split-cfuncs 30000
VFLAGS += --max-num-width 150000
VFLAGS += -O3

ifeq ($(VERILATOR_5_000),1)
VFLAGS += --no-timing +define+VERILATOR_5
else
VFLAGS += +define+VERILATOR_LEGACY
endif

# VCD trace support
EMU_TRACE ?=
ifneq ($(EMU_TRACE),)
VFLAGS += --trace
endif

# ── Source files ──────────────────────────────────────────────────────
# RTL from build/modules/$(MODULE)/
RTL_SV    = $(wildcard $(MODULE_RTL)/$(MODULE)/*.sv)
RTL_V     = $(wildcard $(MODULE_RTL)/$(MODULE)/GEN_w*.v)
RTL_EXTRA = $(wildcard $(MODULE_RTL)/$(MODULE)/plusarg_reader.v)

# SimTop wrapper
SIM_TOP_SV = $(EMU_DIR)/vsrc/SimTop_$(MODULE).sv

# C++ sources
EMU_CPP    = $(EMU_DIR)/csrc/module_emu.cpp
COVER_CPP  = $(wildcard $(MODULE_RTL)/$(MODULE)/firrtl-cover.cpp)
COVER_H    = $(MODULE_RTL)/$(MODULE)/firrtl-cover.h

ALL_VSRC = $(RTL_SV) $(RTL_V) $(RTL_EXTRA) $(SIM_TOP_SV)
ALL_CSRC = $(EMU_CPP) $(COVER_CPP)

# ── C++ flags ─────────────────────────────────────────────────────────
EMU_CXXFLAGS  = -DVERILATOR -std=c++17
EMU_CXXFLAGS += -I$(dir $(COVER_H))

FIRRTL_COVER_EXISTS := $(wildcard $(COVER_H))
ifneq ($(FIRRTL_COVER_EXISTS),)
EMU_CXXFLAGS += -DFIRRTL_COVER
endif

EMU_LDFLAGS =

# Trace support
ifneq ($(EMU_TRACE),)
EMU_CXXFLAGS += -DVM_TRACE=1
endif

# ── Fuzzer mode ───────────────────────────────────────────────────────
ifneq ($(BMCFUZZ),)
BMCFUZZ_HOME ?= $(PROJECT_ROOT)/ccover
FUZZER_LIB    = $(BMCFUZZ_HOME)/target/release/libfuzzer.a

EMU_CXXFLAGS += -DFUZZER_LIB
EMU_LDFLAGS  += $(abspath $(FUZZER_LIB)) -lrt -lpthread

TARGET = $(BUILD_DIR)/fuzzer
else
TARGET = $(BUILD_DIR)/emu
endif

# ── Verilator Makefile generation ─────────────────────────────────────
VMAKE = $(COMPILE_DIR)/V$(EMU_TOP).mk

$(VMAKE): $(ALL_VSRC)
	@mkdir -p $(COMPILE_DIR)
	verilator $(VFLAGS) \
		-Mdir $(COMPILE_DIR) \
		-CFLAGS "$(EMU_CXXFLAGS)" \
		$(if $(EMU_LDFLAGS),-LDFLAGS "$(EMU_LDFLAGS)") \
		-o $(abspath $(TARGET)) \
		$(ALL_VSRC) $(ALL_CSRC)
ifneq ($(VERILATOR_5_000),1)
	@sed -i 's/private/public/g' $(COMPILE_DIR)/VSimTop.h 2>/dev/null || true
endif

# ── Build target ──────────────────────────────────────────────────────
$(TARGET): $(VMAKE) $(ALL_CSRC)
	@echo "[module-emu] Building $(MODULE) → $(TARGET)"
	$(MAKE) -s VM_PARALLEL_BUILDS=1 OPT_FAST="-O3" OPT_SLOW="-O0" \
		-C $(COMPILE_DIR) -f V$(EMU_TOP).mk

# ── User-facing targets ──────────────────────────────────────────────
.PHONY: emu fuzzer clean emu-all fuzzer-all help

emu: $(TARGET)
	@echo "[module-emu] Done: $(TARGET)"

fuzzer: $(TARGET)
	@echo "[module-emu] Done: $(TARGET)"

clean:
	rm -rf $(BUILD_DIR)

clean-all:
	rm -rf $(BUILD_BASE)

# ── Batch targets ─────────────────────────────────────────────────────
emu-all:
	@for m in $(ALL_MODULES); do \
		echo "=== Building EMU for $$m ==="; \
		$(MAKE) -f $(abspath $(lastword $(MAKEFILE_LIST))) emu MODULE=$$m || exit 1; \
	done

fuzzer-all:
	@for m in $(ALL_MODULES); do \
		echo "=== Building fuzzer for $$m ==="; \
		$(MAKE) -f $(abspath $(lastword $(MAKEFILE_LIST))) fuzzer MODULE=$$m BMCFUZZ=1 || exit 1; \
	done

help:
	@echo "Module EMU/Fuzzer Build System"
	@echo ""
	@echo "Targets:"
	@echo "  emu          Build standalone EMU binary (MODULE=<name>)"
	@echo "  fuzzer       Build fuzzer binary (MODULE=<name> BMCFUZZ=1)"
	@echo "  emu-all      Build EMU for all 14 modules"
	@echo "  fuzzer-all   Build fuzzer for all 14 modules"
	@echo "  clean        Remove build for current MODULE"
	@echo "  clean-all    Remove all build artifacts"
	@echo ""
	@echo "Variables:"
	@echo "  MODULE       Target module name (default: timer)"
	@echo "  BMCFUZZ      Enable fuzzer mode (set to 1)"
	@echo "  EMU_TRACE    Enable VCD trace (set to 1)"
	@echo "  BMCFUZZ_HOME Path to BMCFuzz (default: PROJECT_ROOT/ccover)"
	@echo ""
	@echo "Available modules: $(ALL_MODULES)"
