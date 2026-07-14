"""切片渲染集成测试 —— 真实调 PostProcessTool 环境出图。

环境（PostProcessTool python + SimGraph2 + 测试算例）缺失则自动跳过，不阻塞 CI。
"""
import glob
import os
from pathlib import Path

import pytest

from app.services import viz
from app.settings import settings

_CASE = r"D:/Git/SimGraph2/test_data/DLR_A_LTS/DLR_A_LTS.foam"
_ENV_OK = viz.available() and Path(_CASE).exists()

pytestmark = pytest.mark.skipif(not _ENV_OK, reason="PostProcessTool/SimGraph2/测试算例 不可用")


def test_preview_dir_naming():
    d = viz.preview_dir(_CASE)
    assert "DLR_A_LTS" in d.name


def test_render_four_slices(tmp_path, monkeypatch):
    # 用临时预览目录，避免污染
    monkeypatch.setattr(settings, "previews_dir", tmp_path)
    res = viz.generate_previews(_CASE, scalar="T")
    assert res["available"], res.get("reason")
    assert res["images"], "应产出切片图"
    # 至少 3 个方向切片 + 表面
    names = set(res["images"].keys())
    assert {"slice_X", "slice_Y", "slice_Z"} <= names
    # 图片文件真实存在且非空
    for fn in res["images"].values():
        p = Path(res["dir"]) / fn
        assert p.exists() and p.stat().st_size > 1000


def test_cache_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "previews_dir", tmp_path)
    viz.generate_previews(_CASE, scalar="T")
    res2 = viz.generate_previews(_CASE, scalar="T")
    assert res2.get("cached") is True
