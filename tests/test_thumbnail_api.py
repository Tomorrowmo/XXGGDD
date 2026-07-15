"""列表缩略图端点测试 —— 仅返回已缓存切片，不触发渲染。"""
from pathlib import Path

from app.services import viz
from app.settings import settings


def _seed_sim_id(client) -> int:
    client.post("/api/v2/seed")
    cases = client.get("/api/v2/cases").json()["cases"]
    return next(c["id"] for c in cases if c["kind"] == "simulation")


def test_thumbnail_none_when_no_cache(client, monkeypatch, tmp_path):
    # 预览目录指向空 tmp → 无缓存 → available False（且不应渲染）
    monkeypatch.setattr(settings, "previews_dir", tmp_path)
    sid = _seed_sim_id(client)
    d = client.get(f"/api/v2/cases/{sid}/thumbnail").json()
    assert d["available"] is False


def test_thumbnail_experiment_rejected(client):
    client.post("/api/v2/seed")
    cases = client.get("/api/v2/cases").json()["cases"]
    eid = next(c["id"] for c in cases if c["kind"] == "experiment")
    d = client.get(f"/api/v2/cases/{eid}/thumbnail").json()
    assert d["available"] is False


def test_thumbnail_returns_cached(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "previews_dir", tmp_path)
    sid = _seed_sim_id(client)
    # 在该算例的标准预览目录放一张 surf_a.png，模拟已渲染缓存
    from app.db.database import SessionLocal
    from app.db.models import Case
    s = SessionLocal()
    uri = s.get(Case, sid).storage_uri
    s.close()
    pdir = viz.preview_dir(uri)
    (Path(pdir) / "surf_a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 50)
    d = client.get(f"/api/v2/cases/{sid}/thumbnail").json()
    assert d["available"] is True
    assert d["url"].endswith("surf_a.png")
    assert d["which"] == "surf_a"
