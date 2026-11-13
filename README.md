# 函数图像 · 数学可视化

一个基于 Flask、NumPy 和 Chart.js 的交互式二维函数可视化工具。输入数学表达式即可绘制曲线，支持多函数叠加、缩放平移和导出图片。

## 功能

- 输入任意受支持的数学表达式，自动采样并绘制二维曲线
- 最多同时叠加 5 条函数曲线，颜色稳定、图例清晰
- 自定义 X 轴范围与采样点数（10–5000）
- 滚轮缩放、拖拽平移、一键重置视图
- 导出当前图像为 PNG（背景不透明，深浅色主题自适应）
- 深色 / 浅色主题，跟随系统并可手动切换
- 定义域外（如 `log` 的负半轴）自动断开，渐近线处保守断点
- 服务端白名单求值，不使用 `eval`，拒绝任意代码执行
- 响应式布局，支持键盘操作与行内错误提示

## 技术栈

- 后端：Python 3.10+、Flask 3、NumPy
- 前端：原生 HTML / CSS / JavaScript、Chart.js 4、chartjs-plugin-zoom 2
- 图表库通过 jsDelivr 加载，使用 SRI 校验并锁定版本

## 快速开始

1. 创建并激活虚拟环境：

   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

   macOS / Linux 使用 `source .venv/bin/activate`。

2. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

3. 启动服务：

   ```bash
   python app.py
   ```

4. 打开浏览器访问 <http://127.0.0.1:5000>。

开发时可以开启调试模式：

```bash
FLASK_DEBUG=1 python app.py
```

Windows PowerShell 使用 `$env:FLASK_DEBUG=1; python app.py`。服务默认只监听 `127.0.0.1`，可通过 `PORT` 环境变量修改端口。

## 表达式语法

- 变量：`x`
- 运算符：`+ - * / // % **`
- 比较：`> < >= <= == !=`，用 `&`、`|`、`~` 组合条件
- 常量：`pi`、`e`、`tau`（也支持 `π`、`×`、`÷`、`−` 等符号）
- 函数：`sin cos tan asin acos atan atan2 sinh cosh tanh asinh acosh atanh exp expm1 log log1p log2 log10 sqrt cbrt abs sign floor ceil round trunc rint square power hypot degrees radians minimum maximum clip where mod remainder`
- 函数可以写成 `sin(x)`，也可以写成 `np.sin(x)`

示例：

| 表达式 | 说明 |
|---|---|
| `sin(x)` | 正弦曲线 |
| `x**2` | 二次函数（乘方用 `**`，不支持 `^`） |
| `exp(-x**2)` | 高斯函数 |
| `sin(x)/x` | 在 0 处自动断开 |
| `tan(x)` | 渐近线处断线 |
| `log(x)` | 只在定义域内绘制 |
| `where(x > 0, x, -x)` | 分段函数 |
| `(x > -1) & (x < 1)` | 条件表达式，结果为 0 / 1 |

限制：表达式最多 300 个字符；不支持复数、隐函数、参数方程和三维曲面。

## API

### `POST /api/2d-function`

请求体：

```json
{
  "expression": "sin(x)",
  "x_min": -10,
  "x_max": 10,
  "num_points": 1000
}
```

- `expression`：必填，字符串，最多 300 字符
- `x_min` / `x_max`：可选，有限数字，必须满足 `x_min < x_max`
- `num_points`：可选，10–5000 的整数

成功响应（`200`）：

```json
{
  "expression": "sin(x)",
  "x": [-10, -9.98, "..."],
  "y": [-0.544, -0.723, "..."],
  "gaps": [],
  "num_points": 1000
}
```

- `y` 中无法计算的点（`NaN` / `±Infinity`）以 `null` 返回，保证 JSON 合法
- `gaps` 是断点索引，表示曲线应在第 `i-1` 与第 `i` 个点之间断开

错误响应（`400` / `413` / `500`）：

```json
{ "error": "面向用户的中文错误说明" }
```

服务端限制请求体最大 16 KB。

## 测试

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

测试覆盖安全求值器（注入载荷、长度与复杂度限制）、API 参数校验、`NaN` 序列化、标量广播以及断点检测。

## 项目结构

```
app.py                  Flask 应用、参数校验、断点检测
safe_eval.py            AST 白名单数学表达式求值器
templates/index.html    页面结构
static/style.css        样式与主题令牌
static/app.js           图表、交互、主题与请求逻辑
tests/                  pytest 测试
requirements.txt        运行依赖
requirements-dev.txt    开发依赖
```

## 安全说明

- 表达式由 `safe_eval.py` 解析为 AST，只允许白名单内的节点、函数和常量，**不调用 `eval`**
- 不允许属性链、下标、lambda、推导式、关键字参数等语法，也无法访问 `__builtins__`
- 对表达式长度、AST 节点深度与数量、采样点数、请求体大小均设置上限
- 已移除全开放 CORS 与生产式的 `debug=True`
- 本项目面向本地使用，不建议直接暴露到公网；如需部署请使用生产级 WSGI 服务器并置于反向代理之后
