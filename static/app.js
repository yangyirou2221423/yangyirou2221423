(function () {
    "use strict";

    const API_URL = "/api/2d-function";
    const MAX_FUNCTIONS = 5;
    const SERIES_SLOTS = 8;
    const MIN_POINTS = 10;
    const MAX_POINTS = 5000;
    const REQUEST_TIMEOUT_MS = 15000;
    const THEME_KEY = "mathviz-theme";
    const EXAMPLES = [
        "sin(x)",
        "cos(2*x)",
        "x**2",
        "exp(-x**2)",
        "tan(x)",
        "log(x)",
        "sqrt(abs(x))",
        "sin(x)/x",
        "where(x > 0, x, -x)",
        "sin(pi*x)",
    ];

    const SUN_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"></path></svg>';
    const MOON_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z"></path></svg>';

    const refs = {
        form: document.getElementById("plot-form"),
        functionList: document.getElementById("function-list"),
        addFunction: document.getElementById("add-function"),
        xMin: document.getElementById("x-min"),
        xMax: document.getElementById("x-max"),
        numPoints: document.getElementById("num-points"),
        plotButton: document.getElementById("plot-button"),
        errors: document.getElementById("errors"),
        examples: document.getElementById("examples"),
        chartWrap: document.getElementById("chart-wrap"),
        canvas: document.getElementById("chart"),
        emptyState: document.getElementById("empty-state"),
        chartError: document.getElementById("chart-error"),
        loading: document.getElementById("loading"),
        resetZoom: document.getElementById("reset-zoom"),
        exportPng: document.getElementById("export-png"),
        themeToggle: document.getElementById("theme-toggle"),
        themeIcon: document.getElementById("theme-icon"),
        themeLabel: document.getElementById("theme-label"),
    };

    const state = {
        functions: [],
        nextId: 1,
        chart: null,
        chartReady: false,
        chartBroken: false,
        busy: false,
        drawToken: 0,
        controller: null,
    };

    const themeMedia = window.matchMedia("(prefers-color-scheme: dark)");

    function activeTheme() {
        const explicit = document.documentElement.dataset.theme;
        if (explicit === "light" || explicit === "dark") {
            return explicit;
        }
        return themeMedia.matches ? "dark" : "light";
    }

    function token(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    function seriesColor(slot) {
        return token("--series-" + slot);
    }

    function formatNumber(value) {
        if (value === null || value === undefined || !Number.isFinite(value)) {
            return "—";
        }
        if (value === 0) {
            return "0";
        }
        const absolute = Math.abs(value);
        if (absolute >= 1e6 || absolute < 1e-4) {
            return value.toExponential(3).replace("e+", "e");
        }
        return Number(value.toPrecision(6)).toString();
    }

    function formatTick(value) {
        if (value === 0) {
            return "0";
        }
        const absolute = Math.abs(value);
        if (absolute >= 1e4 || absolute < 1e-2) {
            return value.toExponential(1).replace("e+", "e");
        }
        return Number(value.toPrecision(4)).toString();
    }

    function displayLabel(expression) {
        return expression.length > 42 ? expression.slice(0, 39) + "…" : expression;
    }

    /* ---------- 主题 ---------- */

    function syncTheme() {
        const theme = activeTheme();
        refs.themeIcon.innerHTML = theme === "dark" ? SUN_ICON : MOON_ICON;
        refs.themeLabel.textContent = theme === "dark" ? "浅色" : "深色";
        refs.themeToggle.setAttribute(
            "aria-label",
            theme === "dark" ? "切换到浅色模式" : "切换到深色模式"
        );
        refs.themeToggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");

        if (!state.chart || !state.chartReady) {
            return;
        }
        applyChartTheme(state.chart.options);
        state.chart.data.datasets.forEach((dataset) => {
            const color = seriesColor(dataset._slot);
            dataset.borderColor = color;
            dataset.backgroundColor = color;
            dataset.pointHoverBackgroundColor = color;
            dataset.pointHoverBorderColor = token("--surface");
        });
        state.chart.update("none");
    }

    function applyChartTheme(options) {
        const ink = token("--ink-secondary");
        const muted = token("--ink-muted");
        const grid = token("--grid");

        options.color = ink;
        options.plugins.legend.labels.color = ink;
        options.plugins.tooltip.backgroundColor = token("--surface-raised");
        options.plugins.tooltip.titleColor = token("--ink");
        options.plugins.tooltip.bodyColor = ink;
        options.plugins.tooltip.borderColor = token("--border");
        options.scales.x.grid.color = grid;
        options.scales.y.grid.color = grid;
        options.scales.x.ticks.color = muted;
        options.scales.y.ticks.color = muted;
        options.scales.x.title.color = muted;
        options.scales.y.title.color = muted;
    }

    /* ---------- Chart.js ---------- */

    const surfaceBackground = {
        id: "surfaceBackground",
        beforeDraw(chart) {
            const { ctx, width, height } = chart;
            ctx.save();
            ctx.globalCompositeOperation = "destination-over";
            ctx.fillStyle = token("--surface");
            ctx.fillRect(0, 0, width, height);
            ctx.restore();
        },
    };

    const zeroAxes = {
        id: "zeroAxes",
        beforeDatasetsDraw(chart) {
            const { ctx, chartArea, scales } = chart;
            if (!chartArea || !scales.x || !scales.y) {
                return;
            }
            const xZero = scales.x.getPixelForValue(0);
            const yZero = scales.y.getPixelForValue(0);
            ctx.save();
            ctx.strokeStyle = token("--axis");
            ctx.lineWidth = 1;
            if (xZero >= chartArea.left && xZero <= chartArea.right) {
                ctx.beginPath();
                ctx.moveTo(xZero, chartArea.top);
                ctx.lineTo(xZero, chartArea.bottom);
                ctx.stroke();
            }
            if (yZero >= chartArea.top && yZero <= chartArea.bottom) {
                ctx.beginPath();
                ctx.moveTo(chartArea.left, yZero);
                ctx.lineTo(chartArea.right, yZero);
                ctx.stroke();
            }
            ctx.restore();
        },
    };

    const crosshair = {
        id: "crosshair",
        afterDatasetsDraw(chart) {
            const active =
                chart.tooltip && typeof chart.tooltip.getActiveElements === "function"
                    ? chart.tooltip.getActiveElements()
                    : [];
            if (!active.length) {
                return;
            }
            const { ctx, chartArea } = chart;
            const x = active[0].element.x;
            ctx.save();
            ctx.strokeStyle = token("--axis");
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, chartArea.top);
            ctx.lineTo(x, chartArea.bottom);
            ctx.stroke();
            ctx.restore();
        },
    };

    function setupChartLibrary() {
        if (typeof window.Chart === "undefined") {
            state.chartBroken = true;
            refs.chartError.hidden = false;
            refs.chartError.textContent = "图表库加载失败，请检查网络连接后刷新页面。";
            refs.plotButton.disabled = true;
            refs.loading.hidden = true;
            return false;
        }
        const zoomPlugin = window.ChartZoom || window.zoomPlugin;
        if (zoomPlugin) {
            window.Chart.register(zoomPlugin);
        }
        window.Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
        state.chartReady = true;
        return true;
    }

    function createOptions() {
        const options = {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            parsing: false,
            normalized: true,
            interaction: { mode: "index", intersect: false, axis: "x" },
            plugins: {
                legend: {
                    display: false,
                    position: "top",
                    align: "start",
                    labels: {
                        usePointStyle: true,
                        pointStyle: "line",
                        boxWidth: 28,
                        boxHeight: 10,
                        padding: 16,
                        font: { size: 12 },
                    },
                },
                tooltip: {
                    displayColors: true,
                    usePointStyle: true,
                    padding: 10,
                    cornerRadius: 8,
                    borderWidth: 1,
                    titleFont: { size: 11, weight: "600" },
                    bodyFont: { size: 12 },
                    callbacks: {
                        title(items) {
                            if (!items.length) {
                                return "";
                            }
                            return "x = " + formatNumber(items[0].parsed.x);
                        },
                        label(item) {
                            const name = item.dataset._expression || item.dataset.label;
                            return name + "   y = " + formatNumber(item.parsed.y);
                        },
                    },
                },
                zoom: {
                    limits: {
                        x: { minRange: 1e-12 },
                        y: { minRange: 1e-12 },
                    },
                    pan: { enabled: true, mode: "xy" },
                    zoom: {
                        wheel: { enabled: true, speed: 0.1 },
                        pinch: { enabled: true },
                        mode: "xy",
                    },
                },
            },
            scales: {
                x: {
                    type: "linear",
                    grid: { color: "#e1e0d9", lineWidth: 1, drawTicks: false },
                    border: { display: false },
                    ticks: {
                        maxTicksLimit: 8,
                        includeBounds: false,
                        padding: 8,
                        font: { size: 11 },
                        callback: (value) => formatTick(value),
                    },
                    title: { display: true, text: "x", font: { size: 11 } },
                },
                y: {
                    type: "linear",
                    grid: { color: "#e1e0d9", lineWidth: 1, drawTicks: false },
                    border: { display: false },
                    ticks: {
                        maxTicksLimit: 7,
                        includeBounds: false,
                        padding: 8,
                        font: { size: 11 },
                        callback: (value) => formatTick(value),
                    },
                    title: { display: true, text: "y", font: { size: 11 } },
                },
            },
        };
        applyChartTheme(options);
        return options;
    }

    function buildDataset(row, payload) {
        const gaps = new Set(Array.isArray(payload.gaps) ? payload.gaps : []);
        const points = new Array(payload.x.length);
        for (let index = 0; index < payload.x.length; index += 1) {
            const raw = payload.y[index];
            const isGap = gaps.has(index) || typeof raw !== "number" || !Number.isFinite(raw);
            points[index] = { x: payload.x[index], y: isGap ? null : raw };
        }
        const color = seriesColor(row.slot);
        return {
            label: displayLabel(row.expression),
            _expression: row.expression,
            _slot: row.slot,
            data: points,
            borderColor: color,
            backgroundColor: color,
            borderWidth: 2,
            borderJoinStyle: "round",
            borderCapStyle: "round",
            pointRadius: 0,
            pointHoverRadius: 4,
            pointHoverBorderWidth: 2,
            pointHoverBorderColor: token("--surface"),
            pointHoverBackgroundColor: color,
            pointHitRadius: 16,
            tension: 0,
            spanGaps: false,
            fill: false,
        };
    }

    function renderChart(datasets) {
        if (!state.chartReady) {
            return;
        }
        if (!state.chart) {
            state.chart = new window.Chart(refs.canvas, {
                type: "line",
                data: { datasets },
                options: createOptions(),
                plugins: [surfaceBackground, zeroAxes, crosshair],
            });
        } else {
            if (typeof state.chart.resetZoom === "function") {
                state.chart.resetZoom("none");
            }
            state.chart.data.datasets = datasets;
        }
        applyDataBounds(datasets);
        state.chart.options.plugins.legend.display = datasets.length > 1;
        state.chart.update("none");
        updateEmptyState(datasets.length === 0);
        updateToolbar();
    }

    function applyDataBounds(datasets) {
        let xMin = Infinity;
        let xMax = -Infinity;
        let yMin = Infinity;
        let yMax = -Infinity;

        datasets.forEach((dataset) => {
            dataset.data.forEach((point) => {
                if (Number.isFinite(point.x)) {
                    xMin = Math.min(xMin, point.x);
                    xMax = Math.max(xMax, point.x);
                }
                if (Number.isFinite(point.y)) {
                    yMin = Math.min(yMin, point.y);
                    yMax = Math.max(yMax, point.y);
                }
            });
        });

        const xScale = state.chart.options.scales.x;
        const yScale = state.chart.options.scales.y;

        if (Number.isFinite(xMin) && Number.isFinite(xMax) && xMax >= xMin) {
            const xPad = xMax > xMin ? (xMax - xMin) * 0.02 : 1;
            xScale.min = xMin - xPad;
            xScale.max = xMax + xPad;
        } else {
            xScale.min = -10;
            xScale.max = 10;
        }

        if (Number.isFinite(yMin) && Number.isFinite(yMax) && yMax >= yMin) {
            const span = yMax - yMin;
            const yPad =
                Number.isFinite(span) && span > 0
                    ? span * 0.08
                    : Math.max(Math.abs(yMax) * 0.2, 0.5);
            yScale.min = yMin - yPad;
            yScale.max = yMax + yPad;
        } else {
            yScale.min = -1;
            yScale.max = 1;
        }
    }

    function updateEmptyState(isEmpty) {
        refs.emptyState.hidden = !isEmpty;
        if (isEmpty) {
            refs.emptyState.textContent = "没有可绘制的曲线";
        }
    }

    function updateToolbar() {
        const hasCurves = Boolean(
            state.chart && state.chart.data.datasets && state.chart.data.datasets.length > 0
        );
        refs.exportPng.disabled = !hasCurves;
        refs.resetZoom.disabled =
            !hasCurves ||
            !state.chart ||
            typeof state.chart.resetZoom !== "function";
    }

    /* ---------- 函数列表 ---------- */

    function createFunction(expression) {
        if (state.functions.length >= MAX_FUNCTIONS) {
            return null;
        }
        const used = new Set(state.functions.map((fn) => fn.slot));
        let slot = 1;
        while (slot <= SERIES_SLOTS && used.has(slot)) {
            slot += 1;
        }
        if (slot > SERIES_SLOTS) {
            slot = 1;
        }
        const fn = { id: state.nextId, expression: expression || "", slot };
        state.nextId += 1;
        state.functions.push(fn);
        renderFunctions();
        return fn;
    }

    function renderFunctions() {
        refs.functionList.textContent = "";
        state.functions.forEach((fn, index) => {
            const item = document.createElement("li");
            item.className = "function-row";
            item.dataset.id = String(fn.id);

            const key = document.createElement("span");
            key.className = "line-key";
            key.style.setProperty("--line-color", "var(--series-" + fn.slot + ")");
            key.setAttribute("aria-hidden", "true");

            const input = document.createElement("input");
            input.type = "text";
            input.className = "function-input";
            input.value = fn.expression;
            input.placeholder = "例如 sin(x)";
            input.maxLength = 300;
            input.spellcheck = false;
            input.autocomplete = "off";
            input.setAttribute("aria-label", "函数表达式 " + (index + 1));
            input.addEventListener("input", () => {
                fn.expression = input.value;
            });
            input.addEventListener("keydown", (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    draw();
                }
            });

            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "icon-button remove-function";
            remove.textContent = "×";
            remove.setAttribute("aria-label", "删除函数 " + (index + 1));
            remove.disabled = state.functions.length <= 1 || state.busy;
            remove.addEventListener("click", () => removeFunction(fn.id));

            item.append(key, input, remove);
            refs.functionList.append(item);
        });

        refs.addFunction.disabled = state.busy || state.functions.length >= MAX_FUNCTIONS;
        refs.addFunction.textContent =
            state.functions.length >= MAX_FUNCTIONS ? "已达上限" : "＋ 添加函数";
    }

    function removeFunction(id) {
        if (state.functions.length <= 1) {
            return;
        }
        state.functions = state.functions.filter((fn) => fn.id !== id);
        renderFunctions();
    }

    function findTargetFunction() {
        const active = document.activeElement;
        if (active && active.classList.contains("function-input")) {
            const item = active.closest(".function-row");
            const id = Number(item && item.dataset.id);
            const focused = state.functions.find((fn) => fn.id === id);
            if (focused) {
                return focused;
            }
        }
        const empty = state.functions.find((fn) => !fn.expression.trim());
        if (empty) {
            return empty;
        }
        if (state.functions.length < MAX_FUNCTIONS) {
            return createFunction("");
        }
        return state.functions[state.functions.length - 1] || null;
    }

    function renderExamples() {
        EXAMPLES.forEach((expression) => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "example-chip";
            chip.textContent = expression;
            chip.title = "填入此表达式并绘制";
            chip.addEventListener("click", () => {
                const target = findTargetFunction();
                if (!target) {
                    return;
                }
                target.expression = expression;
                renderFunctions();
                draw();
            });
            refs.examples.append(chip);
        });
    }

    /* ---------- 绘制 ---------- */

    function readParameters() {
        const messages = [];
        const xMin = Number.parseFloat(refs.xMin.value);
        const xMax = Number.parseFloat(refs.xMax.value);
        const numPoints = Number(refs.numPoints.value.trim());

        if (!Number.isFinite(xMin)) {
            messages.push("X 轴最小值必须是数字");
        }
        if (!Number.isFinite(xMax)) {
            messages.push("X 轴最大值必须是数字");
        }
        if (Number.isFinite(xMin) && Number.isFinite(xMax) && xMin >= xMax) {
            messages.push("X 轴最小值必须小于最大值");
        }
        if (!Number.isInteger(numPoints) || numPoints < MIN_POINTS || numPoints > MAX_POINTS) {
            messages.push("采样点数必须是 " + MIN_POINTS + " 到 " + MAX_POINTS + " 之间的整数");
        }

        const rows = state.functions
            .map((fn) => ({ ...fn, expression: fn.expression.trim() }))
            .filter((fn) => fn.expression.length > 0);

        if (rows.length === 0) {
            messages.push("请至少输入一个函数表达式");
        }
        rows.forEach((row) => {
            if (row.expression.length > 300) {
                messages.push("「" + row.expression.slice(0, 20) + "…」超过 300 个字符");
            }
        });

        return { messages, xMin, xMax, numPoints, rows };
    }

    async function requestCurve(expression, xMin, xMax, numPoints, signal) {
        const timeoutSignal =
            typeof AbortSignal.timeout === "function"
                ? AbortSignal.timeout(REQUEST_TIMEOUT_MS)
                : null;
        const requestSignal =
            timeoutSignal && typeof AbortSignal.any === "function"
                ? AbortSignal.any([signal, timeoutSignal])
                : signal;

        let response;
        try {
            response = await fetch(API_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    expression,
                    x_min: xMin,
                    x_max: xMax,
                    num_points: numPoints,
                }),
                signal: requestSignal,
            });
        } catch (error) {
            if (error && error.name === "AbortError") {
                throw error;
            }
            if (error && error.name === "TimeoutError") {
                throw new Error("请求超时，请稍后重试");
            }
            throw new Error("无法连接服务器，请确认 Flask 服务正在运行");
        }

        let payload = null;
        try {
            payload = await response.json();
        } catch (error) {
            payload = null;
        }

        if (!response.ok) {
            throw new Error(
                payload && payload.error ? payload.error : "请求失败（HTTP " + response.status + "）"
            );
        }
        if (
            !payload ||
            !Array.isArray(payload.x) ||
            !Array.isArray(payload.y) ||
            payload.x.length !== payload.y.length
        ) {
            throw new Error("服务器返回了意外的数据");
        }
        return payload;
    }

    async function draw() {
        if (state.chartBroken) {
            return;
        }
        clearErrors();
        const params = readParameters();
        if (params.messages.length > 0) {
            showErrors(params.messages);
            return;
        }

        const drawToken = state.drawToken + 1;
        state.drawToken = drawToken;
        if (state.controller) {
            state.controller.abort();
        }
        const controller = new AbortController();
        state.controller = controller;

        setBusy(true);
        const settled = await Promise.allSettled(
            params.rows.map((row) =>
                requestCurve(
                    row.expression,
                    params.xMin,
                    params.xMax,
                    params.numPoints,
                    controller.signal
                ).then((payload) => ({ row, payload }))
            )
        );

        if (drawToken !== state.drawToken) {
            return;
        }
        state.controller = null;
        setBusy(false);

        const datasets = [];
        const messages = [];
        settled.forEach((result, index) => {
            if (result.status === "fulfilled") {
                const { row, payload } = result.value;
                const hasValue = payload.y.some(
                    (value) => typeof value === "number" && Number.isFinite(value)
                );
                if (!hasValue) {
                    messages.push("「" + row.expression + "」：在所选范围内没有可绘制的点");
                    return;
                }
                datasets.push(buildDataset(row, payload));
                return;
            }
            const reason = result.reason;
            if (reason && reason.name === "AbortError") {
                return;
            }
            const row = params.rows[index];
            messages.push(
                "「" + row.expression + "」：" + (reason && reason.message ? reason.message : "请求失败")
            );
        });

        showErrors(messages);
        renderChart(datasets);
    }

    /* ---------- 界面状态 ---------- */

    function setBusy(busy) {
        state.busy = busy;
        refs.plotButton.disabled = busy;
        refs.plotButton.textContent = busy ? "绘制中…" : "绘制图像";
        refs.chartWrap.classList.toggle("is-loading", busy);
        refs.loading.hidden = !busy;
        refs.addFunction.disabled = busy || state.functions.length >= MAX_FUNCTIONS;
        refs.functionList.querySelectorAll(".remove-function").forEach((button) => {
            button.disabled = busy || state.functions.length <= 1;
        });
    }

    function clearErrors() {
        showErrors([]);
    }

    function showErrors(messages) {
        const box = refs.errors;
        box.textContent = "";
        if (!messages.length) {
            box.hidden = true;
            return;
        }

        const title = document.createElement("p");
        title.className = "errors__title";
        title.textContent = "无法绘制";
        box.append(title);

        messages.forEach((message) => {
            const item = document.createElement("p");
            item.className = "error-item";

            const mark = document.createElement("span");
            mark.className = "error-mark";
            mark.setAttribute("aria-hidden", "true");
            mark.textContent = "!";

            const text = document.createElement("span");
            text.textContent = message;

            item.append(mark, text);
            box.append(item);
        });
        box.hidden = false;
    }

    function exportPng() {
        if (!state.chart || state.chart.data.datasets.length === 0) {
            return;
        }
        const link = document.createElement("a");
        const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
        link.download = "函数图像-" + stamp + ".png";
        link.href = state.chart.toBase64Image("image/png", 1);
        link.click();
    }

    /* ---------- 事件与初始化 ---------- */

    function bindEvents() {
        refs.form.addEventListener("submit", (event) => {
            event.preventDefault();
            draw();
        });

        refs.addFunction.addEventListener("click", () => {
            const fn = createFunction("");
            if (!fn) {
                return;
            }
            const inputs = refs.functionList.querySelectorAll(".function-input");
            const last = inputs[inputs.length - 1];
            if (last) {
                last.focus();
            }
        });

        refs.resetZoom.addEventListener("click", () => {
            if (state.chart && typeof state.chart.resetZoom === "function") {
                state.chart.resetZoom();
            }
        });

        refs.exportPng.addEventListener("click", exportPng);

        refs.themeToggle.addEventListener("click", () => {
            const next = activeTheme() === "dark" ? "light" : "dark";
            document.documentElement.dataset.theme = next;
            try {
                localStorage.setItem(THEME_KEY, next);
            } catch (error) {
                /* 忽略存储失败 */
            }
            syncTheme();
        });

        const onSystemThemeChange = () => {
            if (!document.documentElement.dataset.theme) {
                syncTheme();
            }
        };
        if (typeof themeMedia.addEventListener === "function") {
            themeMedia.addEventListener("change", onSystemThemeChange);
        } else if (typeof themeMedia.addListener === "function") {
            themeMedia.addListener(onSystemThemeChange);
        }
    }

    function init() {
        syncTheme();
        bindEvents();
        renderExamples();
        createFunction("sin(x)");
        if (setupChartLibrary()) {
            draw();
        }
        updateToolbar();
    }

    init();
})();
