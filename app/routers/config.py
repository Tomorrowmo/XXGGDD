"""解析 / 物理常数 / 判据来源 配置 API（v2）—— 配置页"解析与判据配置"卡片接真。

GET 读真实 settings 值；PUT 改写白名单字段并落 parse_config.json（判据只读）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import config_store

router = APIRouter(prefix="/api/v2/config", tags=["config"])


@router.get("/parse")
def get_parse_config():
    return config_store.get_config()


class ExperimentPatch(BaseModel):
    delimiter: str | None = None
    encoding: str | None = None
    header_index: int | None = None
    time_column: int | None = None
    channel_patterns: list[str] | str | None = None
    atmos_correction_mpa: float | None = None


class PhysicsPatch(BaseModel):
    gamma: float | None = None
    gas_constant: float | None = None


class ParseConfigPatch(BaseModel):
    experiment: ExperimentPatch | None = None
    physics: PhysicsPatch | None = None


@router.put("/parse")
def update_parse_config(patch: ParseConfigPatch):
    try:
        return config_store.update_config(patch.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
