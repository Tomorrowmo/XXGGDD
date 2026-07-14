"""多源对比评分核心测试（纯函数）。"""
from app.services.compare import compare_operating_point, compare_result_to_dict, SourceValue as S


def _xf2_quantities():
    return [
        {"quantity": "流道22壁压峰值", "unit_dim": "MPa", "truth": 3.20,
         "sources": [S("西工大", "case4", 3.28), S("航天六院", "caseZ", 3.31), S("北航", "caseX", 3.55)]},
        {"quantity": "推力", "unit_dim": "kN", "truth": 48.5,
         "sources": [S("西工大", "case4", 47.9), S("航天六院", "caseZ", 47.2), S("北航", "caseX", 43.1)]},
    ]


def test_ranking_order():
    res = compare_operating_point("Ma6-60kPa", "试车03", _xf2_quantities())
    ranks = {r.unit: r.rank for r in res.ranking}
    assert ranks["西工大"] == 1
    assert ranks["北航"] == 3


def test_best_marked_per_row():
    res = compare_operating_point("Ma6-60kPa", "试车03", _xf2_quantities())
    row = res.rows[0]  # 流道22
    best = [s for s in row.sources if s["best"]]
    assert len(best) == 1
    assert best[0]["unit"] == "西工大"


def test_deviation_sign_and_value():
    res = compare_operating_point("Ma6-60kPa", "试车03", _xf2_quantities())
    row = res.rows[0]
    xg = next(s for s in row.sources if s["unit"] == "西工大")
    assert abs(xg["deviation_pct"] - 2.5) < 0.01  # (3.28-3.20)/3.20*100


def test_overrange_status():
    res = compare_operating_point("Ma6-60kPa", "试车03", _xf2_quantities())
    # 北航推力 -11% > 10% → 该行状态关注
    thrust = next(r for r in res.rows if r.quantity == "推力")
    assert thrust.status == "关注"


def test_serialization_shape():
    d = compare_result_to_dict(compare_operating_point("Ma6-60kPa", "试车03", _xf2_quantities()))
    assert "ranking" in d and "rows" in d
    assert d["ranking"][0]["rank"] == 1
    assert d["ranking"][0]["grade"].startswith("A")
