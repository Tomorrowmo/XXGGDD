"""自然语言检索测试。"""
from app.services.search import parse_query, search


def test_parse_unit_and_op(seeded_db):
    conds = parse_query(seeded_db, "北航 Ma6-60kPa 的仿真")
    fields = {c["field"]: c["value"] for c in conds}
    assert fields.get("unit") == "北航"
    assert fields.get("kind") == "simulation"
    assert "Ma6" in (fields.get("op") or "")


def test_search_by_unit(seeded_db):
    res = search(seeded_db, "北航的算例")
    assert res["answer_type"] == "cases"
    assert all(c["unit"] == "北航" for c in res["results"])
    assert res["results"]


def test_search_overrange(seeded_db):
    res = search(seeded_db, "推力越界的算例有哪些")
    # 北航在 Ma6-60kPa 多量 >10% 偏差 → 命中
    units = {c["unit"] for c in res["results"]}
    assert "北航" in units
    assert "西工大" not in units


def test_search_ranking_intent(seeded_db):
    res = search(seeded_db, "哪家单位偏差最小")
    assert res["answer_type"] == "ranking"
    assert res["answer"][0]["unit"] == "西工大"


def test_search_experiment(seeded_db):
    res = search(seeded_db, "试车实验数据")
    assert all(c["kind"] == "experiment" for c in res["results"])
