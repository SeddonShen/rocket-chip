export NOOP_HOME=$(pwd)
export BMCFUZZ_HOME=$(pwd)/ccover

# source $BMCFUZZ_HOME/env.sh

# OSS CAD Suite
export OSS_CAD_SUITE_HOME=$(pwd)/../oss-cad-suite/environment

# Formal Tool CORPUS
export CORPUS_DIR=$(pwd)/ccover/Formal/coverTasks/hexbin

# Fuzz and Formal Tool Cover Points
export COVER_POINTS_OUT=$(pwd)/ccover/Formal/coverTasks

# Fuzz path
export FUZZ_PATH=$(pwd)/build/fuzzer
export FUZZ_LOG=$(pwd)/ccover/Formal/logs/fuzz

# CSR State Change
export CSR_TRANSITION_DIR=$(pwd)/ccover/SetInitValues
# export CSR_WAVE=$(pwd)/ccover/SetInitValues/csr_wave
# export CSR_SNAPSHOT=$(pwd)/ccover/SetInitValues/csr_snapshot

# riscv corpus
export LINEARIZED_CORPUS=$(pwd)/corpus/linearized/riscv-all
export FOOTPRINTS_CORPUS=$(pwd)/corpus/footprints/riscv-all
# export RISCV_CORPUS=$(pwd)/corpus/linearized/riscv-tests

# RTL Source and Destination
# export RTL_SRC_DIR=$(pwd)/build/rtl
export RTL_INIT_DIR=$(pwd)/ccover/SetInitValues
export RTL_SRC_DIR=$(pwd)/ccover/Formal/demo/rocket
export RTL_DST_DIR=$(pwd)/ccover/Formal/coverTasks/rtl

# sby template
export SBY_TEMPLATE=$(pwd)/ccover/Formal/template.sby

