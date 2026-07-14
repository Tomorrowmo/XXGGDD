"""评估 agent 的工具集 —— 薄封装，委托给服务层，带 harness 路径安全拦截。

分工：agent（渊/析）做单对象**专业判断**；多源对比/评分是确定性的，由 router 直接算，
不进 agent 工具（避免让 LLM 做算术），故这里只暴露"取数 + 判据 + 可视化"类工具。
"""
from __future__ import annotations

import json
from functools import wraps

try:
    from langchain_core.tools import tool
except ImportError:  # 无 langchain 时提供 no-op 装饰器，保证模块可导入
    def tool(fn=None, **_):  # type: ignore
        return fn if callable(fn) else (lambda f: f)

from app.services import simparse_adapter, viz
from app.services import experiment as exp_svc
from app.services import criteria as crit_svc
from app.agents.harness import assert_safe_path, HarnessError


def guard_path(fn):
    """前置校验第一个路径参数在白名单内（防遍历）。"""
    @wraps(fn)
    def w(*a, **k):
        p = a[0] if a else (k.get("case_path") or k.get("file_path"))
        if p:
            try:
                assert_safe_path(p)
            except HarnessError as e:
                return json.dumps({"error": str(e)}, ensure_ascii=False)
        return fn(*a, **k)
    return w


@tool
@guard_path
def get_case_summary(case_path: str) -> str:
    """获取仿真算例概况（格式/求解器/网格量/变量数），来自 simparse。传入算例路径。"""
    return json.dumps(simparse_adapter.summary(case_path), ensure_ascii=False)


@tool
@guard_path
def get_convergence(case_path: str) -> str:
    """获取仿真算例的收敛/残差信息（每变量收敛阶数与状态），来自 simparse。"""
    return json.dumps(simparse_adapter.convergence(case_path), ensure_ascii=False)


@tool
@guard_path
def get_qoi(case_path: str) -> str:
    """获取仿真算例的 QOI 长表（关注量的值/状态/置信度/证据/文献），来自 simparse。"""
    return json.dumps(simparse_adapter.qoi(case_path), ensure_ascii=False)


@tool
@guard_path
def get_field_stats(case_path: str) -> str:
    """获取仿真算例各变量原始统计（min/max/mean），来自 simparse。"""
    return json.dumps(simparse_adapter.field_stats(case_path), ensure_ascii=False)


@tool
@guard_path
def get_mesh_zones(case_path: str) -> str:
    """获取仿真算例网格 zone 信息（网格量/y+/单元类型），来自 simparse。"""
    return json.dumps(simparse_adapter.mesh_zones(case_path), ensure_ascii=False)


@tool
@guard_path
def analyze_experiment(file_path: str) -> str:
    """解析并诊断一份热试车数据：返回通道统计、阶段分割、稳态段关键量（真值候选）、异常判据命中。
    传入试验 TXT/CSV 路径。"""
    parsed = exp_svc.read_experiment(file_path)
    stats = exp_svc.compute_stats(parsed)
    phases = exp_svc.segment_phases(parsed)
    steady_qoi = exp_svc.extract_steady_qoi(parsed, phases)
    anomalies = [a.__dict__ for a in crit_svc.check_experiment_anomalies(stats)]
    return json.dumps({
        "n_rows": parsed.n_rows, "channels": len(parsed.channels), "stats": stats,
        "phases": phases.__dict__, "steady_qoi": steady_qoi, "anomalies": anomalies,
    }, ensure_ascii=False)


@tool
def list_criteria_domains() -> str:
    """列出 sim-knowledge 判据库里可用的物理域（用于查判据）。"""
    return json.dumps(crit_svc.list_available_domains(), ensure_ascii=False)


@tool
def get_domain_criteria(domain: str) -> str:
    """读取某物理域的护城河判据（criteria.yaml）。传入域名，如 numerics / aerodynamics / combustion。"""
    return json.dumps(crit_svc.load_domain_criteria(domain), ensure_ascii=False)


@tool
@guard_path
def generate_case_previews(case_path: str, scalar: str = "Pressure") -> str:
    """为仿真算例生成四张切片快照（surface/xy/xz/yz），返回图片路径。传入算例路径。"""
    return json.dumps(viz.generate_previews(case_path, scalar), ensure_ascii=False)


ALL_TOOLS = [
    get_case_summary, get_convergence, get_qoi, get_field_stats, get_mesh_zones,
    analyze_experiment, list_criteria_domains, get_domain_criteria, generate_case_previews,
]
YUAN_TOOLS = [get_case_summary, get_convergence, get_qoi, get_field_stats, get_mesh_zones,
              list_criteria_domains, get_domain_criteria]
XI_TOOLS = [analyze_experiment, list_criteria_domains, get_domain_criteria]
