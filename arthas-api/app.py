"""
Arthas 注入 + 诊断命令 API 服务（Flask 版）
对应需求文档：
    - 3.1  Arthas 工具注入 API
    - 3.2  4 类诊断命令 API
统一返回格式：{code, msg, data}

运行方式（二选一）：
    1) python app.py                      （Werkzeug 开发服务器，最简单）
    2) flask --app app run --port 8000    （flask 命令）
"""
from diagnose import (
    extract_uris,
    filter_match_method,
    has_match,
    match_business_method,
    monitor_class,
    run_with_auto_traffic,
    trace_method,
    watch_slow_requests,
)
from flask import Flask, jsonify, render_template, request
from injector import copy_arthas_to_pod, start_arthas
from kubectl_utils import list_pods

# 创建 Flask 应用
app = Flask(__name__)
# 让返回 JSON 里的中文直接以 UTF-8 显示（不转成 \uXXXX）
app.json.ensure_ascii = False


# ---------- 统一返回格式 ----------
def ok(data=None, msg="成功"):
    """成功返回：code=200"""
    return {"code": 200, "msg": msg, "data": data}


def fail(msg):
    """失败返回：code=500"""
    return {"code": 500, "msg": msg, "data": None}


TRAFFIC_DEFAULTS = {"auto_traffic": False, "traffic_path": "/slow", "traffic_port": 8080}


def maybe_auto_traffic(pod, params, func, duration=45, default_path="/slow"):
    """若请求里开了 auto_traffic，则后台自动给该 Pod 打流量，同时执行 func(pod)。

    这样用户点一下监控接口就能自动抓到数据，不用手动另开终端打流量。
    """
    if not params.get("auto_traffic"):
        return func(pod)
    path = params.get("traffic_path") or default_path
    port = int(params.get("traffic_port", 8080))
    return run_with_auto_traffic(
        pod, func, params["namespace"],
        traffic_path=path, traffic_port=port, duration=duration,
    )


def resolve_pods(pod, namespace="default"):
    """把 pod 参数统一成列表；不填则取命名空间下所有 Pod。

    支持三种填法：
        - 不填           -> 该命名空间下所有 Pod
        - "podA"         -> 单个 Pod
        - ["podA","podB"] -> 批量
    """
    if pod is None or pod == "":
        return list_pods(namespace)
    if isinstance(pod, str):
        return [pod]
    return list(pod)


# ---------- 请求体解析（替代 FastAPI 的 Pydantic 模型） ----------
def read_params(required=(), defaults=None):
    """解析 JSON 请求体。

    required: 必填字段元组，缺失时返回错误响应
    defaults: 可选字段的默认值字典 {字段: 默认值}
    返回:
        (params_dict, None)            正常
        (None, error_response_dict)    缺必填参数
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}

    params = {}
    if defaults:
        for k, v in defaults.items():
            params[k] = body.get(k, v)
    for r in required:
        if r not in body:
            return None, fail(f"缺少必填参数: {r}")
        params[r] = body[r]
    return params, None


# ---------- 注入 API（需求文档 3.1） ----------
@app.route("/inject", methods=["POST"])
def inject():
    """对指定命名空间下的 Pod 执行注入（拷文件 + attach）。

    入参：{region, cluster, account, namespace(必填), pod[], copy_path}
    若未指定 pod，则默认注入该命名空间下所有 Pod。
    """
    params, err = read_params(
        required=("namespace",),
        defaults={"region": "", "cluster": "", "account": "",
                  "pod": None, "copy_path": "/tmp/arthas"},
    )
    if err:
        return jsonify(err)

    try:
        pod_list = params["pod"]
        if not pod_list:
            pod_list = list_pods(params["namespace"])
            if not pod_list:
                return jsonify(fail(f"命名空间 {params['namespace']} 下没有可注入的 Pod"))

        # 需求 6：单批次最多支持 50 个 Pod
        if len(pod_list) > 50:
            return jsonify(fail("单批次最多支持 50 个 Pod"))

        results = []
        for pod_name in pod_list:
            copy_arthas_to_pod(pod_name, params["namespace"], params["copy_path"])  # ① 拷文件
            start_arthas(pod_name, params["namespace"], params["copy_path"])        # ② 启动+attach
            results.append({"pod": pod_name, "status": "注入成功"})

        return jsonify(ok({
            "region": params["region"], "cluster": params["cluster"],
            "account": params["account"], "copy_path": params["copy_path"],
            "results": results,
        }, "注入成功"))
    except Exception as e:
        return jsonify(fail(f"注入失败: {e}"))


# ---------- 4 个诊断 API（需求文档 3.2） ----------
@app.route("/diagnose/slow-requests", methods=["POST"])
def diag_slow_requests():
    """接口1: 查询耗时超过阈值的请求路径（支持批量，返回每 Pod 独立结果）"""
    params, err = read_params(
        required=("cost_time",),
        defaults={"namespace": "default", "pod": None, "copy_path": "/tmp/arthas",
                  **TRAFFIC_DEFAULTS},
    )
    if err:
        return jsonify(err)

    try:
        pod_list = resolve_pods(params["pod"], params["namespace"])
        if not pod_list:
            return jsonify(fail(f"命名空间 {params['namespace']} 下没有可操作的 Pod"))

        results = []
        for pod in pod_list:
            try:
                def _run(p):
                    return watch_slow_requests(p, params["cost_time"],
                                               params["namespace"], params["copy_path"])
                data = maybe_auto_traffic(pod, params, _run, duration=40)
                results.append({"pod": pod,
                                "result": data if has_match(data) else "无匹配耗时请求"})
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})
        return jsonify(ok(results))
    except Exception as e:
        return jsonify(fail(f"查询失败: {e}"))


@app.route("/diagnose/match-method", methods=["POST"])
def diag_match_method():
    """接口2: 根据请求路径匹配业务类与方法（支持批量，返回每 Pod 独立结果）"""
    params, err = read_params(
        required=("request_uri",),
        defaults={"namespace": "default", "pod": None, "copy_path": "/tmp/arthas",
                  **TRAFFIC_DEFAULTS},
    )
    if err:
        return jsonify(err)

    try:
        pod_list = resolve_pods(params["pod"], params["namespace"])
        if not pod_list:
            return jsonify(fail(f"命名空间 {params['namespace']} 下没有可操作的 Pod"))

        results = []
        for pod in pod_list:
            try:
                def _run(p):
                    return match_business_method(p, params["request_uri"],
                                                 params["namespace"], params["copy_path"])
                # 匹配方法默认就打目标 URI 的流量（如 /slow），命中率最高
                data = maybe_auto_traffic(pod, params, _run, duration=40,
                                          default_path=params["request_uri"])
                matched = filter_match_method(data, params["request_uri"])
                if matched:
                    results.append({"pod": pod, "result": matched})
                else:
                    results.append({"pod": pod,
                                    "result": f"未匹配到请求路径 {params['request_uri']} "
                                              f"对应的业务方法（确认该路径有实际请求流量）"})
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})
        return jsonify(ok(results))
    except Exception as e:
        return jsonify(fail(f"匹配失败: {e}"))


@app.route("/diagnose/trace", methods=["POST"])
def diag_trace():
    """接口3: 追踪方法内部调用栈耗时（支持批量，返回每 Pod 独立结果）"""
    params, err = read_params(
        required=("class_name", "method_name", "cost_time"),
        defaults={"namespace": "default", "pod": None, "copy_path": "/tmp/arthas",
                  **TRAFFIC_DEFAULTS},
    )
    if err:
        return jsonify(err)

    try:
        pod_list = resolve_pods(params["pod"], params["namespace"])
        if not pod_list:
            return jsonify(fail(f"命名空间 {params['namespace']} 下没有可操作的 Pod"))

        results = []
        for pod in pod_list:
            try:
                def _run(p):
                    return trace_method(p, params["class_name"], params["method_name"],
                                        params["cost_time"],
                                        params["namespace"], params["copy_path"])
                data = maybe_auto_traffic(pod, params, _run, duration=40)
                results.append({"pod": pod,
                                "result": data if has_match(data) else "无匹配耗时请求/方法"})
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})
        return jsonify(ok(results))
    except Exception as e:
        return jsonify(fail(f"追踪失败: {e}"))


@app.route("/diagnose/monitor", methods=["POST"])
def diag_monitor():
    """接口4: 统计类下所有方法性能（支持批量，返回每 Pod 独立结果）"""
    params, err = read_params(
        required=("class_name",),
        defaults={"namespace": "default", "pod": None, "copy_path": "/tmp/arthas",
                  "cycle": 10, **TRAFFIC_DEFAULTS},
    )
    if err:
        return jsonify(err)

    try:
        pod_list = resolve_pods(params["pod"], params["namespace"])
        if not pod_list:
            return jsonify(fail(f"命名空间 {params['namespace']} 下没有可操作的 Pod"))

        results = []
        for pod in pod_list:
            try:
                def _run(p):
                    return monitor_class(p, params["class_name"], params["cycle"],
                                         params["namespace"], params["copy_path"])
                data = maybe_auto_traffic(pod, params, _run, duration=params["cycle"] + 15)
                results.append({"pod": pod,
                                "result": data if has_match(data) else "无匹配耗时请求/方法"})
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})
        return jsonify(ok(results))
    except Exception as e:
        return jsonify(fail(f"统计失败: {e}"))


@app.route("/diagnose/chain", methods=["POST"])
def diag_chain():
    """完整排查链路: 慢接口 -> 绑方法（支持批量，返回每 Pod 独立结果）

    注意：链路依赖真实 Web 应用 + 真实慢请求流量才能捕获到数据。
    """
    params, err = read_params(
        required=("cost_time",),
        defaults={"namespace": "default", "pod": None, "copy_path": "/tmp/arthas",
                  **TRAFFIC_DEFAULTS},
    )
    if err:
        return jsonify(err)

    try:
        pod_list = resolve_pods(params["pod"], params["namespace"])
        if not pod_list:
            return jsonify(fail(f"命名空间 {params['namespace']} 下没有可操作的 Pod"))

        results = []
        for pod in pod_list:
            try:
                def _chain(p):
                    # ① 查慢接口
                    slow_output = watch_slow_requests(p, params["cost_time"],
                                                      params["namespace"], params["copy_path"])
                    uris = extract_uris(slow_output)

                    # ② 对每个慢接口 URI，匹配对应的业务类与方法
                    methods = []
                    for uri in uris:
                        try:
                            m = match_business_method(p, uri,
                                                      params["namespace"], params["copy_path"])
                            matched = filter_match_method(m, uri)
                            methods.append({"uri": uri, "match": matched})
                        except Exception as e:
                            methods.append({"uri": uri, "match": f"匹配失败: {e}"})

                    return {"pod": p, "uris": uris, "methods": methods}

                chain_result = maybe_auto_traffic(pod, params, _chain, duration=70)
                results.append(chain_result)
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})

        return jsonify(ok(results, "链路排查完成"))
    except Exception as e:
        return jsonify(fail(f"链路排查失败: {e}"))


# ---------- 首页 & 交互式控制台 & 简易接口说明 ----------
@app.route("/", methods=["GET"])
def root():
    """首页：提示控制台地址"""
    return jsonify({"service": "Arthas 注入 + 诊断 API 服务 (Flask)",
                    "console": "/ui", "docs": "/docs"})


@app.route("/ui", methods=["GET"])
def ui():
    """交互式网页控制台：填参数点按钮调接口（不用手动敲 curl）"""
    return render_template("ui.html")


@app.route("/docs", methods=["GET"])
def docs():
    """简易接口文档（Flask 没有 FastAPI 的自动 Swagger，这里手写一页）"""
    html = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>接口文档</title>
<style>body{font-family:Consolas,monospace;margin:30px}h3{color:#333}code{background:#f4f4f4;padding:2px 5px}</style>
</head><body>
<h2>Arthas 注入 + 诊断 API（Flask 版）</h2>
<p>统一返回格式：<code>{code, msg, data}</code>，code=200 成功 / 500 失败。所有请求体为 JSON。</p>
<h3>1. 注入</h3><p><code>POST /inject</code>　body: <code>{"namespace":必填, "pod":[], "copy_path":"/tmp/arthas"}</code></p>
<h3>2. 慢接口查询</h3><p><code>POST /diagnose/slow-requests</code>　body: <code>{"cost_time":1000, "pod":"x"}</code></p>
<h3>3. 匹配业务方法</h3><p><code>POST /diagnose/match-method</code>　body: <code>{"request_uri":"/slow"}</code></p>
<h3>4. 方法耗时栈追踪</h3><p><code>POST /diagnose/trace</code>　body: <code>{"class_name":"com.x.Demo","method_name":"slow","cost_time":0}</code></p>
<h3>5. 方法性能统计</h3><p><code>POST /diagnose/monitor</code>　body: <code>{"class_name":"com.x.Demo","cycle":10}</code></p>
<h3>6. 完整排查链路</h3><p><code>POST /diagnose/chain</code>　body: <code>{"cost_time":1000}</code></p>
<p>注：pod 可传单个字符串或数组，不传则对该命名空间所有 Pod 操作。</p>
</body></html>"""
    return html


if __name__ == "__main__":
    # 开发环境启动：python app.py
    app.run(host="127.0.0.1", port=8000, debug=False)
