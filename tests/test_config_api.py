"""解析/物理常数配置端点测试（/config/parse GET/PUT + 持久化 + 判据只读汇报）。"""
from app.settings import settings
from app.services import config_store


def test_get_parse_config(client):
    d = client.get("/api/v2/config/parse").json()
    assert d["experiment"]["header_index"] == 10
    assert d["experiment"]["delimiter"] == ","
    assert d["physics"]["gamma"] == 1.4
    # 判据只读来源汇报（sim-knowledge 护城河）
    assert "criteria" in d and "n_domains" in d["criteria"]
    assert "channel_patterns" in d["editable"]["experiment"]


def test_put_updates_and_persists(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "parse_config_file", tmp_path / "parse_config.json")
    try:
        r = client.put("/api/v2/config/parse", json={
            "experiment": {"header_index": 8, "atmos_correction_mpa": 0.1,
                           "channel_patterns": ["流道\\d+", "喷管\\d+"]},
            "physics": {"gamma": 1.33}})
        d = r.json()
        assert d["experiment"]["header_index"] == 8
        assert "喷管\\d+" in d["experiment"]["channel_patterns"]
        assert d["physics"]["gamma"] == 1.33
        # 内存 settings 已改
        assert settings.experiment.header_index == 8
        # 落盘了
        assert (tmp_path / "parse_config.json").exists()
        # 重新载入应用回（模拟重启）
        settings.experiment.header_index = 999
        config_store.load_overrides()
        assert settings.experiment.header_index == 8
    finally:
        # 还原，避免污染其它用例的全局 settings
        settings.experiment.header_index = 10
        settings.experiment.atmos_correction_mpa = 0.101325
        settings.experiment.channel_patterns = [r"流道\d+", r"室压\d+", r"隔离段\d+", r"壁温\d+", r"流量\d+"]
        settings.physics.gamma = 1.4


def test_put_rejects_bad_regex(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "parse_config_file", tmp_path / "parse_config.json")
    try:
        r = client.put("/api/v2/config/parse",
                       json={"experiment": {"channel_patterns": ["流道["]}})
        assert r.status_code == 400
        # settings 未被破坏
        assert settings.experiment.header_index == 10
    finally:
        settings.experiment.channel_patterns = [r"流道\d+", r"室压\d+", r"隔离段\d+", r"壁温\d+", r"流量\d+"]
