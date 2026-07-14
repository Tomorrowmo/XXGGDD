"""评估元数据模型 —— 平台地基（严格对齐 docs/02-评估元数据模型.md）。

层级：
    L1  Unit（单位） → Delivery（交付批次）
    L2  Case（算例/试验车次，kind = simulation | experiment）
    L3  Measurement（测量） → OperatingPoint（规范工况，跨源对齐的锚）
    横切：Quantity（物理量登记）· Confidence（四级置信度）· Provenance（证据链）
    打分：Evaluation（可挂 L1/L2/L3）
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, Float, Text, ForeignKey, Enum, JSON, DateTime, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Confidence(str, enum.Enum):
    """四级置信度（复用 SimGraph 机制）。"""
    HIGH = "HIGH"        # 判据/真值直接命中
    MED = "MED"          # 规则推断
    LOW = "LOW"          # 弱证据
    PENDING = "PENDING"  # 待人工


class CaseKind(str, enum.Enum):
    SIMULATION = "simulation"
    EXPERIMENT = "experiment"


class ParseStatus(str, enum.Enum):
    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"


class MapMethod(str, enum.Enum):
    AUTO = "auto"      # 从数据自动识别
    RULE = "rule"      # 规则/映射表
    MANUAL = "manual"  # 人工指定


class EvalLevel(str, enum.Enum):
    MEASUREMENT = "measurement"   # L3
    CASE = "case"                 # L2
    DELIVERY = "delivery"         # L1


# --------------------------------------------------------------------------- L1
class Unit(Base):
    """承研单位（北航 / 西工大 / 航天六院 / 试车台…）。"""
    __tablename__ = "unit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32), default="承研单位")  # 承研单位/甲方/第三方/试车台

    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="unit", cascade="all, delete-orphan")


class Delivery(Base):
    """交付批次 —— 甲方评级的最小交付单元。"""
    __tablename__ = "delivery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(128))                 # "2026Q1 一轮交付"
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)  # 入库时写入，非脚本生成
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    unit: Mapped["Unit"] = relationship(back_populates="deliveries")
    cases: Mapped[list["Case"]] = relationship(back_populates="delivery", cascade="all, delete-orphan")


# --------------------------------------------------------------------------- L2
class Case(Base):
    """算例 / 试验车次 —— 仿真与实验的统一抽象。"""
    __tablename__ = "case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("delivery.id", ondelete="CASCADE"), index=True)
    kind: Mapped[CaseKind] = mapped_column(Enum(CaseKind), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)      # 算例名 / 车次号
    source_format: Mapped[str] = mapped_column(String(64))          # fluent-hdf5 / openfoam / txt-experiment …
    storage_uri: Mapped[str] = mapped_column(Text)                  # 文件存储位置
    content_hash: Mapped[str] = mapped_column(String(64), index=True)  # SHA-256，入库去重
    parse_status: Mapped[ParseStatus] = mapped_column(Enum(ParseStatus), default=ParseStatus.PENDING)
    parse_confidence: Mapped[Confidence] = mapped_column(Enum(Confidence), default=Confidence.PENDING)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # 求解器/湍流/燃料/网格量…
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    delivery: Mapped["Delivery"] = relationship(back_populates="cases")
    op_links: Mapped[list["CaseOperatingLink"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    measurements: Mapped[list["Measurement"]] = relationship(back_populates="case", cascade="all, delete-orphan")


# --------------------------------------------------------------------------- L3 锚
class OperatingPoint(Base):
    """规范工况点 —— 平台侧的共享身份，跨单位/跨来源对齐的锚（不属于任何单位）。"""
    __tablename__ = "operating_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)  # "Ma6-60kPa"
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # {Ma, 动压, 总温, 总压, 燃料, 当量比…}
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    links: Mapped[list["CaseOperatingLink"]] = relationship(back_populates="op", cascade="all, delete-orphan")


class CaseOperatingLink(Base):
    """算例↔工况映射（心脏）—— 对齐动作本身带方法与置信度，可追溯、可人工纠偏。"""
    __tablename__ = "case_operating_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True)
    op_id: Mapped[int] = mapped_column(ForeignKey("operating_point.id", ondelete="CASCADE"), index=True)
    method: Mapped[MapMethod] = mapped_column(Enum(MapMethod), default=MapMethod.AUTO)
    mapping_confidence: Mapped[Confidence] = mapped_column(Enum(Confidence), default=Confidence.PENDING)
    mapped_by: Mapped[str | None] = mapped_column(String(64), nullable=True)   # 系统 / 规则名 / 用户

    case: Mapped["Case"] = relationship(back_populates="op_links")
    op: Mapped["OperatingPoint"] = relationship(back_populates="links")


# --------------------------------------------------------------------------- 横切
class Quantity(Base):
    """物理量登记 —— 统一语义（直接复用 sim-knowledge/mappings）。"""
    __tablename__ = "quantity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)   # wall_pressure / thrust / mass_flow
    physical_name: Mapped[str] = mapped_column(String(128))
    standard_unit: Mapped[str] = mapped_column(String(32))
    aliases: Mapped[dict | None] = mapped_column(JSON, nullable=True)       # raw_name → 归一（含量纲坑）
    valid_range: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # {min, max}

    measurements: Mapped[list["Measurement"]] = relationship(back_populates="quantity")


class Measurement(Base):
    """测量 —— 一个物理量的一个值（L3 最细粒度）。"""
    __tablename__ = "measurement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True)
    op_id: Mapped[int | None] = mapped_column(ForeignKey("operating_point.id"), index=True, nullable=True)
    quantity_id: Mapped[int] = mapped_column(ForeignKey("quantity.id"), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))              # 经语义归一后的标准量纲
    raw_name: Mapped[str | None] = mapped_column(String(128), nullable=True)   # 原始列名/变量名，可追溯
    source_kind: Mapped[CaseKind] = mapped_column(Enum(CaseKind))              # 冗余便于对比查询
    status: Mapped[str] = mapped_column(String(16), default="normal")          # normal/warning/anomaly
    confidence: Mapped[Confidence] = mapped_column(Enum(Confidence), default=Confidence.MED)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)         # 证据链（源文件+tier+判据+文献）

    case: Mapped["Case"] = relationship(back_populates="measurements")
    quantity: Mapped["Quantity"] = relationship(back_populates="measurements")


# --------------------------------------------------------------------------- 对话（对齐 DataAgent）
class Conversation(Base):
    """对话会话（持久化）。单租户，故不挂 user。"""
    __tablename__ = "conversation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="Message.id")


class Message(Base):
    """对话消息（system/user/assistant）。"""
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


# --------------------------------------------------------------------------- 打分
class Evaluation(Base):
    """评估记录 —— 可挂在 L3 测量 / L2 算例 / L1 交付三层。评分读 sim-knowledge criteria。"""
    __tablename__ = "evaluation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_level: Mapped[EvalLevel] = mapped_column(Enum(EvalLevel), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)     # 指向对应层对象的 id
    op_id: Mapped[int | None] = mapped_column(ForeignKey("operating_point.id"), nullable=True, index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(8), nullable=True)     # A-/B+/B…（L1 评级）
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 可信/存疑/异常/最优
    deviation: Mapped[float | None] = mapped_column(Float, nullable=True)   # 相对真值偏差（L3）
    criteria_hits: Mapped[dict | None] = mapped_column(JSON, nullable=True) # 触发的判据 intent 列表
    confidence: Mapped[Confidence] = mapped_column(Enum(Confidence), default=Confidence.MED)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
