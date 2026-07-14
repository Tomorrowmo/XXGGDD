"""自然语言检索 API（v2）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import search as search_svc

router = APIRouter(prefix="/api/v2/search", tags=["search"])


@router.get("")
def nl_search(q: str, db: Session = Depends(get_db)):
    """自然语言检索：把大白话解析成结构化查询并返回命中算例/排名答案。"""
    return search_svc.search(db, q)
