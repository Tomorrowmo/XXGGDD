"""工况对齐测试：规范键推导 + auto/rule/manual + PENDING 兜底。"""
from app.services.operating_point import (
    canonical_key_from_params, canonical_key_from_name, align_case, assign_op_manual,
)
from app.db.models import (
    Unit, Delivery, Case, CaseKind, ParseStatus, Confidence, MapMethod,
)


def test_key_from_params():
    assert canonical_key_from_params({"Ma": 6.0, "dyn_pressure_kpa": 60}) == "Ma6-60kPa"
    assert canonical_key_from_params({"Ma": 6.0}) == "Ma6"
    assert canonical_key_from_params({}) is None


def test_key_from_name():
    assert canonical_key_from_name("Ma6-60kPa_run") == "Ma6-60kPa"
    assert canonical_key_from_name("case_Ma6_60k") == "Ma6-60kPa"
    assert canonical_key_from_name("case4") is None


def _make_case(db, name):
    u = Unit(name="西工大"); db.add(u); db.flush()
    d = Delivery(unit_id=u.id, label="Q1"); db.add(d); db.flush()
    c = Case(delivery_id=d.id, kind=CaseKind.SIMULATION, name=name,
             source_format="fluent-hdf5", storage_uri="x", content_hash="h_" + name,
             parse_status=ParseStatus.PARSED, parse_confidence=Confidence.HIGH)
    db.add(c); db.flush()
    return c


def test_align_auto_by_params(db):
    c = _make_case(db, "case4")
    link = align_case(db, c, {"Ma": 6.0, "dyn_pressure_kpa": 60})
    assert link.method == MapMethod.AUTO
    assert link.mapping_confidence == Confidence.HIGH
    assert link.op_id is not None


def test_align_rule_by_name(db):
    c = _make_case(db, "Ma6-60kPa_x")
    link = align_case(db, c, None)
    assert link.method == MapMethod.RULE
    assert link.mapping_confidence == Confidence.MED


def test_align_pending_fallback(db):
    c = _make_case(db, "case4")  # 无参数、名字无工况
    link = align_case(db, c, None)
    assert link.mapping_confidence == Confidence.PENDING


def test_manual_assign_upgrades(db):
    c = _make_case(db, "case4")
    link = align_case(db, c, None)
    assert link.mapping_confidence == Confidence.PENDING
    assign_op_manual(db, link, "Ma6-60kPa", {"Ma": 6.0, "dyn_pressure_kpa": 60}, "tester")
    assert link.method == MapMethod.MANUAL
    assert link.mapping_confidence == Confidence.HIGH
