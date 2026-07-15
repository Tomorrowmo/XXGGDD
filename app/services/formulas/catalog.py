"""公式目录（skills 注册表）—— 可扩展的公式清单，供 UI 展示 / 文档 / 查阅。

加新公式：在对应模块写纯函数后，往 CATALOG 追加一条（category/key/name/expr/
inputs/output/unit/reference/fn）。前端"配置/文档"或专业分析页可据此列出可用公式。
"""
from __future__ import annotations

from app.services.formulas import compressible, forces, averaging, flow, geometry, experiment

CATALOG = [
    # —— 可压缩流 ——
    {"category": "可压缩流", "key": "speed_of_sound", "name": "声速",
     "expr": "a = √(γp/ρ)", "inputs": ["p", "ρ", "γ"], "output": "a", "unit": "m/s",
     "reference": "Anderson, Modern Compressible Flow §3", "fn": compressible.speed_of_sound},
    {"category": "可压缩流", "key": "mach_number", "name": "马赫数",
     "expr": "M = |V|/a", "inputs": ["|V|", "p", "ρ", "γ"], "output": "M", "unit": "1",
     "reference": "Anderson §3", "fn": compressible.mach_number},
    {"category": "可压缩流", "key": "total_temperature", "name": "总温（滞止温度）",
     "expr": "T₀ = T(1 + (γ-1)/2·M²)", "inputs": ["T", "M", "γ"], "output": "T₀", "unit": "K",
     "reference": "等熵关系 Anderson §3.4", "fn": compressible.total_temperature},
    {"category": "可压缩流", "key": "total_pressure", "name": "总压（滞止压力）",
     "expr": "P₀ = p(1 + (γ-1)/2·M²)^(γ/(γ-1))", "inputs": ["p", "M", "γ"], "output": "P₀", "unit": "Pa",
     "reference": "等熵关系 Anderson §3.4", "fn": compressible.total_pressure},
    {"category": "可压缩流", "key": "dynamic_pressure", "name": "动压",
     "expr": "q = ½ρ|V|²", "inputs": ["ρ", "|V|"], "output": "q", "unit": "Pa",
     "reference": "空气动力学基础", "fn": compressible.dynamic_pressure},
    # —— 力 ——
    {"category": "力积分", "key": "pressure_force", "name": "壁面压力力",
     "expr": "F_p = Σ pᵢ(-nᵢ)Aᵢ", "inputs": ["p_face", "n_face", "A_face"], "output": "F_p", "unit": "N",
     "reference": "面力积分（外法向约定）", "fn": forces.pressure_force},
    {"category": "力积分", "key": "viscous_force", "name": "壁面黏性力",
     "expr": "F_v = Σ τᵢ", "inputs": ["τ_face"], "output": "F_v", "unit": "N",
     "reference": "壁面剪切积分", "fn": forces.viscous_force},
    {"category": "力积分", "key": "force_coefficient", "name": "力系数",
     "expr": "C = F/(½ρ∞V∞²A_ref)", "inputs": ["F", "ρ∞", "V∞", "A_ref"], "output": "C", "unit": "1",
     "reference": "无量纲化", "fn": forces.force_coefficient},
    # —— 几何 ——
    {"category": "几何", "key": "polygon_area_normal", "name": "多边形面积+法向（Newell）",
     "expr": "nv = ½Σ cross(vᵢ,vᵢ₊₁); A=|nv|; n=nv/A", "inputs": ["顶点(k,3)"],
     "output": "(A, n)", "unit": "m², 1", "reference": "Newell 法", "fn": geometry.polygon_area_normal},
    # —— 平均 ——
    {"category": "统计", "key": "slice_average", "name": "沿轴薄层面平均",
     "expr": "每层 mean(field | xᵢ-½h ≤ x ≤ xᵢ+½h)", "inputs": ["轴坐标", "字段", "n层"],
     "output": "沿程曲线", "unit": "—", "reference": "沿程分析", "fn": averaging.slice_average},
    {"category": "统计", "key": "area_weighted_average", "name": "面积加权平均",
     "expr": "Σ(fᵢAᵢ)/ΣAᵢ", "inputs": ["字段", "面积"], "output": "均值", "unit": "—",
     "reference": "面平均", "fn": averaging.area_weighted_average},
    {"category": "统计", "key": "mass_weighted_average", "name": "质量加权平均",
     "expr": "Σ(fᵢṁᵢ)/Σṁᵢ", "inputs": ["字段", "质量流"], "output": "均值", "unit": "—",
     "reference": "质量平均", "fn": averaging.mass_weighted_average},
    # —— 流量 ——
    {"category": "流量", "key": "mass_flow_general", "name": "质量流量（通用）",
     "expr": "ṁ = Σ ρᵢ(Vᵢ·nᵢ)Aᵢ", "inputs": ["ρ", "V", "n", "A"], "output": "ṁ", "unit": "kg/s",
     "reference": "质量守恒", "fn": flow.mass_flow_general},
    {"category": "流量", "key": "mass_flow_from_flux", "name": "质量流量（Fluent 通量）",
     "expr": "ṁ = -Σ φ", "inputs": ["SV_FLUX"], "output": "ṁ", "unit": "kg/s",
     "reference": "Fluent 通量约定", "fn": flow.mass_flow_from_flux},
    # —— 试验 ——
    {"category": "试验", "key": "atmos_correct", "name": "大气压修正",
     "expr": "p_abs = p_rel + p_atm", "inputs": ["p_rel", "p_atm"], "output": "p_abs", "unit": "MPa",
     "reference": "相对→绝对压力", "fn": experiment.atmos_correct},
    {"category": "试验", "key": "coefficient_of_variation", "name": "变异系数 CV",
     "expr": "CV = σ/|μ|", "inputs": ["样本"], "output": "CV", "unit": "1",
     "reference": "重复性核查", "fn": experiment.coefficient_of_variation},
    {"category": "对比", "key": "relative_deviation_pct", "name": "相对偏差",
     "expr": "(value-truth)/|truth|·100%", "inputs": ["value", "truth"], "output": "偏差%", "unit": "%",
     "reference": "多源对比评分", "fn": experiment.relative_deviation_pct},
]


def catalog_public() -> list[dict]:
    """去掉 fn（不可 JSON 化）的目录，供 API/前端。"""
    return [{k: v for k, v in item.items() if k != "fn"} for item in CATALOG]
