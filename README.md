# Flask 数学可视化项目
一个基于 Flask 和 Chart.js 的交互式二维数学函数可视化工具。

## 功能介绍
- 提供本地 Web 服务，可通过浏览器访问
- 支持输入任意 NumPy 函数表达式，自动计算坐标点
- 前端动态绘制函数图像，可自定义 X 轴范围
- 已实现完整的前后端交互

## 运行方法
1.  确保已安装 Python 3.13+，并创建虚拟环境：
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install flask flask-cors numpy
    ```
2.  运行项目：
    ```bash
    python app.py
    ```
3.  打开浏览器访问 `http://127.0.0.1:5000`，即可使用可视化工具。
