// See LICENSE.SiFive for license details.

package freechips.rocketchip.tilelink

import Chisel._
import freechips.rocketchip.config.Parameters
import freechips.rocketchip.diplomacy._

// Moves the AddressSets of slave devices around
// Combine with TLFilter to remove slaves or reduce their size
/*class TLMap(fn: AddressSet => BigInt)(implicit p: Parameters) extends LazyModule
{
  val node = TLAdapterNode(
    clientFn = { cp => cp },
    managerFn = { mp =>
      mp.v1copy(managers = mp.managers.map(m =>
        m.v1copy(address = m.address.map(a =>
          AddressSet(fn(a), a.mask)))))})

  lazy val module = new LazyModuleImp(this) {
    (node.in zip node.out) foreach { case ((in, edgeIn), (out, edgeOut)) =>
      out <> in
      val convert = edgeIn.manager.managers.flatMap(_.address) zip edgeOut.manager.managers.flatMap(_.address)
      def forward(x: UInt) =
        convert.map { case (i, o) => Mux(i.contains(x), UInt(o.base) | (x & UInt(o.mask)), UInt(0)) }.reduce(_ | _)
      def backward(x: UInt) =
        convert.map { case (i, o) => Mux(o.contains(x), UInt(i.base) | (x & UInt(i.mask)), UInt(0)) }.reduce(_ | _)

      out.a.bits.address := forward(in.a.bits.address)
      if (edgeOut.manager.anySupportAcquireB && edgeOut.client.anySupportProbe) {
        out.c.bits.address := forward(in.c.bits.address)
        in.b.bits.address := backward(out.b.bits.address)
      }
    }
  }
}

object TLMap
{
  def apply(fn: AddressSet => BigInt)(implicit p: Parameters): TLNode =
  {
    val map = LazyModule(new TLMap(fn))
    map.node
  }
}*/

class TLMap(mapsize: BigInt)(implicit p: Parameters) extends LazyModule
{
  val node = TLAdapterNode(
    clientFn = { cp => cp },
    managerFn = { mp =>
      mp.v1copy(managers = mp.managers.map(m =>
        m.v1copy(address = m.address.map(a =>
          AddressSet(a.base + mapsize, a.mask & (mapsize-1))))))})

  lazy val module = new LazyModuleImp(this) {
    (node.in zip node.out) foreach { case ((in, edgeIn), (out, edgeOut)) =>
      out <> in
      val convert = edgeIn.manager.managers.flatMap(_.address) zip edgeOut.manager.managers.flatMap(_.address)
      def forward(x: UInt) =
        convert.map { case (i, o) => Mux(i.contains(x), UInt(o.base) | (x & UInt(i.mask)), UInt(0)) }.reduce(_ | _)
      def backward(x: UInt) =
        convert.map { case (i, o) => Mux(o.contains(x), UInt(i.base) | (x & UInt(i.mask)), UInt(0)) }.reduce(_ | _)

      out.a.bits.address := backward(in.a.bits.address)
      if (edgeOut.manager.anySupportAcquireB && edgeOut.client.anySupportProbe) {
        out.c.bits.address := backward(in.c.bits.address)
        in.b.bits.address := forward(out.b.bits.address)
      }
      convert.map { case (i, o) => 
        println("in.base:0x%x; in.mask:0x%x".format(i.base,i.mask))
        println("out.base:0x%x; out.mask:0x%x\n".format(o.base,o.mask)) 
      }
    }
  }
}

object TLMap
{
  def apply(mapsize: BigInt)(implicit p: Parameters): TLNode =
  {
    val map = LazyModule(new TLMap(mapsize))
    map.node
  }
}

class TLMap_IO(mapsize: BigInt)(implicit p: Parameters) extends LazyModule
{
  val node = TLAdapterNode(
    clientFn = { cp => cp },
    managerFn = { mp => mp },
  )

  lazy val module = new LazyModuleImp(this) {
    (node.in zip node.out) foreach { case ((in, edgeIn), (out, edgeOut)) =>
      out <> in
      val convert = edgeIn.manager.managers.flatMap(_.address) zip edgeOut.manager.managers.flatMap(_.address)

      when((in.a.bits.address>="h40600000".U) & (in.a.bits.address<"h50000000".U)){
        out.a.bits.address := in.a.bits.address + UInt(mapsize)
      } .otherwise {
        out.a.bits.address := in.a.bits.address
      }
      when((in.c.bits.address>="h40600000".U) & (in.c.bits.address<"h50000000".U)){
        out.c.bits.address := in.c.bits.address + UInt(mapsize)
      } .otherwise {
        out.c.bits.address := in.c.bits.address
      }
      when((out.b.bits.address>="h40600000".U) & (out.b.bits.address<"h50000000".U)){
        in.b.bits.address := out.b.bits.address - UInt(mapsize)
      } .otherwise {
        in.b.bits.address := out.b.bits.address
      }
      
      convert.map { case (i, o) => 
        println("in.base:0x%x; in.mask:0x%x".format(i.base,i.mask))
        println("out.base:0x%x; out.mask:0x%x\n".format(o.base,o.mask)) 
      }
    }
  }
}

object TLMap_IO
{
  def apply(mapsize: BigInt)(implicit p: Parameters): TLNode =
  {
    val map = LazyModule(new TLMap_IO(mapsize))
    map.node
  }
}
