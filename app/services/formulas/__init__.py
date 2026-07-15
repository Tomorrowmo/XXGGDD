"""物理计算公式库（"skills"）—— 从原 QJZ_fluent_post / plotter 提取的纯计算公式。

设计目标（老板要求）：把散落在各处、与 Fluent HDF5 读写耦合的**计算公式**抽成
**纯函数库**（numpy 数组进 → 物理量出，不碰任何 I/O），使其：
  1. 数据源无关：Fluent HDF5 / OpenFOAM VTK / CGNS 都能复用同一套公式；
  2. 可测试：每条公式有解析算例单测；
  3. 可扩展：加新公式只需在对应模块加函数并登记进 CATALOG。

模块划分：
  - compressible.py  可压缩流：声速 / 马赫 / 总温 / 总压 / 动压
  - geometry.py      几何：多边形面积+法向（Newell 法）
  - forces.py        力：壁面压力力 / 黏性力 / 合力 / 力系数
  - averaging.py     统计：沿轴薄层面平均 / 面积加权平均
  - flow.py          流量：质量流量（通量法 / ρV·nA 法）/ 边界均值
  - experiment.py    试验：相对压力→绝对压力（大气修正）

物理常数 γ、R 默认取 app.settings.physics（已统一），可按算例覆盖。
公式来源与文献见各函数 docstring 及 CATALOG。
"""
from __future__ import annotations

from app.services.formulas import (  # noqa: F401
    compressible, geometry, forces, averaging, flow, experiment,
)
from app.services.formulas.catalog import CATALOG  # noqa: F401

__all__ = ["compressible", "geometry", "forces", "averaging", "flow",
           "experiment", "CATALOG"]
