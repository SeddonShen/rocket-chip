package freechips.rocketchip.diplomacy
import freechips.rocketchip.config.Parameters
import chisel3.{RawModule, Reset, withClockAndReset, _}
import chisel3.experimental.hierarchy.{Definition, Instance, instantiable, public}
import scala.collection.mutable

abstract class LazyHardenModule[T <: LazyHardenModuleImpLike]()(implicit p: Parameters) extends LazyModule {
  override def module:T

  lazy val moduleInstance = Instance(moduleDef)

  override lazy val genericPathName = {
    val prefix = if (parent.isDefined) parent.get.pathName + "." else ""
    val id = LazyHardenModule.getId(className)
    val tail = if (id == 0) "moduleInstance" else s"moduleInstance_$id"
    val myPathName = prefix + tail
    myPathName
  }

  override def instanceName:String = {
    spreadNames(pathName)
    pathName.split('.').last
  }

  override val isHardenedModule = true

  protected[diplomacy] lazy val moduleDef = if(LazyHardenModule.elemExsist(className)){
    LazyHardenModule.getDef(className).asInstanceOf[Definition[T]]
  } else {
    val modDef = Definition(module)
    LazyHardenModule.defAdd(className, modDef, this)
    modDef
  }

  private def getAllDangles(currentModule:LazyModule):Seq[Dangle] = {
    if(currentModule.children.isEmpty){
      val allDangles = currentModule.nodes.reverse.flatMap(_.instantiate())
      val dangles = allDangles.map(d => d.copy(name = currentModule.desiredName + "_" + d.name))
      dangles
    } else {
      val childrenDangles = currentModule.children.reverse.flatMap(getAllDangles)
      val allDangles = currentModule.nodes.reverse.flatMap(_.instantiate()) ++ childrenDangles
      val pairingSource = allDangles.groupBy(_.source).filter(_._2.length == 2).keys.toSet
      val forward = allDangles.filter(d => !pairingSource(d.source))
      val dangles = forward.map(d => d.copy(name = currentModule.desiredName + "_" + d.name))
      dangles
    }
  }

  protected[diplomacy] def genDangles():Seq[Dangle] = {
    val myDangles:Seq[Dangle] = if(LazyHardenModule.elemExsist(className)) {
      getAllDangles(this)
    } else {
      moduleInstance.dangles
    }
    val auto:AutoBundle = moduleInstance.auto
    require(myDangles.length == auto.elements.values.toSeq.length)
    val newDangles = auto.elements.zip(myDangles).map({
      case((_,data),dg) =>
        dg.copy(data = data)
    })
    newDangles.toSeq
  }

  private def doSpreadNames(ntn: NameTreeNode, mod:LazyModule, prefix:String): Unit ={
    require(ntn.children.length == mod.children.length)
    mod.hardenModuleName = ntn.moduleName
    mod.hardenPathName = if(ntn.pathName == "") prefix else prefix + "." + ntn.pathName
    mod.isNamed = true
    if(ntn.children.nonEmpty) {
      for((n, m) <- ntn.children.zip(mod.children)) {
        doSpreadNames(n, m, prefix)
      }
    }
  }

  private def spreadNames(myPathName:String):Unit = {
    val nameTreeRoot = if(LazyHardenModule.ntExist(className)){
      LazyHardenModule.getNameTree(className)
    } else {
      val instantiatedWrapper = LazyHardenModule.getWrapper(className)
      val res = LazyHardenModule.genNameTreeNode(instantiatedWrapper, desiredName + ".").copy(pathName = "")
      LazyHardenModule.ntAdd(className, res)
      res
    }
    doSpreadNames(nameTreeRoot, this, myPathName)
  }
}

object LazyHardenModule {
  private val defMap = new mutable.HashMap[String,(Definition[LazyHardenModuleImpLike],Int, LazyModule)]()
  private def defAdd(name:String, definition: Definition[LazyHardenModuleImpLike], wrapper:LazyModule):Unit = {
    defMap(name) = (definition, 0, wrapper)
  }
  private def elemExsist(name:String):Boolean = {
    defMap.contains(name)
  }
  private def getDef(name:String):Definition[LazyHardenModuleImpLike] = {
    require(defMap.contains(name))
    defMap(name)._1
  }
  private def getWrapper(name:String):LazyModule = {
    require(defMap.contains(name))
    defMap(name)._3
  }
  private def getId(name:String):Int = {
    require(defMap.contains(name))
    defMap(name) = (defMap(name)._1, defMap(name)._2 + 1, defMap(name)._3)
    defMap(name)._2 - 1
  }

  private val nodeTreeMap = new mutable.HashMap[String, NameTreeNode]()
  private def ntAdd(name:String, root:NameTreeNode):Unit = {
    nodeTreeMap(name) = root
  }
  private def ntExist(name:String):Boolean = {
    nodeTreeMap.contains(name)
  }
  private def getNameTree(name:String):NameTreeNode = {
    require(nodeTreeMap.contains(name))
    nodeTreeMap(name)
  }



  private def genNameTreeNode(me:LazyModule, prefix:String):NameTreeNode = {
    if(me.children.isEmpty){
      val pn = if(prefix == "") me.pathName else me.pathName.stripPrefix(prefix)
      NameTreeNode(Seq(), me.moduleName, pn)
    } else {
      val childrenNodes = me.children.map(genNameTreeNode(_, prefix))
      NameTreeNode(childrenNodes, me.moduleName, me.pathName)
    }
  }
}

/** Trait describing the actual [[Module]] implementation wrapped by a [[LazyHardenModule]].
  *
  * This is the actual Chisel module that is lazily-evaluated in the second phase of Diplomacy.
  * Only the first call will generate circuit, other call just use the copy.
  * The IOs of all the instances must be the same.
  */
@instantiable
sealed trait LazyHardenModuleImpLike extends LazyModuleImpLike {

  /** [[LazyHardenModule]] that contains this instance. */
  require(!LazyHardenModuleImpLike.reinstantiationMap.contains(wrapper.className), "Illegal instantiation of a harden module occurred!")
  LazyHardenModuleImpLike.reinstantiationMap(wrapper.className) = 1
  @public val auto: AutoBundle
  @public val dangles: Seq[Dangle]
}

/** Actual description of a [[Module]] which can be instantiated by a call to [[LazyHardenModule.module]].
  *
  * @param wrapper the [[LazyHardenModule]] from which the `.module` call is being made.
  */
@instantiable
class LazyHardenModuleImp(val wrapper: LazyHardenModule[_ <: LazyHardenModuleImpLike]) extends MultiIOModule with LazyHardenModuleImpLike {

  /** Instantiate hardware of this `Module`. */
  val inst_info = instantiate()
  @public val auto = inst_info._1
  @public val dangles = inst_info._2
}

/** Actual description of a [[RawModule]] which can be instantiated by a call to [[LazyHardenModule.module]].
  *
  * @param wrapper the [[LazyHardenModule]] from which the `.module` call is being made.
  */
@instantiable
class LazyRawHardenModuleImp(val wrapper: LazyHardenModule[_ <: LazyHardenModuleImpLike]) extends RawModule with LazyHardenModuleImpLike {
  // These wires are the default clock+reset for all LazyHardenModule children.
  // It is recommended to drive these even if you manually drive the [[clock]] and [[reset]] of all of the
  // [[LazyRawModuleImp]] children.
  // Otherwise, anonymous children ([[Monitor]]s for example) will not have their [[clock]] and/or [[reset]] driven properly.
  /** drive clock explicitly. */
  val childClock: Clock = Wire(Clock())

  /** drive reset explicitly. */
  val childReset: Reset = Wire(Reset())
  // the default is that these are disabled
  childClock := false.B.asClock
  childReset := chisel3.DontCare
  val inst_info = withClockAndReset(childClock, childReset) {
    instantiate()
  }
  @public val auto = inst_info._1
  @public val dangles = inst_info._2
}

object LazyHardenModuleImpLike{
  private val reinstantiationMap = new mutable.HashMap[String,Int]()
}

