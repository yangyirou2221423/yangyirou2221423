"""Flask 数学函数可视化服务。"""

from __future__ import annotations

import math
import os
from typing import Any

import numpy as np
from flask import Flask, jsonify, render_template, request

from safe_eval import MAX_EXPRESSION_LENGTH, SafeExpressionError, evaluate

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
app.json.ensure_ascii = False

DEFAULT_X_MIN = -10.0
DEFAULT_X_MAX = 10.0
DEFAULT_NUM_POINTS = 1000
MIN_NUM_POINTS = 10
MAX_NUM_POINTS = 5000


class RequestError(ValueError):
    """请求参数不合法。"""


def _parse_expression(payload: dict[str, Any]) -> str:
    expression = payload.get("expression")
    if not isinstance(expression, str):
        raise RequestError("请提供 expression 字段（函数表达式）")
    expression = expression.strip()
    if not expression:
        raise RequestError("函数表达式不能为空")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise RequestError(f"函数表达式过长（最多 {MAX_EXPRESSION_LENGTH} 个字符）")
    return expression


def _parse_number(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool):
        raise RequestError(f"{key} 必须是数字")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError as exc:
            raise RequestError(f"{key} 必须是数字") from exc
    else:
        raise RequestError(f"{key} 必须是数字")
    if not math.isfinite(number):
        raise RequestError(f"{key} 必须是有限数字")
    return number


def _parse_num_points(payload: dict[str, Any]) -> int:
    value = payload.get("num_points", DEFAULT_NUM_POINTS)
    if isinstance(value, bool):
        raise RequestError("num_points 必须是整数")
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError as exc:
            raise RequestError("num_points 必须是整数") from exc
    if not isinstance(value, (int, float)):
        raise RequestError("num_points 必须是整数")
    number = float(value)
    if not math.isfinite(number) or not number.is_integer():
        raise RequestError("num_points 必须是整数")
    points = int(number)
    if not MIN_NUM_POINTS <= points <= MAX_NUM_POINTS:
        raise RequestError(
            f"num_points 必须在 {MIN_NUM_POINTS} 到 {MAX_NUM_POINTS} 之间"
        )
    return points


def _to_plot_array(result: Any, shape: tuple[int, ...]) -> np.ndarray:
    array = np.asarray(result)
    if np.iscomplexobj(array):
        raise RequestError("表达式返回了复数，无法在二维实数坐标系中绘制")
    try:
        array = np.asarray(array, dtype=float)
    except (TypeError, ValueError) as exc:
        raise RequestError("表达式结果不是数值") from exc
    if array.ndim > 1:
        raise RequestError("表达式结果必须是一维数组")
    try:
        array = np.broadcast_to(array, shape)
    except ValueError as exc:
        raise RequestError("表达式结果的形状与 x 不匹配") from exc
    return array


def find_discontinuity_gaps(y: np.ndarray) -> list[int]:
    """保守识别渐近线断点。

    规则：相邻两点符号相反，且两侧幅值都超过有限值稳健尺度（p95-p5）的 3 倍。
    返回的索引 i 表示曲线应在第 i-1 与第 i 点之间断开。
    """
    finite = y[np.isfinite(y)]
    if finite.size < MIN_NUM_POINTS:
        return []
    spread = float(np.percentile(finite, 95) - np.percentile(finite, 5))
    if spread <= 0 or not math.isfinite(spread):
        return []

    threshold = 3.0 * spread
    gaps: list[int] = []
    for index in range(1, y.size):
        left = y[index - 1]
        right = y[index]
        if not (np.isfinite(left) and np.isfinite(right)):
            continue
        if np.signbit(left) == np.signbit(right):
            continue
        if abs(left) > threshold and abs(right) > threshold:
            gaps.append(index)
    return gaps


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/2d-function")
def compute_2d():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("请求体必须是 JSON 对象")

    try:
        expression = _parse_expression(payload)
        x_min = _parse_number(payload, "x_min", DEFAULT_X_MIN)
        x_max = _parse_number(payload, "x_max", DEFAULT_X_MAX)
        num_points = _parse_num_points(payload)
        if x_min >= x_max:
            raise RequestError("x_min 必须小于 x_max")
        if not math.isfinite(x_max - x_min):
            raise RequestError("x 轴范围跨度过大")

        x = np.linspace(x_min, x_max, num_points)
        if not np.isfinite(x).all():
            raise RequestError("x 轴范围无效")
        with np.errstate(all="ignore"):
            result = evaluate(expression, x)
        y = _to_plot_array(result, x.shape)
        gaps = find_discontinuity_gaps(y)

        y_values = [
            float(value) if math.isfinite(float(value)) else None for value in y
        ]
        return jsonify(
            {
                "expression": expression,
                "x": x.tolist(),
                "y": y_values,
                "gaps": gaps,
                "num_points": num_points,
            }
        )
    except (RequestError, SafeExpressionError) as exc:
        return _error(str(exc))
    except Exception:  # noqa: BLE001 - 兜底，避免向客户端泄漏堆栈
        app.logger.exception("计算函数表达式时发生未预期错误")
        return _error("服务器计算失败，请稍后重试", 500)


@app.errorhandler(413)
def payload_too_large(_error_obj):
    return _error("请求体过大", 413)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
