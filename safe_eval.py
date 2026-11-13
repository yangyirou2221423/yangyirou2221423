"""白名单式数学表达式求值器。

不使用 Python 的 ``eval``：先把表达式解析成 AST，校验节点类型，再由本模块
自行递归求值。只允许数字、``x``、常量以及白名单中的数学函数。
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable

import numpy as np

MAX_EXPRESSION_LENGTH = 300
MAX_AST_NODES = 200
MAX_AST_DEPTH = 40

__all__ = [
    "MAX_EXPRESSION_LENGTH",
    "SUPPORTED_CONSTANTS",
    "SUPPORTED_FUNCTIONS",
    "SafeExpressionError",
    "evaluate",
]


class SafeExpressionError(ValueError):
    """表达式非法或无法计算时抛出，消息可直接展示给用户。"""


_NUMPY_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "asin": np.arcsin,
    "acos": np.arccos,
    "atan": np.arctan,
    "atan2": np.arctan2,
    "arctan2": np.arctan2,
    "arcsin": np.arcsin,
    "arccos": np.arccos,
    "arctan": np.arctan,
    "sinh": np.sinh,
    "cosh": np.cosh,
    "tanh": np.tanh,
    "asinh": np.arcsinh,
    "acosh": np.arccosh,
    "atanh": np.arctanh,
    "arcsinh": np.arcsinh,
    "arccosh": np.arccosh,
    "arctanh": np.arctanh,
    "exp": np.exp,
    "expm1": np.expm1,
    "log": np.log,
    "log1p": np.log1p,
    "log2": np.log2,
    "log10": np.log10,
    "sqrt": np.sqrt,
    "cbrt": np.cbrt,
    "abs": np.abs,
    "absolute": np.abs,
    "sign": np.sign,
    "floor": np.floor,
    "ceil": np.ceil,
    "round": np.round,
    "trunc": np.trunc,
    "rint": np.rint,
    "square": np.square,
    "power": np.power,
    "hypot": np.hypot,
    "degrees": np.degrees,
    "radians": np.radians,
    "minimum": np.minimum,
    "maximum": np.maximum,
    "clip": np.clip,
    "where": np.where,
    "mod": np.mod,
    "remainder": np.remainder,
}

SUPPORTED_FUNCTIONS = tuple(sorted(_NUMPY_FUNCTIONS))
SUPPORTED_CONSTANTS = ("pi", "e", "tau")

_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
}

_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Invert: operator.invert,
}

_COMPARE_OPERATORS: dict[type[ast.cmpop], Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_FULLWIDTH_OFFSET = 0xFEE0
_TRANSLATION = str.maketrans(
    {
        "π": "pi",
        "×": "*",
        "·": "*",
        "÷": "/",
        "−": "-",
        "　": " ",
    }
)


def _function_hint() -> str:
    return "sin、cos、tan、exp、log、sqrt、abs、where 等"


def _short_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message if len(message) <= 120 else message[:117] + "..."


def _normalize(expression: str) -> str:
    """把常见 Unicode 数学符号与全角字符转成 ASCII。"""
    expression = expression.translate(_TRANSLATION)
    chars: list[str] = []
    for char in expression:
        code = ord(char)
        if 0xFF01 <= code <= 0xFF5E:
            chars.append(chr(code - _FULLWIDTH_OFFSET))
        else:
            chars.append(char)
    return "".join(chars)


def _syntax_message(exc: SyntaxError) -> str:
    detail = (exc.msg or "无法解析").strip()
    return f"表达式语法错误：{detail}。乘法用 *，乘方用 **。"


def _check_limits(tree: ast.AST) -> None:
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise SafeExpressionError("表达式过于复杂，请简化后重试")
    _check_depth(tree, 1)


def _check_depth(node: ast.AST, depth: int) -> None:
    if depth > MAX_AST_DEPTH:
        raise SafeExpressionError("表达式嵌套过深，请简化后重试")
    for child in ast.iter_child_nodes(node):
        _check_depth(child, depth + 1)


class _Evaluator:
    def __init__(self, x: Any) -> None:
        self._x = x

    def visit(self, node: ast.AST) -> Any:
        method = getattr(self, "_visit_" + type(node).__name__, None)
        if method is None:
            raise SafeExpressionError(f"表达式包含不支持的语法（{type(node).__name__}）")
        return method(node)

    def _visit_Constant(self, node: ast.Constant) -> float:
        value = node.value
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            try:
                return float(value)
            except OverflowError as exc:
                raise SafeExpressionError("数值常量过大") from exc
        raise SafeExpressionError("表达式中只能使用数字常量")

    def _visit_Name(self, node: ast.Name) -> Any:
        name = node.id
        if name == "x":
            return self._x
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        if name == "np":
            raise SafeExpressionError("np 只能用于调用 np.函数名，例如 np.sin(x)")
        if name in _NUMPY_FUNCTIONS:
            raise SafeExpressionError(f"{name} 是函数，请写成 {name}(x)")
        raise SafeExpressionError(f"不支持的名称 {name!r}。常用函数：{_function_hint()}")

    def _visit_Attribute(self, node: ast.Attribute) -> Any:
        if not (isinstance(node.value, ast.Name) and node.value.id == "np"):
            raise SafeExpressionError("只允许访问 np 下的白名单函数，例如 np.sin(x)")
        if node.attr.startswith("_"):
            raise SafeExpressionError("不支持的属性访问")
        if node.attr in _NUMPY_FUNCTIONS:
            return _NUMPY_FUNCTIONS[node.attr]
        if node.attr in _CONSTANTS:
            return _CONSTANTS[node.attr]
        raise SafeExpressionError(f"不支持的函数 np.{node.attr}。常用函数：{_function_hint()}")

    def _resolve_callable(self, node: ast.AST) -> Callable[..., Any]:
        if isinstance(node, ast.Name):
            if node.id in _NUMPY_FUNCTIONS:
                return _NUMPY_FUNCTIONS[node.id]
            raise SafeExpressionError(f"不支持的函数 {node.id}。常用函数：{_function_hint()}")
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "np"
                and node.attr in _NUMPY_FUNCTIONS
            ):
                return _NUMPY_FUNCTIONS[node.attr]
            raise SafeExpressionError("只允许调用 np 下的白名单函数")
        raise SafeExpressionError("只能调用白名单中的数学函数")

    def _visit_Call(self, node: ast.Call) -> Any:
        if node.keywords:
            raise SafeExpressionError("函数调用不支持关键字参数")
        func = self._resolve_callable(node.func)
        args = [self.visit(arg) for arg in node.args]
        try:
            with np.errstate(all="ignore"):
                return func(*args)
        except SafeExpressionError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转成面向用户的错误
            raise SafeExpressionError(f"函数计算出错：{_short_message(exc)}") from exc

    def _visit_BinOp(self, node: ast.BinOp) -> Any:
        if isinstance(node.op, ast.BitXor):
            raise SafeExpressionError("不支持 ^ 运算符；乘方请使用 **")
        func = _BINARY_OPERATORS.get(type(node.op))
        if func is None:
            raise SafeExpressionError("不支持的运算符")
        left = self.visit(node.left)
        right = self.visit(node.right)
        try:
            with np.errstate(all="ignore"):
                return func(left, right)
        except ZeroDivisionError as exc:
            raise SafeExpressionError("表达式出现除以零") from exc
        except OverflowError as exc:
            raise SafeExpressionError("数值过大，无法计算") from exc
        except Exception as exc:  # noqa: BLE001
            raise SafeExpressionError(f"运算失败：{_short_message(exc)}") from exc

    def _visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        func = _UNARY_OPERATORS.get(type(node.op))
        if func is None:
            raise SafeExpressionError("不支持的一元运算符")
        operand = self.visit(node.operand)
        try:
            with np.errstate(all="ignore"):
                return func(operand)
        except Exception as exc:  # noqa: BLE001
            raise SafeExpressionError(f"运算失败：{_short_message(exc)}") from exc

    def _visit_Compare(self, node: ast.Compare) -> Any:
        if len(node.ops) != 1:
            raise SafeExpressionError("不支持链式比较，请写成 (x > 0) & (x < 1)")
        func = _COMPARE_OPERATORS.get(type(node.ops[0]))
        if func is None:
            raise SafeExpressionError("不支持的比较运算符")
        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
        try:
            with np.errstate(all="ignore"):
                return func(left, right)
        except Exception as exc:  # noqa: BLE001
            raise SafeExpressionError(f"比较失败：{_short_message(exc)}") from exc

    def _visit_BoolOp(self, node: ast.BoolOp) -> Any:
        raise SafeExpressionError("条件之间请使用 & 或 | 连接，例如 (x > 0) & (x < 1)")

    def _visit_Subscript(self, node: ast.Subscript) -> Any:
        raise SafeExpressionError("不支持下标访问")

    def _visit_Lambda(self, node: ast.Lambda) -> Any:
        raise SafeExpressionError("不支持 lambda 表达式")


def evaluate(expression: str, x: Any) -> Any:
    """计算表达式，返回 numpy 数组或标量；非法输入抛 SafeExpressionError。"""
    if not isinstance(expression, str):
        raise SafeExpressionError("表达式必须是字符串")

    normalized = _normalize(expression).strip()
    if not normalized:
        raise SafeExpressionError("表达式不能为空")
    if len(normalized) > MAX_EXPRESSION_LENGTH:
        raise SafeExpressionError(f"表达式过长（最多 {MAX_EXPRESSION_LENGTH} 个字符）")

    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise SafeExpressionError(_syntax_message(exc)) from exc
    except (ValueError, RecursionError, MemoryError) as exc:
        raise SafeExpressionError("表达式无法解析，请检查后重试") from exc

    _check_limits(tree)
    evaluator = _Evaluator(x)
    with np.errstate(all="ignore"):
        return evaluator.visit(tree.body)
