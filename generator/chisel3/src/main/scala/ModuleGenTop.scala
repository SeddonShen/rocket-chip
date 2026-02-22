package freechips.rocketchip.system

import chisel3._
import chisel3.stage.{ChiselCli, ChiselGeneratorAnnotation, ChiselStage}
import chisel3.util.{Valid, log2Ceil}
import firrtl.options.Shell
import firrtl.stage.FirrtlCli
import org.chipsalliance.cde.config._
import freechips.rocketchip.devices.tilelink._
import freechips.rocketchip.diplomacy._
import freechips.rocketchip.amba.axi4._
import freechips.rocketchip.interrupts._
import freechips.rocketchip.jtag._
import freechips.rocketchip.subsystem.BaseSubsystemConfig
import freechips.rocketchip.tilelink._
import freechips.rocketchip.unittest._
import freechips.rocketchip.util._
import xfuzz.CoverPoint

class ModuleGenConfig extends Config(new BaseSubsystemConfig)

// ---- Wrapper: TLBroadcast ----
class StandaloneBroadcast(txns: Int)(implicit p: Parameters) extends LazyModule {
  val fuzz  = LazyModule(new TLFuzzer(txns))
  val model = LazyModule(new TLRAMModel("Broadcast"))
  val ram   = LazyModule(new TLRAM(AddressSet(0x0, 0x3ff)))

  (ram.node
    := TLFragmenter(4, 64)
    := TLDelayer(0.1)
    := TLBroadcast(64, numTrackers = 4)
    := TLDelayer(0.1)
    := model.node
    := fuzz.node)

  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) with UnitTestModule {
    io.finished := fuzz.module.io.finished
  }
}

// ---- Wrapper: TLXbar (Multiclient) ----
class StandaloneXbar(nManagers: Int, nClients: Int, txns: Int)(implicit p: Parameters) extends LazyModule {
  val xbar = LazyModule(new TLXbar)

  val fuzzers = (0 until nClients) map { _ =>
    val fuzz = LazyModule(new TLFuzzer(txns))
    xbar.node := TLDelayer(0.1) := fuzz.node
    fuzz
  }

  (0 until nManagers) foreach { n =>
    val ram = LazyModule(new TLRAM(AddressSet(0x0 + 0x400 * n, 0x3ff)))
    ram.node := TLFragmenter(4, 256) := TLDelayer(0.1) := xbar.node
  }

  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) with UnitTestModule {
    io.finished := fuzzers.last.module.io.finished
  }
}

// ---- Wrapper: AXI4Xbar ----
class StandaloneAXI4Xbar(txns: Int)(implicit p: Parameters) extends LazyModule {
  val xbar = AXI4Xbar()
  val slaveSize = 0x2000

  val slaves = Seq.tabulate(2) { i =>
    val ram = LazyModule(new AXI4RAM(AddressSet(slaveSize * i, slaveSize - 1), beatBytes = 8))
    (ram.node
      := AXI4Fragmenter()
      := AXI4Buffer(BufferParams.flow)
      := AXI4Delayer(0.25)
      := xbar)
    ram
  }

  val masters = Seq.fill(2) { LazyModule(new TLFuzzer(txns, 8, nOrdered = Some(1))) }
  val masterBandSize = slaveSize >> 1
  masters.zipWithIndex.foreach { case (m, i) =>
    val filter = TLFilter.mSelectIntersect(AddressSet(i * masterBandSize, ~BigInt(slaveSize - masterBandSize)))
    (xbar
      := AXI4Delayer(0.25)
      := AXI4Deinterleaver(4096)
      := TLToAXI4()
      := TLFilter(filter)
      := TLRAMModel(s"AXI4Xbar Master $i")
      := m.node)
  }

  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) with UnitTestModule {
    io.finished := masters.map(_.module.io.finished).reduce(_ || _)
  }
}

// ---- Wrapper: PLIC ----
class StandalonePLIC(implicit p: Parameters) extends LazyModule with BindingScope {
  val fuzz = LazyModule(new TLFuzzer(100))
  val plic = LazyModule(new TLPLIC(PLICParams(baseAddress = 0x0C000000, maxPriorities = 7), beatBytes = 4))

  plic.node := TLFragmenter(4, 64) := TLDelayer(0.1) := fuzz.node

  val intSrcNode = IntSourceNode(IntSourcePortSimple(num = 8, resources = Nil))
  plic.intnode := intSrcNode

  val intSinkNode = IntSinkNode(IntSinkPortSimple(ports = 1))
  intSinkNode := plic.intnode

  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) with UnitTestModule {
    io.finished := fuzz.module.io.finished
    intSrcNode.out.flatMap(_._1).foreach(_ := false.B)
    intSinkNode.in.flatMap(_._1).foreach(_ => ())
  }
}

// ---- Wrapper: TLRAM with ECC ----
class StandaloneSRAMECC(txns: Int)(implicit p: Parameters) extends LazyModule {
  val fuzz  = LazyModule(new TLFuzzer(txns))
  val model = LazyModule(new TLRAMModel("SRAMSimple"))
  val ram   = LazyModule(new TLRAM(
    AddressSet(0x0, 0x3ff),
    atomics   = true,
    beatBytes = 8,
    ecc       = ECCParams(bytes = 4, code = new SECDEDCode),
    sramReg   = true))

  ram.node := TLDelayer(0.25) := model.node := fuzz.node

  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) with UnitTestModule {
    io.finished := fuzz.module.io.finished
  }
}

// ---- Wrapper: TLToAXI4 (full bridge chain) ----
class StandaloneToAXI4(txns: Int)(implicit p: Parameters) extends LazyModule {
  val master = LazyModule(new AXI4FuzzMaster(txns))
  val slave  = LazyModule(new AXI4FuzzSlave)

  slave.node := master.node

  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) with UnitTestModule {
    io.finished := master.module.io.finished
  }
}

// ---- Wrapper: TLFragmenter ----
class StandaloneFragmenter(txns: Int)(implicit p: Parameters) extends LazyModule {
  val fuzz  = LazyModule(new TLFuzzer(txns))
  val model = LazyModule(new TLRAMModel("Fragmenter"))
  val ram   = LazyModule(new TLRAM(AddressSet(0x0, 0x3ff), beatBytes = 4))

  (ram.node
    := TLDelayer(0.1)
    := TLBuffer(BufferParams.flow)
    := TLDelayer(0.1)
    := TLFragmenter(4, 256, earlyAck = EarlyAck.AllPuts)
    := TLDelayer(0.1)
    := TLBuffer(BufferParams.flow)
    := TLFragmenter(4, 128)
    := TLDelayer(0.1)
    := TLBuffer(BufferParams.flow)
    := model.node
    := fuzz.node)

  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) with UnitTestModule {
    io.finished := fuzz.module.io.finished
  }
}

// ---- Wrapper: TLAtomicAutomata ----
class StandaloneAtomic(txns: Int)(implicit p: Parameters) extends LazyModule {
  val fuzz  = LazyModule(new TLFuzzer(txns))
  val model = LazyModule(new TLRAMModel("AtomicAutomata"))
  val ram   = LazyModule(new TLRAM(AddressSet(0x0, 0x3ff)))

  (ram.node
    := TLFragmenter(4, 256)
    := TLDelayer(0.1)
    := TLAtomicAutomata()
    := TLDelayer(0.1)
    := model.node
    := fuzz.node)

  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) with UnitTestModule {
    io.finished := fuzz.module.io.finished
  }
}

// ---- Wrapper: ECC (SECDEDCode encode/decode) ----
class ECCModule(dataWidth: Int) extends Module {
  val code = new SECDEDCode
  val io = IO(new Bundle {
    val dataIn        = Input(UInt(dataWidth.W))
    val poison        = Input(Bool())
    val encoded       = Output(UInt(code.width(dataWidth).W))
    val decoded       = Output(UInt(dataWidth.W))
    val correctable   = Output(Bool())
    val uncorrectable = Output(Bool())
  })
  val enc = code.encode(io.dataIn, io.poison)
  io.encoded := enc
  val dec = code.decode(enc)
  io.decoded       := dec.corrected
  io.correctable   := dec.correctable
  io.uncorrectable := dec.uncorrectable
}

// ---- Wrapper: Replacement (PseudoLRU) ----
class ReplacementModule(nWays: Int) extends Module {
  val plru = new PseudoLRU(nWays)
  val io = IO(new Bundle {
    val touch      = Flipped(Valid(UInt(log2Ceil(nWays).W)))
    val replaceWay = Output(UInt(log2Ceil(nWays).W))
    val state      = Output(UInt(plru.nBits.W))
  })
  when(io.touch.valid) { plru.access(io.touch.bits) }
  io.replaceWay := plru.way
  io.state      := plru.state_read
}

// ---- Main entry point ----
object ModuleGenMain {
  def main(args: Array[String]): Unit = {
    val moduleName = args.head
    val stageArgs = args.tail

    (new FuzzStage).execute(stageArgs, Seq(
      ChiselGeneratorAnnotation(() => {
        implicit val p: Parameters = new ModuleGenConfig
        implicit val valName: ValName = ValName(moduleName)
        moduleName match {
          case "broadcast"   => LazyModule(new StandaloneBroadcast(100)).module
          case "xbar"        => LazyModule(new StandaloneXbar(4, 4, 100)).module
          case "axi4xbar"    => LazyModule(new StandaloneAXI4Xbar(100)).module
          case "plic"        => LazyModule(new StandalonePLIC).module
          case "sram_ecc"    => LazyModule(new StandaloneSRAMECC(100)).module
          case "toaxi4"      => LazyModule(new StandaloneToAXI4(100)).module
          case "fragmenter"  => LazyModule(new StandaloneFragmenter(100)).module
          case "atomic"      => LazyModule(new StandaloneAtomic(100)).module
          case "timer"       => new Timer(1024, 8)
          case "idpool"      => new IDPool(32)
          case "jtag_fsm"    => new JtagStateMachine
          case "arbiter"     => new HellaCountingArbiter(UInt(64.W), 4, 8)
          case "reorder_q"   => new ReorderQueue(UInt(64.W), 4, Some(16))
          case "ecc"         => new ECCModule(64)
          case "async_queue" => new AsyncQueue(UInt(64.W), AsyncQueueParams())
          case "replacement" => new ReplacementModule(8)
          case other         => throw new IllegalArgumentException(s"Unknown module: $other")
        }
      })
    ) ++ CoverPoint.getTransforms(stageArgs)._2)
  }
}
