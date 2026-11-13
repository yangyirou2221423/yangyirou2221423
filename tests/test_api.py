"""HTTP API 与断点检测测试。"""

import json

import numpy as np
import pytest

from app import app, find_discontinuity_gaps


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def post_curve(client, **overrides):
    payload = {
        "expression": "sin(x)",
        "x_min": -10,
        "x_max": 10,
        "num_points": 100,
    }
    payload.update(overrides)
    return client.post("/api/2d-function", json=payload)


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "函数图像" in body
    assert "chartjs-plugin-zoom" in body


def test_valid_request(client):
    response = post_curve(client)
    assert response.status_code == 200
    data = response.get_json()
    assert data["expression"] == "sin(x)"
    assert len(data["x"]) == len(data["y"]) == 100
    assert data["num_points"] == 100
    assert isinstance(data["gaps"], list)
    assert all(
        isinstance(point, (int, float)) for point in data["x"]
    )


def test_log_negative_values_are_null_and_json_parses(client):
    response = post_curve(client, expression="log(x)")
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert any(value is None for value in data["y"])
    # 关键：响应体必须是合法 JSON（不能出现裸 NaN/Infinity）
    json.loads(response.get_data(as_text=True))


def test_scalar_expression_is_broadcast(client):
    response = post_curve(client, expression="5", num_points=10)
    assert response.status_code == 200
    assert response.get_json()["y"] == [5.0] * 10


def test_numeric_strings_are_accepted(client):
    response = post_curve(client, x_min="-1", x_max="1", num_points="20")
    assert response.status_code == 200
    assert len(response.get_json()["x"]) == 20


def test_gaps_detected_for_reciprocal(client):
    response = post_curve(client, expression="1/x", num_points=1000)
    assert response.status_code == 200
    assert response.get_json()["gaps"]


@pytest.mark.parametrize(
    "payload",
    [
        {"expression": "__import__('os').getcwd()"},
        {"expression": "np.load('x')"},
        {"expression": "().__class__.__bases__"},
    ],
)
def test_injection_attempts_are_rejected(client, payload):
    response = client.post("/api/2d-function", json=payload)
    assert response.status_code == 400
    assert response.is_json
    assert "error" in response.get_json()


@pytest.mark.parametrize(
    "overrides",
    [
        {"x_min": 10, "x_max": 10},
        {"x_min": 10, "x_max": -10},
        {"x_min": "abc"},
        {"x_max": None},
        {"x_min": True},
        {"num_points": 9},
        {"num_points": 5001},
        {"num_points": 10.5},
        {"num_points": "abc"},
        {"num_points": True},
        {"expression": ""},
        {"expression": "   "},
        {"expression": 123},
        {"expression": "x + " + "0" * 400},
        {"x_min": -1e308, "x_max": 1e308},
    ],
)
def test_invalid_parameters_return_json_400(client, overrides):
    response = post_curve(client, **overrides)
    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"]


def test_missing_expression(client):
    response = client.post("/api/2d-function", json={"x_min": -1, "x_max": 1})
    assert response.status_code == 400
    assert response.get_json()["error"]


def test_non_json_body(client):
    response = client.post(
        "/api/2d-function", data="not-json", content_type="text/plain"
    )
    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"]


def test_unknown_function(client):
    response = post_curve(client, expression="foo(x)")
    assert response.status_code == 400
    assert response.is_json
    assert "error" in response.get_json()


def test_caret_hint(client):
    response = post_curve(client, expression="x ^ 2")
    assert response.status_code == 400
    assert "**" in response.get_json()["error"]


def test_payload_too_large(client):
    response = client.post(
        "/api/2d-function",
        data="x" * (17 * 1024),
        content_type="application/json",
    )
    assert response.status_code == 413
    assert response.is_json
    assert response.get_json()["error"]


def test_find_discontinuity_gaps_for_asymptote():
    y = np.concatenate(
        [np.linspace(-1, 1, 200), [1000.0], [-1000.0], np.linspace(1, -1, 200)]
    )
    assert find_discontinuity_gaps(y) == [201]


def test_find_discontinuity_gaps_ignores_smooth_curves():
    x = np.linspace(-10, 10, 1000)
    assert find_discontinuity_gaps(np.sin(x)) == []
    assert find_discontinuity_gaps(np.exp(x)) == []
    assert find_discontinuity_gaps(np.linspace(-1, 1, 1000)) == []


def test_find_discontinuity_gaps_for_tan_asymptotes():
    x = np.linspace(-10, 10, 1000)
    assert len(find_discontinuity_gaps(np.tan(x))) == 6
