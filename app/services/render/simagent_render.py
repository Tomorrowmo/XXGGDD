# ⚑ Vendored from SimGraph2/simagent_render.py（本平台自有资产，纯标准 VTK，无 Romtek）。
#   独立进平台后，切片渲染不再依赖 SIMGRAPH2_ROOT 仓库。如上游有改进可手工同步。
"""聚焦弹体的多视角渲染（给 SimAgent 用）：相机拉近弹体、切片裁到近体区、颜色范围取近体值。

为什么单独写：SimGraph2 自带 preview_render 用"区块名关键字"找物体且相机框整个域，
对 piflow（区块名 Elem/tri、外流场很大）会渲成远场大盒子。这里改成：
  - 最小区块(点最少) = 弹体表面；最大区块 = 体网格；
  - 物面：渲弹体 tri 并按标量上色，相机等距框弹体；
  - 切片：切体网格 → 裁到弹体附近的盒子 → 相机正交拉近 → 颜色范围取近体；
  - 流线：在弹体上游撒种子，vtkStreamTracer，管线着色，相机框近体。
全程 vtk 离屏渲染（本环境已验证可用）。
"""
import os

import vtk

BODY_VIEW_FACTOR = 1.3   # 视野半高 = 弹体最大尺寸 × 该系数（越小越近）
RANGE_FACTOR = 1.2       # 取颜色范围的近体盒子 = 弹体尺寸 × 该系数


def _named_blocks(mb):
    out = []
    for i in range(mb.GetNumberOfBlocks()):
        b = mb.GetBlock(i)
        if b and b.GetNumberOfPoints() > 0:
            meta = mb.GetMetaData(i)
            name = meta.Get(vtk.vtkCompositeDataSet.NAME()) if (meta and meta.Has(vtk.vtkCompositeDataSet.NAME())) else f"blk{i}"
            out.append((name, b))
    return out


def _merge(blocks):
    ap = vtk.vtkAppendFilter()
    for _, b in blocks:
        ap.AddInputData(b)
    ap.Update()
    return ap.GetOutput()


def _surface(dataset):
    g = vtk.vtkGeometryFilter()
    g.SetInputData(dataset)
    g.Update()
    return g.GetOutput()


def _range_near_body(dataset, scalar, center, half):
    """近体盒子内该标量的数值范围（避免远场均匀值冲淡配色）。"""
    box = vtk.vtkBox()
    box.SetBounds(center[0] - half, center[0] + half, center[1] - half, center[1] + half, center[2] - half, center[2] + half)
    ext = vtk.vtkExtractGeometry()
    ext.SetImplicitFunction(box)
    ext.ExtractInsideOn()
    ext.SetInputData(dataset)
    ext.Update()
    out = ext.GetOutput()
    arr = out.GetPointData().GetArray(scalar) or out.GetCellData().GetArray(scalar)
    if arr and arr.GetNumberOfTuples() > 0:
        return arr.GetRange()
    arr = dataset.GetPointData().GetArray(scalar) or dataset.GetCellData().GetArray(scalar)
    return arr.GetRange() if arr else (0.0, 1.0)


def _lut():
    lut = vtk.vtkLookupTable()
    lut.SetHueRange(0.667, 0.0)  # 蓝→红
    lut.SetNumberOfColors(256)
    lut.Build()
    return lut


def _render(polydata, scalar, out_path, w, h, *, focal, half, normal=None, up=None,
            iso=False, srange=None, tube=False, cam_pos=None):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(polydata)
    have_scalar = False
    if scalar:
        arr = polydata.GetPointData().GetArray(scalar)
        use_point = arr is not None
        if arr is None:
            arr = polydata.GetCellData().GetArray(scalar)
        if arr:
            mapper.SetScalarModeToUsePointFieldData() if use_point else mapper.SetScalarModeToUseCellFieldData()
            mapper.SelectColorArray(scalar)
            mapper.SetScalarRange(srange or arr.GetRange())
            mapper.SetLookupTable(_lut())
            mapper.ScalarVisibilityOn()
            have_scalar = True
    if not have_scalar:
        mapper.ScalarVisibilityOff()

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    if not have_scalar:
        p = actor.GetProperty()
        p.SetColor(0.72, 0.78, 0.85); p.SetAmbient(0.35); p.SetDiffuse(0.8); p.SetSpecular(0.15)
        p.EdgeVisibilityOn(); p.SetEdgeColor(0.12, 0.12, 0.16)

    ren = vtk.vtkRenderer()
    ren.AddActor(actor)
    ren.SetBackground(0.09, 0.10, 0.14)
    if have_scalar:
        bar = vtk.vtkScalarBarActor()
        bar.SetLookupTable(mapper.GetLookupTable())
        bar.SetTitle(scalar)
        bar.SetNumberOfLabels(5)
        bar.SetMaximumWidthInPixels(70)
        ren.AddActor2D(bar)

    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetSize(w, h)
    win.AddRenderer(ren)

    cam = ren.GetActiveCamera()
    cam.SetFocalPoint(*focal)
    if iso:
        cp = cam_pos or (half * 2, -half * 2.5, half * 1.6)
        cam.SetPosition(focal[0] + cp[0], focal[1] + cp[1], focal[2] + cp[2])
        cam.SetViewUp(0, 0, 1)
        cam.ParallelProjectionOn()
    else:
        d = max(half * 6, 1.0)
        cam.SetPosition(focal[0] + normal[0] * d, focal[1] + normal[1] * d, focal[2] + normal[2] * d)
        cam.SetViewUp(*(up or [0, 0, 1]))
        cam.ParallelProjectionOn()
    cam.SetParallelScale(half)        # 视野半高 → 拉近到弹体附近
    ren.ResetCameraClippingRange()
    win.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.SetInputBufferTypeToRGB()
    w2i.ReadFrontBufferOff()
    w2i.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(out_path)
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()
    win.Finalize()


def render_cad_from_stl(stl_path, out_dir, w=600, h=460):
    """直接从 STL 渲 CAD 外形多视角（参数化CAD生成阶段即可，不必等网格）。"""
    reader = vtk.vtkSTLReader()
    reader.SetFileName(stl_path)
    reader.Update()
    surf = reader.GetOutput()
    if surf.GetNumberOfPoints() == 0:
        return []
    os.makedirs(out_dir, exist_ok=True)
    bb = surf.GetBounds()
    bc = [(bb[0] + bb[1]) / 2, (bb[2] + bb[3]) / 2, (bb[4] + bb[5]) / 2]
    bsize = max(bb[1] - bb[0], bb[3] - bb[2], bb[5] - bb[4]) or 1.0
    results = []
    angles = [("iso", "CAD·斜视", (bsize * 0.6, -bsize * 0.9, bsize * 0.5)),
              ("side", "CAD·侧视", (0.01, -bsize, 0.01)),
              ("top", "CAD·俯视", (0.01, 0.01, bsize))]
    for tag, label, cp in angles:
        p = os.path.join(out_dir, f"cad_{tag}.png")
        _render(surf, None, p, w, h, focal=bc, half=bsize * 0.62, iso=True, cam_pos=cp)
        results.append((label, p))
    return results


def render_case(multiblock, scalar, out_dir, w=760, h=520):
    """渲染聚焦弹体的多视角图，返回 [(label, path)]。"""
    blocks = _named_blocks(multiblock)
    if not blocks:
        return []
    os.makedirs(out_dir, exist_ok=True)
    vol_name, volume = max(blocks, key=lambda nb: nb[1].GetNumberOfPoints())  # 体网格=最大区块（场在其 cell 数据上）
    # 物面：外流用几何式隔离飞行器/弹体本体（排远场/对称面/体网格）；内流回退最小块表面
    surf = _isolate_body(blocks)
    if surf is None:
        _bn, body = min(blocks, key=lambda nb: nb[1].GetNumberOfPoints())
        surf = _surface(body)
    bb = surf.GetBounds()
    bc = [(bb[0] + bb[1]) / 2, (bb[2] + bb[3]) / 2, (bb[4] + bb[5]) / 2]
    bsize = max(bb[1] - bb[0], bb[3] - bb[2], bb[5] - bb[4]) or 1.0
    half = bsize * BODY_VIEW_FACTOR
    results = []

    # ① 物面云图（两视角；物面 Mach 近均匀，用 CoefPressure 更能体现压力分布）
    surf_scalar = scalar
    if (surf.GetPointData().GetArray("CoefPressure") or surf.GetCellData().GetArray("CoefPressure")):
        surf_scalar = "CoefPressure"
    # 稳健百分位范围优先（避免离群/远场均匀值把物面配成一片单色），退化时用近体范围
    srange = _robust_range(surf, surf_scalar) or _range_near_body(surf, surf_scalar, bc, bsize)
    for tag, cp in [("a", (half * 0.6, -half * 0.8, half * 0.45)), ("b", (0.01, 0.01, half))]:
        p = os.path.join(out_dir, f"surf_{tag}.png")
        _render(surf, surf_scalar, p, w, h, focal=bc, half=bsize * 0.85, iso=True, srange=srange, cam_pos=cp)
        results.append((f"物面云图·{'斜视' if tag == 'a' else '俯视'}", p))

    # ② 三向切片（直接渲剖切结果保留 Mach，相机拉近裁到近体，颜色范围取近体值）
    nu = [("X", [1, 0, 0], [0, 0, 1]), ("Y", [0, 1, 0], [0, 0, 1]), ("Z", [0, 0, 1], [0, 1, 0])]
    for ax, normal, up in nu:
        plane = vtk.vtkPlane(); plane.SetOrigin(*bc); plane.SetNormal(*normal)
        cutter = vtk.vtkCutter(); cutter.SetCutFunction(plane); cutter.SetInputData(volume); cutter.Update()
        sl = cutter.GetOutput()
        srange = _range_near_body(sl, scalar, bc, half)
        p = os.path.join(out_dir, f"slice_{ax}.png")
        _render(sl, scalar, p, w, h, focal=bc, half=half, normal=normal, up=up, srange=srange)
        results.append((f"Mach 切片 {ax}", p))

    # ③ 流线（体网格 cell→point 转速度场，弹体上游沿来流撒种子）
    try:
        c2p = vtk.vtkCellDataToPointData(); c2p.SetInputData(volume); c2p.Update()
        vdata = c2p.GetOutput()
        if vdata.GetPointData().GetArray("VelocityX") is not None:
            calc = vtk.vtkArrayCalculator(); calc.SetInputData(vdata)
            calc.AddScalarArrayName("VelocityX"); calc.AddScalarArrayName("VelocityY"); calc.AddScalarArrayName("VelocityZ")
            calc.SetFunction("VelocityX*iHat + VelocityY*jHat + VelocityZ*kHat")
            calc.SetResultArrayName("Vel"); calc.Update()
            vv = calc.GetOutput(); vv.GetPointData().SetActiveVectors("Vel")
            # 主流方向按弹体长轴（X）；种子线放在头部上游、竖向铺开
            seed = vtk.vtkLineSource()
            seed.SetPoint1(bb[0] - bsize * 0.3, bc[1], bc[2] - bsize * 0.5)
            seed.SetPoint2(bb[0] - bsize * 0.3, bc[1], bc[2] + bsize * 0.5)
            seed.SetResolution(30)
            tracer = vtk.vtkStreamTracer()
            tracer.SetInputData(vv); tracer.SetSourceConnection(seed.GetOutputPort())
            tracer.SetIntegrationDirectionToBoth()
            tracer.SetMaximumPropagation(bsize * 6)
            tracer.SetInitialIntegrationStep(bsize * 0.02)
            tracer.SetMaximumNumberOfSteps(4000)
            tracer.Update()
            tube = vtk.vtkTubeFilter(); tube.SetInputConnection(tracer.GetOutputPort())
            tube.SetRadius(bsize * 0.008); tube.SetNumberOfSides(6); tube.Update()
            out = tube.GetOutput()
            if out.GetNumberOfPoints() > 0:
                # 叠加半透明弹体做参照
                body_surf = _surface(body)
                p = os.path.join(out_dir, "streamline.png")
                _render_with_body(out, body_surf, scalar, p, w, h, focal=bc, half=half * 1.4)
                results.append(("流线", p))
    except Exception:
        pass

    return results


def _render_with_body(streamtube, body_surf, scalar, out_path, w, h, *, focal, half):
    """流线管(按标量上色) + 半透明弹体参照，斜视。"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    smap = vtk.vtkPolyDataMapper(); smap.SetInputData(streamtube)
    arr = streamtube.GetPointData().GetArray(scalar)
    if arr:
        smap.SetScalarModeToUsePointFieldData(); smap.SelectColorArray(scalar)
        smap.SetScalarRange(arr.GetRange()); smap.SetLookupTable(_lut()); smap.ScalarVisibilityOn()
    sact = vtk.vtkActor(); sact.SetMapper(smap)
    bmap = vtk.vtkPolyDataMapper(); bmap.SetInputData(body_surf); bmap.ScalarVisibilityOff()
    bact = vtk.vtkActor(); bact.SetMapper(bmap)
    bp = bact.GetProperty(); bp.SetColor(0.55, 0.6, 0.7); bp.SetOpacity(0.35)
    ren = vtk.vtkRenderer(); ren.AddActor(sact); ren.AddActor(bact); ren.SetBackground(0.09, 0.10, 0.14)
    if arr:
        bar = vtk.vtkScalarBarActor(); bar.SetLookupTable(smap.GetLookupTable()); bar.SetTitle(scalar)
        bar.SetNumberOfLabels(5); bar.SetMaximumWidthInPixels(70); ren.AddActor2D(bar)
    win = vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.SetSize(w, h); win.AddRenderer(ren)
    cam = ren.GetActiveCamera(); cam.SetFocalPoint(*focal)
    cam.SetPosition(focal[0] + half * 0.4, focal[1] - half * 2.2, focal[2] + half * 1.0)
    cam.SetViewUp(0, 0, 1); cam.ParallelProjectionOn(); cam.SetParallelScale(half)
    ren.ResetCameraClippingRange(); win.Render()
    w2i = vtk.vtkWindowToImageFilter(); w2i.SetInput(win); w2i.SetInputBufferTypeToRGB(); w2i.ReadFrontBufferOff(); w2i.Update()
    writer = vtk.vtkPNGWriter(); writer.SetFileName(out_path); writer.SetInputConnection(w2i.GetOutputPort()); writer.Write()
    win.Finalize()


# --------------------------------------------------------------------------- 缩略图（能看出是什么模型）
_BODY_HINT = ("wall", "solid", "body", "aircraft", "missile", "wing", "blade",
              "hull", "skin", "surface", "geom")
_FAR_HINT = ("far", "freestream", "inlet", "outlet", "internal", "interior",
             "volume", "fluid", "domain", "symmetry", "elem", "background")


def _domain_bounds(blocks):
    """所有块并集的包围盒。"""
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    any_ = False
    for _, b in blocks:
        if b.GetNumberOfPoints() == 0:
            continue
        bb = b.GetBounds()
        for a in range(3):
            lo[a] = min(lo[a], bb[2 * a]); hi[a] = max(hi[a], bb[2 * a + 1])
        any_ = True
    if not any_:
        return None
    return (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])


def _maxdim(bb):
    return max(bb[1] - bb[0], bb[3] - bb[2], bb[5] - bb[4])


def _is_volume_block(b, sample=25):
    """体网格块（含 3D 单元：四面体/六面体/棱柱/金字塔…）。纯面块只有 2D 单元。"""
    n = b.GetNumberOfCells()
    if n == 0:
        return False
    vol3d = {10, 11, 12, 13, 14, 24, 25, 26, 29}  # tetra/voxel/hexa/wedge/pyramid/…（二次单元）
    step = max(1, n // sample)
    for i in range(0, n, step):
        if b.GetCellType(i) in vol3d:
            return True
    return False


def _isolate_body(blocks, compact_frac=0.3, planar_frac=0.15):
    """外流：隔离飞行器/弹体**本体面**（紧凑面块），排除跨域远场/对称面与体网格。

    判据（几何式，不靠块名/单元数——外流 CGNS 常按单元类型 Elem_* 命名，语义名失效）：
      - 体网格块（含 3D 单元）→ 排除；
      - 面块"包围盒最大边 ≥ compact_frac×整域最大边"→ 跨域远场，排除；
      - 面块**近平面**（最小边≈0）且"最大边 ≥ planar_frac×整域"→ 对称面/远场平面，排除；
      - 其余紧凑面块 = 本体 + 舵面/翼 → 合并提表面。
    仅当"既有紧凑面块、又有跨域块（远场/对称面/体网格）"才判为外流并隔离；否则返回 None，
    交调用方回退整域行为（内流：燃烧室/流道，整域即关心区）。
    """
    dom = _domain_bounds(blocks)
    if dom is None:
        return None
    dmax = _maxdim(dom)
    if dmax <= 0:
        return None
    compact, has_spanning = [], False
    for name, b in blocks:
        if b.GetNumberOfPoints() == 0:
            continue
        if _is_volume_block(b):
            has_spanning = True
            continue
        bb = b.GetBounds()
        dims = sorted([bb[1] - bb[0], bb[3] - bb[2], bb[5] - bb[4]])
        mx = dims[2]
        planar = mx > 0 and dims[0] < 0.02 * mx
        if mx >= compact_frac * dmax or (planar and mx >= planar_frac * dmax):
            has_spanning = True          # 跨域远场 / 对称面 / 远场平面
            continue
        compact.append((name, b))
    if not compact or not has_spanning:
        return None                      # 内流或无远场 → 不隔离
    ap = vtk.vtkAppendFilter()
    for _, b in compact:
        ap.AddInputData(b)
    ap.Update()
    surf = _surface(ap.GetOutput())
    # 防误判：内流的小进出口 patch 也会是"紧凑面块"。要求隔离出的本体足够**大且三维**，
    # 否则判为内流回退整域（避免把 DLR 燃烧室的小 inlet patch 当成"弹体"）。
    if surf.GetNumberOfPoints() < 200:
        return None
    bb = surf.GetBounds()
    dims = sorted([bb[1] - bb[0], bb[3] - bb[2], bb[5] - bb[4]])
    if dims[2] <= 0 or dims[0] < 0.01 * dims[2]:   # 退化/平面 → 非三维本体
        return None
    return surf


def _robust_range(dataset, scalar, lo=2.0, hi=98.0, sample=6000):
    """标量的百分位稳健范围，避免离群/远场均匀值把云图配色冲成一片单色。"""
    arr = (dataset.GetPointData().GetArray(scalar)
           or dataset.GetCellData().GetArray(scalar))
    if arr is None:
        return None
    n = arr.GetNumberOfTuples()
    if n == 0:
        return None
    step = max(1, n // sample)
    vals = []
    for i in range(0, n, step):
        v = arr.GetComponent(i, 0)
        if v == v:                       # 排除 NaN
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    m = len(vals)

    def pct(p):
        k = (m - 1) * p / 100.0
        f = int(k)
        c = min(f + 1, m - 1)
        return vals[f] + (vals[c] - vals[f]) * (k - f)

    r0, r1 = pct(lo), pct(hi)
    if r1 <= r0:
        r0, r1 = vals[0], vals[-1]
    return (r0, r1) if r1 > r0 else None


def _pick_body_surface(blocks):
    """挑最能代表模型的表面。

    - 有明确"物面"命名(wall/solid/body…)：取其中**面片最多**者（主壁面/主体，
      如燃烧室取整段壁面而非细小进出口环）；
    - 无命名线索：取**最紧凑**(包围盒最小)的非远场块（外流场里的弹体，如导弹）。
    远场/体网格(far/internal/elem…)一律排除。"""
    cands = []
    for name, b in blocks:
        surf = _surface(b)
        n = surf.GetNumberOfPoints()
        if n < 30:
            continue
        bb = surf.GetBounds()
        diag = ((bb[1] - bb[0]) ** 2 + (bb[3] - bb[2]) ** 2 + (bb[5] - bb[4]) ** 2) ** 0.5
        low = (name or "").lower()
        cands.append({"surf": surf, "n": n, "cells": surf.GetNumberOfCells(), "diag": diag,
                      "body": any(h in low for h in _BODY_HINT),
                      "far": any(h in low for h in _FAR_HINT)})
    if not cands:
        return None
    named = [c for c in cands if c["body"] and not c["far"]]
    if named:                                   # 有物面命名 → 取面最多的主壁面
        named.sort(key=lambda c: -c["cells"])
        return named[0]["surf"]
    pool = [c for c in cands if not c["far"]] or cands   # 无命名 → 取最紧凑的非远场块
    pool.sort(key=lambda c: (round(c["diag"], 3), c["n"]))
    return pool[0]["surf"]


def render_thumbnail(multiblock, out_path, w=384, h=384):
    """生成一张"能认出模型外形"的缩略图：隔离弹体表面 → 明暗着色 → 3/4 视角紧凑取景。

    方形输出，供列表 54px 方形缩略图无损裁切。返回是否成功。
    """
    blocks = _named_blocks(multiblock)
    if not blocks:
        return False
    body = _isolate_body(blocks) or _pick_body_surface(blocks)
    if body is None or body.GetNumberOfPoints() == 0:
        return False
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    norm = vtk.vtkPolyDataNormals()
    norm.SetInputData(body)
    norm.SetFeatureAngle(60)
    norm.SplittingOff()
    norm.ConsistencyOn()
    norm.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(norm.GetOutput())
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    p = actor.GetProperty()
    p.SetColor(0.62, 0.74, 0.94)
    p.SetAmbient(0.30); p.SetDiffuse(0.85); p.SetSpecular(0.30); p.SetSpecularPower(24)

    ren = vtk.vtkRenderer()
    ren.AddActor(actor)
    ren.GradientBackgroundOn()
    ren.SetBackground(0.055, 0.065, 0.095)   # 底部深
    ren.SetBackground2(0.13, 0.15, 0.21)     # 顶部亮（微渐变，更有质感）

    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetSize(w, h)
    win.AddRenderer(ren)

    cam = ren.GetActiveCamera()
    cam.SetViewUp(0, 0, 1)
    ren.ResetCamera()                        # 紧贴模型取景
    cam.Azimuth(-45)
    cam.Elevation(20)
    ren.ResetCameraClippingRange()
    cam.Zoom(1.4)
    win.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.SetInputBufferTypeToRGB()
    w2i.ReadFrontBufferOff()
    w2i.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(out_path)
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()
    win.Finalize()
    return True


def _body_actor_renderer(body):
    """公用：物面 → (renderer, window, camera) 明暗着色 + 渐变背景。"""
    norm = vtk.vtkPolyDataNormals()
    norm.SetInputData(body); norm.SetFeatureAngle(60); norm.SplittingOff(); norm.ConsistencyOn(); norm.Update()
    mapper = vtk.vtkPolyDataMapper(); mapper.SetInputData(norm.GetOutput()); mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor(); actor.SetMapper(mapper)
    p = actor.GetProperty()
    p.SetColor(0.62, 0.74, 0.94); p.SetAmbient(0.30); p.SetDiffuse(0.85); p.SetSpecular(0.30); p.SetSpecularPower(24)
    ren = vtk.vtkRenderer(); ren.AddActor(actor)
    ren.GradientBackgroundOn(); ren.SetBackground(0.055, 0.065, 0.095); ren.SetBackground2(0.13, 0.15, 0.21)
    return ren


def render_turntable(multiblock, out_dir, n_frames: int = 24, w: int = 440, h: int = 440) -> int:
    """绕竖轴渲染 n 帧（turn_00.png … turn_{n-1}.png），供前端拖拽轨道旋转。返回帧数。"""
    blocks = _named_blocks(multiblock)
    if not blocks:
        return 0
    body = _isolate_body(blocks) or _pick_body_surface(blocks)
    if body is None or body.GetNumberOfPoints() == 0:
        return 0
    os.makedirs(out_dir, exist_ok=True)
    ren = _body_actor_renderer(body)
    win = vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.SetSize(w, h); win.AddRenderer(ren)
    cam = ren.GetActiveCamera(); cam.SetViewUp(0, 0, 1)
    ren.ResetCamera(); cam.Elevation(18); ren.ResetCameraClippingRange(); cam.Zoom(1.25)
    step = 360.0 / max(n_frames, 1)
    count = 0
    for i in range(n_frames):
        ren.ResetCameraClippingRange()
        win.Render()
        w2i = vtk.vtkWindowToImageFilter(); w2i.SetInput(win); w2i.SetInputBufferTypeToRGB(); w2i.ReadFrontBufferOff(); w2i.Update()
        writer = vtk.vtkPNGWriter(); writer.SetFileName(os.path.join(out_dir, "turn_%02d.png" % i))
        writer.SetInputConnection(w2i.GetOutputPort()); writer.Write()
        count += 1
        cam.Azimuth(step)
    win.Finalize()
    return count
