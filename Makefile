FUZZ_TOP  = freechips.rocketchip.system.FuzzMain
BUILD_DIR = $(abspath ./build)
TOP_V     = $(BUILD_DIR)/SimTop.v

MILL_ARGS = --target-dir $(BUILD_DIR) \
            --full-stacktrace

# Number of CPU cores
NUM_CORES ?= 1

# Coverage support
ifneq ($(FIRRTL_COVER),)
MILL_ARGS += COVER=$(FIRRTL_COVER)
endif

BOOTROM_DIR = $(abspath ./bootrom)
BOOTROM_SRC = $(BOOTROM_DIR)/bootrom.S
BOOTROM_IMG = $(BOOTROM_DIR)/bootrom.img

$(BOOTROM_IMG): $(BOOTROM_SRC)
	@make -C $(BOOTROM_DIR) all

SCALA_FILE = $(shell find ./src/main/scala -name '*.scala')
$(TOP_V): $(SCALA_FILE) $(BOOTROM_IMG)
	mill -i rocketchip.runMain $(FUZZ_TOP) $(MILL_ARGS)
	@cp src/main/resources/vsrc/EICG_wrapper.v $(BUILD_DIR)
	@sed -i 's/UNOPTFLAT/LATCH/g' $(BUILD_DIR)/EICG_wrapper.v

sim-verilog: $(TOP_V)

emu: sim-verilog
	@$(MAKE) -C difftest emu WITH_CHISELDB=0 WITH_CONSTANTIN=0

clean:
	rm -rf $(BUILD_DIR)

idea:
	mill -i mill.scalalib.GenIdea/idea
