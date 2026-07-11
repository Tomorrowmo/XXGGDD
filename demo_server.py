"""兼容旧引用的薄 shim。真正的应用在 app.main。请改用 `python run.py`。"""
from app.main import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8501, reload=True)
