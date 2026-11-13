"""安全表达式求值器测试。"""

import numpy as np
import pytest

from safe_eval import MAX_EXPRESSION_LENGTH, SafeExpressionError, evaluate

X = np.linspace(-2.0, 2.0, 5)


def test_trig_functions():
    result = evaluate("sin(x)", X)
    assert np.allclose(result, np.sin(X))


def test_np_prefix():
    assert np.allclose(evaluate("np.sin(x)", X), np.sin(X))
    assert np.allclose(evaluate("np.cos(x) * np.exp(-abs(x))", X), np.cos(X) * np.exp(-np.abs(X)))


def test_constants():
    assert evaluate("pi", X) == pytest.approx(np.pi)
    assert evaluate("e", X) == pytest.approx(np.e)
    assert np.allclose(evaluate("sin(pi * x)", X), np.sin(np.pi * X))


def test_unicode_symbols_are_normalized():
    assert np.allclose(evaluate("π * x", X), np.pi * X)
    assert np.allclose(evaluate("x × 2 ÷ 4 − 1", X), X * 2 / 4 - 1)
    assert np.allclose(evaluate("（x）", X), X)


def test_scalar_result():
    assert evaluate("5", X) == 5.0
    assert evaluate("np.pi", X) == pytest.approx(np.pi)


def test_comparison_and_where():
    result = evaluate("where(x > 0, x, -x)", X)
    assert np.allclose(result, np.abs(X))


def test_boolean_combination():
    result = evaluate("(x > -1) & (x < 1)", X)
    assert result.tolist() == ((X > -1) & (X < 1)).tolist()


def test_domain_errors_return_nan_not_exception():
    values = evaluate("log(x)", X)
    assert np.isnan(values[0])
    assert np.isnan(values[1])


def test_division_by_zero_returns_inf():
    values = evaluate("1 / x", np.array([-1.0, 0.0, 1.0]))
    assert values[0] == -1.0
    assert np.isinf(values[1])
    assert values[2] == 1.0


def test_abs_alias():
    assert np.allclose(evaluate("abs(x)", X), np.abs(X))


@pytest.mark.parametrize(
    "payload",
    [
        "__import__('os').getcwd()",
        "().__class__.__bases__",
        "x.__class__",
        "np.sin.__globals__",
        "np.load('x')",
        "np.ctypeslib",
        "open('/etc/passwd')",
        "eval('1 + 1')",
        "getattr(x, 'shape')",
        "lambda: 1",
        "[item for item in x]",
        "x[0]",
        "'abc'",
    ],
)
def test_rejects_unsafe_expressions(payload):
    with pytest.raises(SafeExpressionError):
        evaluate(payload, X)


def test_caret_has_helpful_message():
    with pytest.raises(SafeExpressionError, match=r"\*\*"):
        evaluate("x ^ 2", X)


def test_chained_comparison_has_helpful_message():
    with pytest.raises(SafeExpressionError, match="链式比较"):
        evaluate("0 < x < 1", X)


def test_unknown_function_message():
    with pytest.raises(SafeExpressionError, match="foo"):
        evaluate("foo(x)", X)


def test_function_used_without_call():
    with pytest.raises(SafeExpressionError, match="sin"):
        evaluate("sin + 1", X)


def test_keyword_arguments_rejected():
    with pytest.raises(SafeExpressionError, match="关键字参数"):
        evaluate("round(x, decimals=2)", X)


def test_expression_length_limit():
    expression = "x" + "+0" * MAX_EXPRESSION_LENGTH
    with pytest.raises(SafeExpressionError, match="过长"):
        evaluate(expression, X)


def test_ast_node_limit():
    expression = "x" + "+1" * 100
    assert len(expression) < MAX_EXPRESSION_LENGTH
    with pytest.raises(SafeExpressionError, match="复杂"):
        evaluate(expression, X)


def test_ast_depth_limit():
    expression = "sin(" * 45 + "x" + ")" * 45
    with pytest.raises(SafeExpressionError, match="嵌套"):
        evaluate(expression, X)


def test_huge_power_fails_fast():
    with pytest.raises(SafeExpressionError, match="数值过大"):
        evaluate("9 ** 9 ** 9 ** 9", X)


def test_empty_and_syntax_errors():
    with pytest.raises(SafeExpressionError):
        evaluate("", X)
    with pytest.raises(SafeExpressionError, match="语法错误"):
        evaluate("sin(", X)
