package freechips.rocketchip.system

import chisel3.stage.ChiselGeneratorAnnotation
import circt.stage._

object FuzzMain {
  def main(args: Array[String]): Unit = {
    val generator = Seq(ChiselGeneratorAnnotation(() => {
      freechips.rocketchip.diplomacy.DisableMonitors(p => new SimTop()(p))(new FuzzConfig)
    }))
    (new ChiselStage).execute(args, generator
      :+ CIRCTTargetAnnotation(CIRCTTarget.SystemVerilog)
      :+ FirtoolOption("--disable-annotation-unknown")
    )
  }
}
