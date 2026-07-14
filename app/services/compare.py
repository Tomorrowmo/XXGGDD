"""多源对比与评分 —— 平台评判层的核心（对齐 docs/02 §5、原型对比评估页）。

纯计算核心（不依赖 DB，便于测试）：给定一组各单位测量 + 实验真值，
产出 逐物理量偏差表 + 各单位平均偏差 + 评级 + 排名。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.criteria import grade_from_avg_deviation, tier_from_deviation


@dataclass
class SourceValue:
    unit: str            # 单位（西工大/北航/…）
    case: str            # 算例名
    value: float


@dataclass
class QuantityRow:
    quantity: str
    unit_dim: str                       # 量纲
    truth: float
    sources: list[dict] = field(default_factory=list)   # [{unit, case, value, deviation_pct, tier, best}]
    status: str = "正常"                # 正常 / 关注（有源越界）


@dataclass
class UnitRank:
    unit: str
    case: str
    avg_deviation: float
    n_pass: int
    n_total: int
    grade: str
    rank: int = 0


@dataclass
class CompareResult:
    operating_point: str
    truth_source: str
    rows: list[QuantityRow]
    ranking: list[UnitRank]


def _deviation_pct(value: float, truth: float) -> float:
    if truth == 0:
        return 0.0
    return (value - truth) / abs(truth) * 100.0


def compare_operating_point(
    op_key: str,
    truth_source: str,
    quantities: list[dict],
) -> CompareResult:
    """对比一个工况点。

    quantities: [
        {"quantity": "流道22壁压峰值", "unit_dim": "MPa", "truth": 3.20,
         "sources": [SourceValue(...), ...]},
        ...
    ]
    """
    rows: list[QuantityRow] = []
    # 累积每单位的绝对偏差用于评级
    unit_devs: dict[str, list[float]] = {}
    unit_case: dict[str, str] = {}
    unit_pass: dict[str, int] = {}
    unit_total: dict[str, int] = {}

    for q in quantities:
        truth = q["truth"]
        srcs = q["sources"]
        row = QuantityRow(quantity=q["quantity"], unit_dim=q.get("unit_dim", ""), truth=truth)
        # 计算各源偏差
        best_unit, best_abs = None, None
        row_has_overrange = False
        for s in srcs:
            dev = _deviation_pct(s.value, truth)
            adev = abs(dev)
            tier = tier_from_deviation(adev)
            if adev > 10.0:
                row_has_overrange = True
            row.sources.append({
                "unit": s.unit, "case": s.case, "value": s.value,
                "deviation_pct": round(dev, 2), "tier": tier, "best": False,
            })
            unit_devs.setdefault(s.unit, []).append(adev)
            unit_case[s.unit] = s.case
            unit_total[s.unit] = unit_total.get(s.unit, 0) + 1
            if tier in ("优秀", "合格"):
                unit_pass[s.unit] = unit_pass.get(s.unit, 0) + 1
            if best_abs is None or adev < best_abs:
                best_abs, best_unit = adev, s.unit
        # 标记最接近真值者
        for sr in row.sources:
            if sr["unit"] == best_unit:
                sr["best"] = True
        row.status = "关注" if row_has_overrange else "正常"
        rows.append(row)

    # 各单位评级 + 排名
    ranking: list[UnitRank] = []
    for unit, devs in unit_devs.items():
        avg = sum(devs) / len(devs) if devs else 0.0
        total = unit_total.get(unit, 0)
        npass = unit_pass.get(unit, 0)
        grade = grade_from_avg_deviation(avg, all_qoi_pass=(npass == total))
        ranking.append(UnitRank(unit=unit, case=unit_case.get(unit, ""),
                                avg_deviation=round(avg, 2), n_pass=npass,
                                n_total=total, grade=grade))
    ranking.sort(key=lambda r: r.avg_deviation)
    for i, r in enumerate(ranking, 1):
        r.rank = i

    return CompareResult(operating_point=op_key, truth_source=truth_source,
                         rows=rows, ranking=ranking)


def compare_result_to_dict(res: CompareResult) -> dict:
    """序列化为前端可用结构。"""
    return {
        "operating_point": res.operating_point,
        "truth_source": res.truth_source,
        "rows": [
            {"quantity": r.quantity, "unit_dim": r.unit_dim, "truth": r.truth,
             "status": r.status, "sources": r.sources}
            for r in res.rows
        ],
        "ranking": [
            {"rank": r.rank, "unit": r.unit, "case": r.case,
             "avg_deviation": r.avg_deviation, "n_pass": r.n_pass,
             "n_total": r.n_total, "grade": r.grade}
            for r in res.ranking
        ],
    }
