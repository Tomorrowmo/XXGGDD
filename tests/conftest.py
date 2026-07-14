"""pytest 夹具 —— 隔离的临时数据库 + 会话 + TestClient。

注意：EVAL_DB_URL 必须在 import app.settings 之前设置（settings.db_url 在类定义时求值）。
conftest 由 pytest 最先导入，故在此模块顶层设置环境变量。
"""
import os
import tempfile
import pathlib

_TMP = tempfile.mkdtemp(prefix="evaltest_")
_DB = pathlib.Path(_TMP, "test.db").as_posix()
os.environ["EVAL_DB_URL"] = f"sqlite:///{_DB}"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import pytest  # noqa: E402
from app.db.database import Base, engine, SessionLocal  # noqa: E402
import app.db.models  # noqa: E402,F401  注册模型到 Base.metadata


def _fresh_schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def db():
    """函数级：干净库 + 会话。"""
    _fresh_schema()
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def seeded_db(db):
    """已写入 XF-2 场景的库。"""
    from app.services.seed import seed
    seed(db, reset=True)
    return db


@pytest.fixture
def client():
    """FastAPI TestClient（干净库）。"""
    _fresh_schema()
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def exp_file(tmp_path):
    """合成一份热试车 TXT（headerIndex=10 + 点火/主级/关车剖面）。"""
    import numpy as np
    lines = [f"#meta {i}" for i in range(10)]
    lines.append("Time (s),流道22,流道23,室压1")
    N = 1000
    t = np.linspace(0, 18.4, N)
    prof = np.piecewise(
        t,
        [t < 2.5, (t >= 2.5) & (t < 4), (t >= 4) & (t < 16), t >= 16],
        [0.01, lambda x: 0.01 + (x - 2.5) / 1.5 * 3.0, 3.10,
         lambda x: np.maximum(3.10 * (1 - (x - 16) / 2.4), 0)],
    )
    rng = np.random.default_rng(42)
    for i in range(N):
        p = max(prof[i], 0.0)
        lines.append(f"{t[i]:.4f},{p + rng.normal(0, 0.005):.4f},{p * 0.98:.4f},{p * 0.66:.4f}")
    f = tmp_path / "试车03.txt"
    f.write_text("\n".join(lines), encoding="utf-8")
    return str(f)
