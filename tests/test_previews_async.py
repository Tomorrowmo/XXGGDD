"""切片预览非阻塞：已缓存直接给 URL、环境不可用即时返回——面板加载不被渲染阻塞。"""
from pathlib import Path

from app.services import viz
from app.settings import settings


def _seed_sim_uri(client):
    client.post("/api/v2/seed")
    cases = client.get("/api/v2/cases").json()["cases"]
    sid = next(c["id"] for c in cases if c["kind"] == "simulation")
    from app.db.database import SessionLocal
    from app.db.models import Case
    s = SessionLocal()
    uri = s.get(Case, sid).storage_uri
    s.close()
    return sid, uri


def test_previews_status_and_endpoint_return_cached(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "previews_dir", tmp_path)
    sid, uri = _seed_sim_uri(client)
    pdir = Path(viz.preview_dir(uri))
    for n in ("slice_X", "slice_Y", "slice_Z", "surf_a", "surf_b"):
        (pdir / f"{n}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    # 已缓存 → status / start_previews 立即 available，urls 齐全，不触发渲染
    st = viz.previews_status(uri)
    assert st["available"] is True and st["rendering"] is False and len(st["urls"]) == 5
    st2 = viz.start_previews(uri)
    assert st2["available"] is True
    # /previews 端点也非阻塞返回缓存 urls
    d = client.get(f"/api/v2/cases/{sid}/previews").json()
    assert d["available"] is True and len(d.get("urls", {})) == 5


def test_start_previews_env_unavailable_returns_immediately(monkeypatch, tmp_path):
    # 无缓存 + 需 Romtek 的格式但环境不可用 → 立即返回（不阻塞、不起渲染线程）
    monkeypatch.setattr(settings, "previews_dir", tmp_path)
    monkeypatch.setattr(viz.settings.assets, "postprocess_python", Path("/nonexistent/py.exe"))
    monkeypatch.setattr(viz.settings.assets, "simgraph2_root", Path("/nonexistent/sg2"))
    r = viz.start_previews(str(tmp_path / "some.cgns"))
    assert r["available"] is False and r["rendering"] is False and "reason" in r


def test_vtp_status_uncached(monkeypatch, tmp_path):
    # 未缓存 VTP → status 报未就绪、未在渲染（只读，不触发）
    monkeypatch.setattr(settings, "previews_dir", tmp_path)
    st = viz.vtp_status(str(tmp_path / "some.cgns"))
    assert st["available"] is False and st["rendering"] is False
