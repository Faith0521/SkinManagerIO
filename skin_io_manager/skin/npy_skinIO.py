# -*- coding: utf-8 -*-
import os
import maya.OpenMaya as om
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as om2Anim
import maya.cmds as cmds
import maya.mel as mel
import numpy as np

from . import getSkinCluster
from ..utils.helpers import get_skinCluster_mfn


NPY_EXT = ".npz"
PACK_NPY_EXT = ".npzPack"

npd_type = "float64"


class SkinClusterIO(object):

    def __init__(self):
        self.cDataIO = DataIO()

        # 初始化变量
        self.name = ''
        self.type = 'skinCluster'
        self.weightsNonZero_Array = []
        self.weights_Array = []
        self.infMap_Array = []
        self.vertSplit_Array = []
        self.inf_Array = []
        self.skinningMethod = 1
        self.normalizeWeights = 1
        self.geometry = None
        self.blendWeights = []
        self.vtxCount = 0
        self.envelope = 1
        self.useComponents = 0
        self.deformUserNormals = 1

    def get_mesh_components_from_tag_expression(self, skinPy, tag='*'):
        # 获取连接到蒙皮簇的第一个几何体
        geometries = cmds.skinCluster(skinPy, query=True, geometry=True)
        if not geometries:
            raise RuntimeError("No geometries found connected to the skin cluster.")
        geo = geometries[0]

        # 获取形状的 geo out 属性
        out_attr = cmds.deformableShape(geo, localShapeOutAttr=True)[0]

        # 获取输出几何体数据作为 MObject
        sel = om.MSelectionList()
        sel.add(geo)
        dep = om.MObject()
        sel.getDependNode(0, dep)
        fn_dep = om.MFnDependencyNode(dep)
        plug = fn_dep.findPlug(out_attr, True)
        obj = plug.asMObject()

        # 使用 MFnGeometryData 类查询标签表达式的组件
        fn_geodata = om.MFnGeometryData(obj)

        # 组件 MObject
        components = fn_geodata.resolveComponentTagExpression(tag)

        dagPath = om.MDagPath.getAPathTo(dep)
        return dagPath, components

    def get_data(self, skinCluster):
        # 获取蒙皮簇组件
        try:
            fnSet = om.MFnSet(get_skinCluster_mfn(skinCluster).deformerSet())
            members = om.MSelectionList()
            fnSet.getMembers(members, False)
            dagPath = om.MDagPath()
            components = om.MObject()
            members.getDagPath(0, dagPath, components)
        except:
            dagPath, components = self.get_mesh_components_from_tag_expression(skinCluster)

        # 获取几何体
        geometry = cmds.skinCluster(skinCluster, query=True, geometry=True)[0]

        # 获取顶点ID数组
        vtxID_Array = range(0, len(cmds.ls('%s.vtx[*]' % geometry, fl=1)))

        # 获取蒙皮数据（使用 om2）
        selList = om2.MSelectionList()
        selList.add(mel.eval('findRelatedSkinCluster %s' % geometry))
        skinPath = selList.getDependNode(0)

        # 获取网格
        selList = om2.MSelectionList()
        selList.add(geometry)
        meshPath = selList.getDagPath(0)

        # 获取顶点权重
        fnSkinCluster = om2Anim.MFnSkinCluster(skinPath)
        fnVtxComp = om2.MFnSingleIndexedComponent()
        vtxComponents = fnVtxComp.create(om2.MFn.kMeshVertComponent)
        fnVtxComp.addElements(vtxID_Array)

        # 获取权重和影响数量
        dWeights, infCount = fnSkinCluster.getWeights(meshPath, vtxComponents)
        weights_Array = np.array(dWeights, dtype=npd_type)

        # 获取影响对象列表
        inf_Array = [dp.partialPathName() for dp in fnSkinCluster.influenceObjects()]

        # 压缩权重数据
        weightsNonZero_Array, infMap_Array, vertSplit_Array = self.compress_weightData(weights_Array, infCount)

        # 获取混合权重
        blendWeights_mArray = om.MDoubleArray()
        skin_mfn = get_skinCluster_mfn(skinCluster)
        if skin_mfn:
            skin_mfn.getBlendWeights(dagPath, components, blendWeights_mArray)
            blendWeights = [
                round(blendWeights_mArray[i], 6) for i in range(blendWeights_mArray.length())
                if round(blendWeights_mArray[i], 6) != 0.0
            ]
        else:
            blendWeights = []

        # 设置实例变量
        self.name = skinCluster
        self.weightsNonZero_Array = np.array(weightsNonZero_Array, dtype=npd_type)
        self.infMap_Array = np.array(infMap_Array, dtype=np.int32)
        self.vertSplit_Array = np.array(vertSplit_Array, dtype=np.int32)
        self.inf_Array = np.array(inf_Array)  # 字符串数组
        self.geometry = geometry
        self.blendWeights = np.array(blendWeights, dtype=npd_type) if blendWeights else np.array([], dtype=npd_type)
        self.vtxCount = len(vertSplit_Array) - 1

        # 获取蒙皮簇属性
        self.envelope = cmds.getAttr(skinCluster + ".envelope")
        self.skinningMethod = cmds.getAttr(skinCluster + ".skinningMethod")
        self.useComponents = cmds.getAttr(skinCluster + ".useComponents")
        self.normalizeWeights = cmds.getAttr(skinCluster + ".normalizeWeights")
        self.deformUserNormals = cmds.getAttr(skinCluster + ".deformUserNormals")

        return True

    def set_data(self, skinCluster):
        # 获取蒙皮簇组件
        try:
            fnSet = om.MFnSet(get_skinCluster_mfn(skinCluster).deformerSet())
            members = om.MSelectionList()
            fnSet.getMembers(members, False)
            dagPath = om.MDagPath()
            components = om.MObject()
            members.getDagPath(0, dagPath, components)
        except:
            dagPath, components = self.get_mesh_components_from_tag_expression(skinCluster)

        # 获取影响路径
        influencePaths = om.MDagPathArray()
        skin_mfn = get_skinCluster_mfn(skinCluster)
        if not skin_mfn:
            raise RuntimeError(f"Failed to get skin cluster MFn for {skinCluster}")

        infCount = skin_mfn.influenceObjects(influencePaths)
        influences_Array = [influencePaths[i].partialPathName() for i in range(influencePaths.length())]

        # 设置影响索引
        influenceIndices = om.MIntArray(infCount)
        [influenceIndices.set(i, i) for i in range(infCount)]

        # 重构权重数组
        infCount = len(influences_Array)
        weights_mArray = om.MDoubleArray()
        length = len(self.vertSplit_Array)

        for vtxId, splitStart in enumerate(self.vertSplit_Array):
            if vtxId < length - 1:
                vertChunk_Array = [0.0] * infCount
                splitEnd = self.vertSplit_Array[vtxId + 1]

                # 解包数据并替换非零权重值
                for i in range(splitStart, splitEnd):
                    infMap = self.infMap_Array[i]
                    val = self.weightsNonZero_Array[i]
                    if 0 <= infMap < infCount:  # 边界检查
                        vertChunk_Array[infMap] = val

                # 添加到权重数组
                for vert in vertChunk_Array:
                    weights_mArray.append(vert)

        # 设置权重
        skin_mfn.setWeights(dagPath, components, influenceIndices, weights_mArray, True)

        # 设置混合权重
        if self.blendWeights is not None and len(self.blendWeights) > 0:
            blendWeights_mArray = om.MDoubleArray()
            for i in self.blendWeights:
                blendWeights_mArray.append(i)
            skin_mfn.setBlendWeights(dagPath, components, blendWeights_mArray)

        # 设置蒙皮簇属性
        cmds.setAttr('%s.envelope' % skinCluster, self.envelope)
        cmds.setAttr('%s.skinningMethod' % skinCluster, self.skinningMethod)
        cmds.setAttr('%s.useComponents' % skinCluster, self.useComponents)
        cmds.setAttr('%s.normalizeWeights' % skinCluster, self.normalizeWeights)
        cmds.setAttr('%s.deformUserNormals' % skinCluster, self.deformUserNormals)

        # 重命名
        cmds.rename(skinCluster, self.geometry + "_skinCls")

    def save(self, node=None, file_path=None):
        # 获取选择的节点
        if node is None:
            node = cmds.ls(sl=1)
            if not node:
                print('ERROR: Select Something!')
                return False
            node = node[0]

        # 获取蒙皮簇
        skinCluster = str(getSkinCluster(node)) or ""
        print("save", skinCluster, node, "-------------")
        if not cmds.objExists(skinCluster):
            print('ERROR: Node has no skinCluster!')
            return False

        # 获取文件路径
        if file_path is None:
            startDir = cmds.workspace(q=True, rootDirectory=True)
            file_path = cmds.fileDialog2(caption='Save Skinweights', dialogStyle=2, fileMode=3,
                                         startingDirectory=startDir, fileFilter='*.npz', okCaption="Select")
            if not file_path:
                print("ERROR: No file path selected!")
                return False
            file_path = file_path[0]  # fileDialog2 返回列表

        # 获取蒙皮数据
        self.get_data(skinCluster)
        transformNode, meshNode = self._geometry_compatibility()
        self.geometry = transformNode
        if self.skinningMethod < 0:
            self.skinningMethod = 0

        # 保存数据（使用 np.savez 存储多个数组和元数据）
        try:
            # 分离数组和标量数据
            np.savez(
                file_path,
                weightsNonZero_Array=self.weightsNonZero_Array,
                vertSplit_Array=self.vertSplit_Array,
                infMap_Array=self.infMap_Array,
                inf_Array=self.inf_Array,
                blendWeights=self.blendWeights,
                # 标量数据转成数组存储
                vtxCount=np.array([self.vtxCount]),
                envelope=np.array([self.envelope]),
                skinningMethod=np.array([self.skinningMethod]),
                useComponents=np.array([self.useComponents]),
                normalizeWeights=np.array([self.normalizeWeights]),
                deformUserNormals=np.array([self.deformUserNormals]),
                # 字符串数据单独存储
                geometry=np.array([self.geometry], dtype='U'),
                name=np.array([self.name], dtype='U'),
                type=np.array([self.type], dtype='U')
            )
            print(f"Successfully saved skin data to: {file_path}")
            return True
        except Exception as e:
            print(f"ERROR saving file: {e}")
            return False

    def load(self, file_path=None, createMissingJoints=True):
        # 获取文件路径
        if file_path is None:
            startDir = cmds.workspace(q=True, rootDirectory=True)
            file_path = cmds.fileDialog2(caption='Load Skinweights', dialogStyle=2, fileMode=1,
                                         startingDirectory=startDir, fileFilter='*.npz', okCaption="Select")
            if not file_path:
                print("ERROR: No file path selected!")
                return False
            file_path = file_path[0]

        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f'ERROR: file {file_path} does not exist!')
            return False

        # 读取数据（适配新的 np.savez 格式）
        try:
            data = np.load(file_path, allow_pickle=True)
        except Exception as e:
            print(f"ERROR loading file: {e}")
            return False

        # 解析数据
        self.weightsNonZero_Array = data['weightsNonZero_Array']
        self.infMap_Array = data['infMap_Array']
        self.vertSplit_Array = data['vertSplit_Array']
        self.inf_Array = data['inf_Array']
        self.blendWeights = data['blendWeights']
        self.vtxCount = int(data['vtxCount'][0])
        self.geometry = data['geometry'][0]
        self.name = data['name'][0]
        self.envelope = float(data['envelope'][0])
        self.skinningMethod = int(data['skinningMethod'][0])
        self.useComponents = int(data['useComponents'][0])
        self.normalizeWeights = int(data['normalizeWeights'][0])
        self.deformUserNormals = int(data['deformUserNormals'][0])
        self.type = data['type'][0]

        # 检查几何体和顶点数量
        node = self.geometry
        transformNode, meshNode = self._geometry_compatibility()
        dataVertexCount = self.vtxCount
        nodeVertexCount = cmds.polyEvaluate(node, vertex=True)

        if dataVertexCount != nodeVertexCount:
            om.MGlobal.displayWarning(
                f'SKIPPED: vertex count mismatch! {dataVertexCount} != {nodeVertexCount}')
            return False

        # 解绑现有蒙皮簇
        skinCluster = mel.eval('findRelatedSkinCluster ' + node)
        if cmds.objExists(skinCluster):
            cmds.skinCluster(skinCluster, e=True, ub=True)

        # 检查缺失的关节
        missing_joints = [inf for inf in self.inf_Array if not cmds.objExists(inf)]
        if missing_joints:
            if createMissingJoints:
                if not cmds.objExists('missingJoints'):
                    grp = cmds.createNode("transform", n="missingJoints")
                else:
                    grp = 'missingJoints'
                for inf in missing_joints:
                    jnt = cmds.joint(n=inf)
                    cmds.parent(jnt, grp)
            else:
                om.MGlobal.displayError(f'ERROR: {missing_joints[0]} does not exist!')
                return False

        # 绑定新蒙皮
        skinCluster = cmds.skinCluster(self.inf_Array, node, n=self.geometry + "_skinCluster", tsb=True)[0]

        # 设置蒙皮数据
        self.set_data(skinCluster)
        print(f"Successfully loaded skin data to: {skinCluster}")
        return True

    def compress_weightData(self, weights_Array, infCount):
        # 转换为非零权重数组
        weightsNonZero_Array = []
        infCounter = 0
        infMap_Chunk = []
        infMap_ChunkCount = 0
        vertSplit_Array = [infMap_ChunkCount]
        infMap_Array = []

        for w in weights_Array:
            if abs(w) > 1e-9:  # 使用极小值代替 0.0，避免浮点精度问题
                weightsNonZero_Array.append(w)
                infMap_Chunk.append(infCounter)

            # 更新影响计数器
            infCounter += 1
            if infCounter == infCount:
                infCounter = 0

                # 更新顶点分割数组
                infMap_Array.extend(infMap_Chunk)
                infMap_ChunkCount = len(infMap_Chunk) + infMap_ChunkCount
                vertSplit_Array.append(infMap_ChunkCount)
                infMap_Chunk = []

        return weightsNonZero_Array, infMap_Array, vertSplit_Array

    def _geometry_compatibility(self):
        """ 兼容形状节点和变换节点 """
        meshData = self.geometry
        transformNode = None
        meshNode = None

        # 检查是否为网格节点
        if cmds.nodeType(meshData) == "mesh":
            transformNode = cmds.listRelatives(meshData, parent=True, fullPath=True)[0]
            meshNode = meshData
        # 检查是否为变换节点
        elif cmds.nodeType(meshData) == "transform":
            transformNode = meshData
            shapes = cmds.listRelatives(meshData, shapes=True, fullPath=True) or []
            for shape in shapes:
                if cmds.nodeType(shape) == "mesh":
                    meshNode = shape
                    break

        if not transformNode or not meshNode:
            raise RuntimeError(f"Failed to find compatible geometry for node: {meshData}")

        # 清理路径，只保留节点名
        transformNode = transformNode.split("|")[-1]
        return transformNode, meshNode


class DataIO(object):
    def __init__(self):
        pass

    @staticmethod
    def get_legendArrayFromData(data):
        return data.get('legend', [])

    @staticmethod
    def get_dataItem(data, item, legend_Array=None):
        if item not in data:
            print(f'ERROR: "{item}" Not Found in data!')
            return False
        return data[item]

    @staticmethod
    def set_dataItems(data, itemData_Array):
        return data
