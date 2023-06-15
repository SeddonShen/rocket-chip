FUZZ_TOP  = freechips.rocketchip.system.FuzzMain
BUILD_DIR = $(abspath ./build)
TOP_V     = $(BUILD_DIR)/SimTop.v

MILL_ARGS = --target-dir $(BUILD_DIR)

# Number of CPU cores
NUM_CORES ?= 1

# Coverage support
ifneq ($(FIRRTL_COVER),)
MILL_ARGS += COVER=$(FIRRTL_COVER)
endif

SCALA_FILE = $(shell find ./src/main/scala -name '*.scala')
$(TOP_V): $(SCALA_FILE)
	mill -i rocketchip.runMain $(FUZZ_TOP) $(MILL_ARGS)
	@cp src/main/resources/vsrc/EICG_wrapper.v $(BUILD_DIR)
	@sed -i 's/UNOPTFLAT/LATCH/g' $(BUILD_DIR)/EICG_wrapper.v

sim-verilog: $(TOP_V)

emu: sim-verilog
	@$(MAKE) -C difftest emu SIM_TOP=SimTop NUM_CORES=$(NUM_CORES) NO_DIFF=1

clean:
	rm -rf $(BUILD_DIR)

idea:
	mill -i mill.scalalib.GenIdea/idea
