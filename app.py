from flask import Flask, request, jsonify,render_template
import numpy as np
from flask_cors import CORS  # 引入跨域支持

app = Flask(__name__)
CORS(app)  # 允许跨域请求，方便前端页面调用

# 首页
@app.route('/')
def hello():
    return render_template('index.html')

# 二维函数计算接口
@app.route('/api/2d-function', methods=['POST'])
def compute_2d():
    try:
        # 从请求中获取参数
        data = request.get_json()
        expr = data.get('expression')  # 比如 "np.sin(x)"
        x_min = data.get('x_min', -10)
        x_max = data.get('x_max', 10)
        num_points = data.get('num_points', 1000)

        # 生成x轴数据
        x = np.linspace(x_min, x_max, num_points)

        # 安全执行表达式，只允许使用np和x变量
        allowed_globals = {'np': np}
        y = eval(expr, allowed_globals, {'x': x})

        # 把numpy数组转为Python列表，方便JSON序列化
        return jsonify({
            'x': x.tolist(),
            'y': y.tolist()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
