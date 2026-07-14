"""评估编排测试：seed → 装配对比 → 生成报告。"""
from app.services.evaluation import assemble_compare, build_report
from app.services.compare import compare_result_to_dict


def test_seed_then_compare(seeded_db):
    res = assemble_compare(seeded_db, "Ma6-60kPa")
    assert res is not None
    d = compare_result_to_dict(res)
    # 三家仿真 + 8 物理量
    assert len(d["ranking"]) == 3
    assert len(d["rows"]) == 8
    # 西工大第一
    assert d["ranking"][0]["unit"] == "西工大"
    assert d["ranking"][0]["rank"] == 1
    # 北航垫底
    assert d["ranking"][-1]["unit"] == "北航"


def test_avg_deviation_reasonable(seeded_db):
    d = compare_result_to_dict(assemble_compare(seeded_db, "Ma6-60kPa"))
    xg = next(r for r in d["ranking"] if r["unit"] == "西工大")
    bh = next(r for r in d["ranking"] if r["unit"] == "北航")
    assert xg["avg_deviation"] < 2.0
    assert bh["avg_deviation"] > 8.0


def test_build_report(seeded_db):
    rep = build_report(seeded_db, "Ma6-60kPa", engine_name="XF-2")
    assert rep["ok"]
    assert "XF-2" in rep["title"]
    assert "评估范围" in rep["sections"]
    assert len(rep["sections"]["各物理量偏差"]) == 8
    assert "西工大" in rep["sections"]["评级与建议"]


def test_compare_missing_op(db):
    # 空库、不存在的工况
    assert assemble_compare(db, "Ma9-99kPa") is None
