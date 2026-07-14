"""平台自有的切片渲染（vendored from SimGraph2，纯标准 VTK）。

- openfoam_loader.load_openfoam：vtkOpenFOAMReader → 扁平 multiblock（无 Romtek）
- simagent_render.render_case：multiblock + 标量 → 多视角切片 PNG

OpenFOAM 算例完全自洽：仅需一个装了 VTK 的 python（平台基础环境即有 VTK 9.6+），
不再依赖 SimGraph2 仓库。Fluent 等需 Romtek 的格式仍走旧 PostEngine 回退（见 render_runner）。
"""
