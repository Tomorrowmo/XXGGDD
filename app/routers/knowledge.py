"""知识库 API（v2）—— 知识库注册表 + RAG 问答（检索增强，带出处）。

管理（增删库/文档）与问答；问答优先走已有 ragflow 通道，缺配置时返回结构化说明。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2/knowledge", tags=["knowledge"])

# 知识库注册表（可后续落库/落 knowledge.json）
_BASES = [
    {"id": "eval_std", "name": "组合动力评估标准库", "docs": 4, "chunks": 128, "updated": "2026-07-12"},
    {"id": "history", "name": "历史评估报告库", "docs": 17, "chunks": 542, "updated": "2026-07-14"},
    {"id": "literature", "name": "领域文献库", "docs": 33, "chunks": 1204, "updated": "2026-06-30"},
    {"id": "usage_docs", "name": "使用文档", "docs": 6, "chunks": 88, "updated": "2026-07-10"},
]

_DOCS = {
    "eval_std": [
        {"name": "组合动力仿真数据评估规范 v2.1.pdf", "size": "2.3 MB", "status": "indexed"},
        {"name": "热试车数据处理与判据标准.docx", "size": "860 KB", "status": "indexed"},
        {"name": "组合动力性能量定义.md", "size": "42 KB", "status": "indexed"},
        {"name": "评估流程 SOP.pdf", "size": "1.1 MB", "status": "indexing"},
    ],
}


@router.get("/bases")
def list_bases():
    return {"bases": _BASES}


@router.get("/bases/{base_id}/docs")
def list_docs(base_id: str):
    return {"base_id": base_id, "docs": _DOCS.get(base_id, [])}


class QueryReq(BaseModel):
    base_id: str = "eval_std"
    question: str


@router.post("/query")
def query(req: QueryReq):
    """RAG 问答：检索知识库并作答，附原文出处。

    实际检索走 RAGflow（已有 ragflow 通道）；此处给出结构化响应骨架，
    部署接入 RAGflow 后填充真实 answer/sources。
    """
    # TODO(部署): 接 app.core.rag_client / ragflow，用 req.base_id 检索
    return {
        "base_id": req.base_id,
        "question": req.question,
        "answer": "（需接入 RAGflow 后返回真实答案）",
        "sources": [],
        "ready": False,
    }
