"""用户自定义算法 skills：安全表达式求值 + 增删/校验/真实算例试算。"""
import pytest

from app.services import algorithms as A
from app.settings import settings


# --------------------------------------------------------------- 安全求值
def test_safe_eval_math():
    assert A.safe_eval("2+3*4", {}) == 14.0
    assert A.safe_eval("thrust/mass_flow", {"thrust": 48.5, "mass_flow": 12.6}) == pytest.approx(48.5 / 12.6)
    assert A.safe_eval("sqrt(gamma*R*T)", {"gamma": 1.4, "R": 287.0, "T": 300.0}) == pytest.approx(347.19, abs=0.1)


def test_safe_eval_rejects_dangerous():
    for bad in ["__import__('os')", "a.b", "open('x')", "lambda: 1", "[1,2]", "x if y else z"]:
        with pytest.raises(A.ExprError):
            A.safe_eval(bad, {"a": 1, "x": 1, "y": 1, "z": 1})


def test_safe_eval_unknown_var_and_divzero():
    with pytest.raises(A.ExprError):
        A.safe_eval("foo+1", {})
    with pytest.raises(A.ExprError):
        A.safe_eval("1/0", {})


def test_expr_variables():
    assert A.expr_variables("F/(0.5*rho*V**2*A)") == ["A", "F", "V", "rho"]
    assert A.expr_variables("sqrt(gamma*R*T)") == ["R", "T", "gamma"]   # 函数名不算变量


# --------------------------------------------------------------- 存储 CRUD
def test_add_list_delete(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "algorithms_file", tmp_path / "algos.json")
    a = A.add_algorithm(name="比冲近似", expr="thrust*1000/(mass_flow*9.81)", unit="s")
    assert a["inputs"] == ["mass_flow", "thrust"]
    assert any(x["id"] == a["id"] for x in A.list_algorithms())
    assert A.delete_algorithm(a["id"]) is True
    assert A.list_algorithms() == []


def test_add_rejects_bad_expr(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "algorithms_file", tmp_path / "algos.json")
    with pytest.raises(A.ExprError):
        A.add_algorithm(name="坏", expr="__import__('os')")


def test_evaluate_missing_vars():
    r = A.evaluate("a+b", {"a": 1})
    assert r["ok"] is False and "b" in r["missing"]


# --------------------------------------------------------------- HTTP + 真实算例
def test_api_crud_and_eval_on_case(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "algorithms_file", tmp_path / "algos.json")
    client.post("/api/v2/seed")
    sim = next(c for c in client.get("/api/v2/cases").json()["cases"] if c["kind"] == "simulation")
    # 该算例可用变量（种子含 thrust/isp/chamber_p…）
    ctx = client.get(f"/api/v2/algorithms/case-context/{sim['id']}").json()
    names = [v["name"] for v in ctx["vars"]]
    assert "thrust" in names and "gamma" in names
    # 校验
    v = client.post("/api/v2/algorithms/validate", json={"expr": "thrust/chamber_p"}).json()
    assert v["ok"] is True
    # 新建
    a = client.post("/api/v2/algorithms", json={"name": "推力室压比", "expr": "thrust/chamber_p", "unit": ""}).json()
    assert a["id"]
    # 在真实算例上试算
    r = client.post("/api/v2/algorithms/eval", json={"expr": "thrust/chamber_p", "case_id": sim["id"]}).json()
    assert r["ok"] is True and r["value"] > 0
    # 坏表达式被拒
    bad = client.post("/api/v2/algorithms", json={"name": "x", "expr": "a.b"})
    assert bad.status_code == 400
    # 删除
    assert client.delete(f"/api/v2/algorithms/{a['id']}").json()["ok"] is True
