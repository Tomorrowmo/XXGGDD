"""用户自定义算法 skills —— 表达式编排（安全求值），把公式库变成可扩展的算法平台。

用户在前端写一个**安全算术表达式**（如 thrust/mass_flow、sqrt(gamma*R*T)），
用已有变量（算例 QOI / 物理常数）组合，后端受限 AST 求值、落盘、可在真实算例上试算。
只允许：数字、变量名、+ - * / ** %、一元正负、白名单函数——**不执行任意代码**。
"""
from __future__ import annotations

import ast
import json
import math
import operator
import uuid

from app.settings import settings

_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "min": min, "max": max, "log": math.log,
    "log10": math.log10, "exp": math.exp, "sin": math.sin, "cos": math.cos,
    "tan": math.tan, "floor": math.floor, "ceil": math.ceil, "pow": pow,
    "round": round,
}
_CONSTS = {"pi": math.pi, "e": math.e}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class ExprError(ValueError):
    pass


def _walk(node, context: dict):
    if isinstance(node, ast.Expression):
        return _walk(node.body, context)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        raise ExprError("只允许数字常量")
    if isinstance(node, ast.BinOp):
        op = _BIN.get(type(node.op))
        if op is None:
            raise ExprError("不允许的运算符")
        return op(_walk(node.left, context), _walk(node.right, context))
    if isinstance(node, ast.UnaryOp):
        op = _UN.get(type(node.op))
        if op is None:
            raise ExprError("不允许的一元运算符")
        return op(_walk(node.operand, context))
    if isinstance(node, ast.Name):
        if node.id in context:
            return float(context[node.id])
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ExprError(f"未知变量：{node.id}")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise ExprError("不允许的函数调用")
        return _FUNCS[node.func.id](*[_walk(a, context) for a in node.args])
    raise ExprError("表达式含不允许的结构")


def safe_eval(expr: str, context: dict) -> float:
    """受限 AST 求值。非法结构 / 未知变量 / 数学错误 → ExprError。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"表达式语法错误：{e.msg}")
    try:
        return float(_walk(tree, context))
    except ExprError:
        raise
    except ZeroDivisionError:
        raise ExprError("除以零")
    except Exception as e:  # noqa: BLE001
        raise ExprError(f"求值失败：{e}")


def expr_variables(expr: str) -> list[str]:
    """抽出表达式里用到的自由变量名（排除函数名与常量）。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return []
    names, funcs = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            funcs.add(n.func.id)
        elif isinstance(n, ast.Name):
            names.add(n.id)
    return sorted(names - funcs - set(_CONSTS))


def validate_expr(expr: str) -> dict:
    """静态校验：能解析 + 只含允许结构（用占位 1.0 求值探测）。返回 {ok, vars, reason?}。"""
    vs = expr_variables(expr)
    try:
        safe_eval(expr, {v: 1.0 for v in vs})
    except ExprError as e:
        return {"ok": False, "vars": vs, "reason": str(e)}
    return {"ok": True, "vars": vs}


# --------------------------------------------------------------------------- 存储
def _load() -> list[dict]:
    f = settings.algorithms_file
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
    return []


def _save(items: list[dict]) -> None:
    settings.algorithms_file.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_algorithms() -> list[dict]:
    return _load()


def add_algorithm(*, name: str, expr: str, unit: str = "", category: str = "自定义",
                  description: str = "") -> dict:
    v = validate_expr(expr)
    if not v["ok"]:
        raise ExprError(v.get("reason", "表达式非法"))
    if not (name or "").strip():
        raise ExprError("算法名不能为空")
    item = {"id": uuid.uuid4().hex[:10], "name": name.strip(), "expr": expr.strip(),
            "unit": unit.strip(), "category": (category or "自定义").strip(),
            "description": description.strip(), "inputs": v["vars"], "builtin": False}
    items = _load()
    items.append(item)
    _save(items)
    return item


def delete_algorithm(algo_id: str) -> bool:
    items = _load()
    kept = [x for x in items if x.get("id") != algo_id]
    if len(kept) == len(items):
        return False
    _save(kept)
    return True


def evaluate(expr: str, context: dict) -> dict:
    """在给定变量上下文上求值。返回 {ok, value, missing?, reason?}。"""
    need = expr_variables(expr)
    missing = [v for v in need if v not in context]
    if missing:
        return {"ok": False, "missing": missing,
                "reason": "缺变量：" + ", ".join(missing)}
    try:
        return {"ok": True, "value": safe_eval(expr, context)}
    except ExprError as e:
        return {"ok": False, "reason": str(e)}
