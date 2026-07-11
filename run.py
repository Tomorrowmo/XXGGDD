"""启动入口：在项目根执行 `python run.py`，服务运行于 http://0.0.0.0:8501。"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8501, reload=True)
