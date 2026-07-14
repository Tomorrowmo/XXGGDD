"""大模型配置 API（v2）—— 配置方式对齐 DataAgent（.env 默认 + BYOK 覆盖）。"""
from __future__ import annotations

from fastapi import APIRouter, Body
from pydantic import BaseModel

from app.services import llm as llm_svc

router = APIRouter(prefix="/api/v2/llm", tags=["llm-config"])


class SaveConfigReq(BaseModel):
    api_key: str = ""      # 空串=清除，回退 .env
    base_url: str = ""     # 空=回退 .env
    model: str = ""        # 空=回退 .env


class TestReq(BaseModel):
    api_key: str = ""      # 填了就用它测；空则用已保存/.env
    base_url: str = ""
    model: str = ""


@router.get("/config")
def get_config():
    """当前生效配置（脱敏，只报是否已配 key）。"""
    return llm_svc.public_config()


@router.put("/config")
def save_config(req: SaveConfigReq):
    """保存 BYOK 覆盖。空串回退 .env。"""
    llm_svc.save_override(api_key=req.api_key, base_url=req.base_url, model=req.model)
    return {"ok": True, **llm_svc.public_config()}


@router.post("/test")
async def test_config(req: TestReq | None = Body(default=None)):
    """连通性测试。若传入 api_key/base_url/model 则用它们测（未保存也能测）；否则用生效配置。"""
    req = req or TestReq()
    client = llm_svc.LLMClient(
        api_key=(req.api_key or None),
        base_url=(req.base_url or None),
        model=(req.model or None),
    )
    return await client.test()
