package freechips.rocketchip.system

import chisel3.stage.{ChiselCli, ChiselGeneratorAnnotation, ChiselStage}
import firrtl.options.Shell
import firrtl.stage.FirrtlCli

class FuzzStage extends ChiselStage {
  override val shell: Shell = new Shell("rocket-chip")
    with ChiselCli
    with FirrtlCli
}

object FuzzMain {
  def main(args: Array[String]): Unit = {
    (new FuzzStage).execute(args, Seq(
      ChiselGeneratorAnnotation(() => {
        freechips.rocketchip.diplomacy.DisableMonitors(p => new SimTop()(p))(new FuzzConfig)
      })
    ))
  }
}
