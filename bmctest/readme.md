# BMCFuzz 通用模块 Benchmark 筛选

## 目标

从 rocket-chip 中提取的 15 个独立非处理器模块中，筛选出适合作为 **BMCFuzz benchmark** 的模块。判定标准：

- **纯 BMC 跑不动**：在合理时间/深度内，大量 cover point 无法被 BMC 覆盖（BMC 深度瓶颈）
- **加上快照机制能跑动**：模块具有足够的时序深度和状态复杂度，使得 BMCFuzz 的 snapshot 机制能发挥作用

论文参考：[ICCAD25_BMCFuzz_Camera_Ready.pdf](./ICCAD25_BMCFuzz_Camera_Ready.pdf)

## 背景知识

### BMCFuzz 核心思路

BMCFuzz 结合了 **有界模型检测（BMC）** 和 **模糊测试（Fuzz）**：

1. BMC 从初始状态展开，在有限深度 k 内搜索能到达 cover point 的路径
2. 对于时序深度很深的模块，BMC 在合理深度内无法覆盖深层状态 —— 这是 BMC 的瓶颈
3. BMCFuzz 通过 **快照机制** 解决：先用 Fuzz 探索到中间状态，保存为快照（snapshot），再从快照出发用 BMC 展开，大幅减少所需的展开深度

### 覆盖率插桩

所有模块的 SV 文件已通过 `xfuzz.CoverPoint.getTransforms` 注入了覆盖率插桩（Chisel 3.6.1）。SV 中的覆盖率模块形如：

```systemverilog
GEN_w2_mux mux_cover_42 (
  .clock(clock),
  .reset(reset),
  .valid({condition_1, condition_0})
);
```

其中 `GEN_w<N>_<type>` 是插桩生成的黑盒模块，`valid` 信号的每一位对应一个 cover point。

### 现有工具链

BMCFuzz 的 formal 部分位于 `ccover/Formal/`：

- `Tools.py` — RTL 解析、cover point 提取、sby 文件生成
  - `parse_and_modify_rtl_files()`: 从 SV 中提取 `GEN_w<N>_<type>` 块，生成 `cover()` 或 `assert(~...)` 语句
  - `generate_sby_files()`: 为每个 cover point 生成独立的 `.sby` 验证任务
- `Executor.py` — 并行执行 sby 任务（ThreadPoolExecutor）
- `template.sby` — SymbiYosys 模板，支持 SMT（`smtbmc bitwuzla`）和 SAT（`aiger rIC3`）两种引擎
- `Scheduler.py` — Hybrid Loop 调度器（BMC + Fuzz 交替执行）

**注意**：现有工具链针对处理器（SimTop）设计，包含 DifftestMem、CSR 转换等处理器特定逻辑。通用模块需要一个**简化版**的 BMC 测试流程。

## 15 个模块清单

> **注意**：原始 16 个模块中 `axi4xbar` 已被排除 —— 其 `MemRWHelper.v` 在 `SYNTHESIS` 宏下会分配 2 GB 内存，formal 工具无法处理。

### 大型模块（Diplomacy LazyModule，含 TLFuzzer 测试拓扑）

| 模块 | SV 行数 | 文件 | Scala 源 | 核心特点 |
|------|--------|------|----------|---------|
| broadcast | 35,324 | StandaloneBroadcast.sv | tilelink/Broadcast.scala (522行) | TLBroadcast 缓存一致性广播，4 tracker FSM |
| xbar | 82,021 | StandaloneXbar.sv | tilelink/Xbar.scala (409行) | 4-client 4-manager TileLink 交叉开关 |
| plic | 12,125 | StandalonePLIC.sv | devices/tilelink/Plic.scala (369行) | 平台级中断控制器，8 设备 |
| sram_ecc | 25,135 | StandaloneSRAMECC.sv | tilelink/SRAM.scala (380行) | SECDED 纠错码 SRAM |
| toaxi4 | 112,542 | StandaloneToAXI4.sv | tilelink/ToAXI4.scala (305行) | TileLink-to-AXI4 完整桥接链 |
| fragmenter | 51,110 | StandaloneFragmenter.sv | tilelink/Fragmenter.scala (374行) | 双级事务分片器 |
| atomic | 34,007 | StandaloneAtomic.sv | tilelink/AtomicAutomata.scala (344行) | 原子操作自动机 |

### 小型模块（普通 Chisel Module）

| 模块 | SV 行数 | 文件 | Scala 源 | 核心特点 |
|------|--------|------|----------|---------|
| timer | 782 | Timer.sv | util/Timer.scala (~97行) | 多路计数器 + 超时检测 |
| idpool | 1,306 | IDPool.sv | util/IDPool.scala (~56行) | 位图 ID 分配/回收 |
| jtag_fsm | 390 | JtagStateMachine.sv | jtag/JtagStateMachine.scala (~142行) | 16 状态 JTAG FSM |
| arbiter | 372 | HellaCountingArbiter.sv | util/Arbiters.scala (~147行) | 锁定计数仲裁器 |
| reorder_q | 1,077 | ReorderQueue.sv | util/ReorderQueue.scala (~83行) | 标签重排序缓冲 |
| ecc | 67 | ECCModule.sv | util/ECC.scala (~234行) | SECDED 编解码（纯组合逻辑） |
| async_queue | 2,953 | AsyncQueue.sv | util/AsyncQueue.scala (~231行) | 跨时钟域异步 FIFO |
| replacement | 191 | ReplacementModule.sv | util/Replacement.scala (~600+行) | PseudoLRU 替换策略 |

所有 SV 文件位于 `build/modules/<name>/` 目录，通过 `make gen-modules` 生成（Chisel 3.6.1 + 覆盖率插桩）。

生成入口：`generator/chisel3/src/main/scala/ModuleGenTop.scala` 中的 `ModuleGenMain`。

## BMC 深度测试脚本 `bmctest/bmc_depth_test.py`

脚本已实现，核心流程分为 4 步：

### 1. RTL 处理与 cover point 解析 (`process_rtl`)

从模块的 SV 文件中提取 `GEN_w<N>_{cover_type}` 覆盖率实例，插桩并写入工作目录：

1. **复制辅助文件**：将 `GEN_w*_*.v`、`plusarg_reader.v` 拷贝到 `work/<mod>/rtl/`，生成 `define.sv`
2. **时钟统一**：`posedge <anything>` → `posedge glb_clk`（多时钟域模块需统一时钟以配合 formal 工具）
3. **解析 GEN 实例**：正则匹配 `GEN_w<N>_{cover_type}` 块，提取 reset / valid 信号
4. **插入验证语句**：
   - SMT 模式：`cover(valid[bit])`
   - SAT 模式：`assert(~valid[bit])`
5. **初始状态约束**：为未初始化的 `reg` 插入 `initial assume(!reg)`
   - 跳过 `RAND` 辅助寄存器
   - 跳过带显式初始值的寄存器
   - 数组寄存器元素 >16 个时跳过（避免 formal 工具过载）

### 2. SBY 任务生成 (`generate_sby_files`)

为每个 cover point 生成独立的 `.sby` 文件，使用 `chformal` 命令隔离单个 cover point：

- SMT 模式：`mode cover` + `smtbmc bitwuzla`，用 `chformal -remove -cover c:<label> %n` 移除其他 cover，再 `chformal -remove -assert` 移除所有 assert
- SAT 模式：`mode bmc` + `aiger rIC3`，用 `chformal -remove -assert c:<label> %n` 移除其他 assert，再 `chformal -remove -cover` 移除所有 cover

### 3. 并行 BMC 执行 (`run_bmc`)

- 使用 `ThreadPoolExecutor` 并行执行所有 sby 任务（默认 64 workers，受 `os.cpu_count()` 上限）
- 自动查找 OSS CAD Suite 环境和 sby 命令（优先使用项目内自定义 sby）
- 解析 sby logfile，提取每个 cover point 的状态和深度

### 4. 结果分析 (`analyze_results`)

对每个模块输出：
- 总 cover point 数、已覆盖 / 未覆盖 / 超时 / 错误数
- 覆盖率和不可覆盖率
- 覆盖深度统计（平均 / 最大 / 中位数）
- 深度分布直方图（按 10 步分桶）
- **瓶颈判定**：不可覆盖率 >30% 标记为 BMC 瓶颈

输出文件：
- 每模块：`work/<mod>/results.json`
- 多模块汇总：`reports/summary.json` + `reports/summary.txt`

## 使用方法

### 单模块测试

```bash
python3 bmctest/bmc_depth_test.py --module broadcast --depth 50 --timeout 3600 --mode smt
```

### 全模块测试

```bash
python3 bmctest/bmc_depth_test.py --all --depth 50 --timeout 3600 --mode smt
```

### 完整 CLI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--module` / `--all` | (必选其一) | 测试单个模块或全部 15 个模块 |
| `--depth` | 50 | BMC 展开深度 |
| `--timeout` | 3600 | 每个任务的超时时间（秒） |
| `--mode` | smt | 验证模式：`smt`（cover + smtbmc）或 `sat`（bmc + rIC3） |
| `--workers` | 64 | 最大并行 worker 数（受 CPU 核数上限） |
| `--ric3` | (无) | rIC3 二进制路径（SAT 模式必需） |
| `--build-dir` | `build/modules` | 模块 SV 根目录 |
| `--work-dir` | `bmctest/work` | 工作目录 |
| `--cover-type` | toggle | 覆盖率插桩类型（需与 SV 生成时一致） |

## Benchmark 筛选标准

根据测试结果，筛选出满足以下条件的模块：

1. **BMC 瓶颈**：在 depth=50~100 范围内，仍有大量（>30%）cover point 无法被覆盖
2. **非纯组合逻辑**：模块必须有足够的时序深度（排除 ecc 这种纯组合逻辑模块）
3. **状态可达性**：cover point 不是死代码（理论上通过足够长的仿真可以覆盖）

预期结果：
- **ecc**（67 行，纯组合）、**arbiter**（372 行）、**replacement**（191 行）等小模块可能 BMC 直接穷举完 —— 不适合作为 benchmark
- **broadcast**（35K 行）、**xbar**（82K 行）、**toaxi4**（112K 行）等大型模块可能 BMC 深度瓶颈严重 —— 适合作为 benchmark
- 中等模块（timer、idpool、jtag_fsm、async_queue）需要实际测试才知道

## 环境依赖

- SymbiYosys（sby）—— 通过 `OSS_CAD_SUITE_HOME` 环境变量加载，或自动搜索已知路径
- bitwuzla（SMT solver）—— 包含在 OSS CAD Suite 中
- rIC3（SAT-based IC3/PDR engine）—— 位于 `ccover/Formal/bin/rIC3`（SAT 模式需要通过 `--ric3` 指定）
- Python 3.8+，依赖：`tqdm`（可选，缺失时自动降级为无进度条模式）

## 关键文件路径

```
rocket-chip/
├── build/modules/                    # 生成的 SV 文件
│   ├── broadcast/
│   │   ├── StandaloneBroadcast.sv
│   │   ├── GEN_w1_mux.v
│   │   ├── GEN_w2_control.v
│   │   └── ...
│   ├── xbar/
│   ├── timer/
│   └── ...
├── bmctest/                          # 本测试目录
│   ├── readme.md                     # 本文件
│   ├── bmc_depth_test.py             # BMC 深度测试脚本
│   ├── work/                         # 运行时工作目录（自动生成）
│   │   └── <module>/
│   │       ├── rtl/                  # 插桩后的 RTL 文件
│   │       │   ├── define.sv
│   │       │   ├── <module>.sv
│   │       │   ├── GEN_w*.v
│   │       │   └── plusarg_reader.v
│   │       ├── tasks/                # SBY 任务文件及输出
│   │       │   ├── cover_<N>.sby
│   │       │   └── cover_<N>/logfile.txt
│   │       └── results.json          # 单模块结果
│   └── reports/                      # 多模块汇总报告（自动生成）
│       ├── summary.json
│       └── summary.txt
├── generator/chisel3/src/main/scala/
│   ├── ModuleGenTop.scala            # 模块生成入口（15 个 wrapper + ModuleGenMain）
│   └── FuzzTop.scala                 # 处理器 SV 生成入口（参考）
├── ccover/Formal/
│   ├── Tools.py                      # RTL 解析、sby 生成（参考，但需简化）
│   ├── Executor.py                   # 并行 sby 执行器（参考）
│   ├── Scheduler.py                  # Hybrid Loop 调度（处理器专用）
│   ├── template.sby                  # sby 模板
│   └── Coverage.py                   # 覆盖率追踪
├── Makefile                          # make gen-modules 生成全部模块
└── env.sh                            # 环境变量设置
```

## 注意事项

1. **`axi4xbar` 已排除**：其 `MemRWHelper.v` 在 `SYNTHESIS` 宏下分配 2 GB 内存，formal 工具无法处理
2. **大型模块的 SV 包含完整 Diplomacy 拓扑**（TLFuzzer -> DUT -> TLRAM），BMC 需要处理的状态空间包括 fuzzer 和 RAM 的状态。这实际上更有利于 benchmark 测试——因为这模拟了真实的系统集成环境
3. **小型模块是纯 Module**，没有 Diplomacy 拓扑，状态空间更小，BMC 更容易穷举
4. **覆盖率类型**：通过 `--cover-type` 指定，需要与 SV 生成时使用的类型一致。如需重新生成：`make gen-modules MODULE_COVER=toggle`
5. **glb_clk 替换**：脚本自动将所有 `posedge <clock>` 替换为 `posedge glb_clk`（多时钟域模块需要统一时钟以配合 formal 工具）
6. **initial assume**：脚本自动为未初始化的 `reg` 插入 `initial assume(!reg)`，但会跳过 RAND 辅助寄存器、带初始值的寄存器、以及元素超过 16 个的数组寄存器
