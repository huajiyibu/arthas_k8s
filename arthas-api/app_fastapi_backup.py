"""
Arthas 注入 + 诊断命令 API 服务（阶段 4 + 5）
用 FastAPI 实现，对应需求文档：
    - 3.1  Arthas 工具注入 API
    - 3.2  4 类诊断命令 API
统一返回格式：{code, msg, data}
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional, Union

from injector import copy_arthas_to_pod, start_arthas
from diagnose import (watch_slow_requests, match_business_method,
                      filter_match_method,
                      trace_method, monitor_class,
                      extract_uris, has_match)
from kubectl_utils import list_pods

# 创建 FastAPI 应用（app 是实例，也是 uvicorn 要运行的入口）
app = FastAPI(title="Pod 注入 Arthas 工具及诊断命令 API 服务", version="1.0.0")


# ---------- 统一返回格式 ----------
def ok(data=None, msg="成功"):
    """成功返回：code=200"""
    return {"code": 200, "msg": msg, "data": data}


def fail(msg):
    """失败返回：code=500"""
    return {"code": 500, "msg": msg, "data": None}


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


# ---------- 请求体模型（Pydantic：定义接口收什么参数） ----------
class InjectRequest(BaseModel):
    """注入 API 的入参（需求文档 3.1.2）"""
    region: Optional[str] = ""                 # 区域（需求字段；单集群环境暂不用于连接）
    cluster: Optional[str] = ""                # 集群（需求字段；单集群环境暂不用于连接）
    account: Optional[str] = ""                # 账户（需求字段；预留鉴权扩展）
    namespace: str                             # 命名空间（必填）
    pod: Optional[List[str]] = None            # Pod 名称列表（可选；不填则注入命名空间下所有 Pod）
    copy_path: Optional[str] = "/tmp/arthas"   # 拷贝路径（可选，默认 /tmp/arthas）


class DiagnoseBase(BaseModel):
    """诊断接口的公共入参"""
    namespace: str = "default"
    pod: Optional[Union[str, List[str]]] = None  # 单个/批量；不填=该namespace全部
    copy_path: Optional[str] = "/tmp/arthas"     # arthas 在 Pod 内的路径（可选）


class SlowRequestsRequest(DiagnoseBase):
    cost_time: int                            # 接口1：耗时阈值(ms)


class MatchMethodRequest(DiagnoseBase):
    request_uri: str                          # 接口2：请求路径


class TraceRequest(DiagnoseBase):
    class_name: str                           # 接口3：业务类全名
    method_name: str                          # 接口3：方法名
    cost_time: int                            # 接口3：耗时阈值(ms)


class MonitorRequest(DiagnoseBase):
    class_name: str                           # 接口4：业务类全名
    cycle: int = 10                           # 接口4：统计周期(秒)，默认10


class ChainRequest(DiagnoseBase):
    cost_time: int                            # 链路：慢接口耗时阈值(ms)


# ---------- 注入 API（需求文档 3.1） ----------
@app.post("/inject", summary="批量注入 Arthas")
def inject(req: InjectRequest):
    """对指定命名空间下的 Pod 执行注入（拷文件 + attach）。

    若未指定 pod，则默认注入该命名空间下所有 Pod。
    """
    results = []
    try:
        # 确定要注入的 Pod 列表：不填则取命名空间下所有 Pod
        pod_list = req.pod
        if not pod_list:
            pod_list = list_pods(req.namespace)
            if not pod_list:
                return fail(f"命名空间 {req.namespace} 下没有可注入的 Pod")

        # 需求 6：单批次最多支持 50 个 Pod
        if len(pod_list) > 50:
            return fail("单批次最多支持 50 个 Pod")

        for pod_name in pod_list:
            copy_arthas_to_pod(pod_name, req.namespace, req.copy_path)  # ① 拷文件
            start_arthas(pod_name, req.namespace, req.copy_path)        # ② 启动+attach
            results.append({"pod": pod_name, "status": "注入成功"})

        return ok({
            "region": req.region, "cluster": req.cluster, "account": req.account,
            "copy_path": req.copy_path, "results": results,
        }, "注入成功")
    except Exception as e:
        return fail(f"注入失败: {e}")


# ---------- 4 个诊断 API（需求文档 3.2） ----------
@app.post("/diagnose/slow-requests", summary="接口1: 慢接口查询")
def diag_slow_requests(req: SlowRequestsRequest):
    """查询耗时超过阈值的请求路径（支持批量，返回每 Pod 独立结果）"""
    try:
        pod_list = resolve_pods(req.pod, req.namespace)
        if not pod_list:
            return fail(f"命名空间 {req.namespace} 下没有可操作的 Pod")

        results = []
        for pod in pod_list:
            try:
                data = watch_slow_requests(pod, req.cost_time, req.namespace, req.copy_path)
                results.append({"pod": pod,
                                "result": data if has_match(data) else "无匹配耗时请求"})
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})
        return ok(results)
    except Exception as e:
        return fail(f"查询失败: {e}")


@app.post("/diagnose/match-method", summary="接口2: 匹配业务类方法")
def diag_match_method(req: MatchMethodRequest):
    """根据请求路径匹配业务类与方法（支持批量，返回每 Pod 独立结果）"""
    try:
        pod_list = resolve_pods(req.pod, req.namespace)
        if not pod_list:
            return fail(f"命名空间 {req.namespace} 下没有可操作的 Pod")

        results = []
        for pod in pod_list:
            try:
                data = match_business_method(pod, req.request_uri, req.namespace, req.copy_path)
                matched = filter_match_method(data, req.request_uri)
                if matched:
                    results.append({"pod": pod, "result": matched})
                else:
                    results.append({"pod": pod,
                                    "result": f"未匹配到请求路径 {req.request_uri} "
                                              f"对应的业务方法（确认该路径有实际请求流量）"})
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})
        return ok(results)
    except Exception as e:
        return fail(f"匹配失败: {e}")


@app.post("/diagnose/trace", summary="接口3: 方法耗时栈追踪")
def diag_trace(req: TraceRequest):
    """追踪方法内部调用栈耗时（支持批量，返回每 Pod 独立结果）"""
    try:
        pod_list = resolve_pods(req.pod, req.namespace)
        if not pod_list:
            return fail(f"命名空间 {req.namespace} 下没有可操作的 Pod")

        results = []
        for pod in pod_list:
            try:
                data = trace_method(pod, req.class_name, req.method_name,
                                    req.cost_time, req.namespace, req.copy_path)
                results.append({"pod": pod,
                                "result": data if has_match(data) else "无匹配耗时请求/方法"})
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})
        return ok(results)
    except Exception as e:
        return fail(f"追踪失败: {e}")


@app.post("/diagnose/monitor", summary="接口4: 方法性能统计")
def diag_monitor(req: MonitorRequest):
    """统计类下所有方法性能（支持批量，返回每 Pod 独立结果）"""
    try:
        pod_list = resolve_pods(req.pod, req.namespace)
        if not pod_list:
            return fail(f"命名空间 {req.namespace} 下没有可操作的 Pod")

        results = []
        for pod in pod_list:
            try:
                data = monitor_class(pod, req.class_name, req.cycle, req.namespace, req.copy_path)
                results.append({"pod": pod,
                                "result": data if has_match(data) else "无匹配耗时请求/方法"})
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})
        return ok(results)
    except Exception as e:
        return fail(f"统计失败: {e}")


@app.post("/diagnose/chain", summary="完整排查链路: 慢接口→绑方法")
def diag_chain(req: ChainRequest):
    """一次调用走完链路：①慢接口 -> ②匹配方法（支持批量，返回每 Pod 独立结果）

    注意：链路依赖真实 Web 应用 + 真实慢请求流量才能捕获到数据。
    """
    try:
        pod_list = resolve_pods(req.pod, req.namespace)
        if not pod_list:
            return fail(f"命名空间 {req.namespace} 下没有可操作的 Pod")

        results = []
        for pod in pod_list:
            try:
                # ① 查慢接口
                slow_output = watch_slow_requests(pod, req.cost_time,
                                                  req.namespace, req.copy_path)
                uris = extract_uris(slow_output)

                # ② 对每个慢接口 URI，匹配对应的业务类与方法
                methods = []
                for uri in uris:
                    try:
                        m = match_business_method(pod, uri, req.namespace, req.copy_path)
                        matched = filter_match_method(m, uri)
                        methods.append({"uri": uri, "match": matched})
                    except Exception as e:
                        methods.append({"uri": uri, "match": f"匹配失败: {e}"})

                results.append({"pod": pod, "uris": uris, "methods": methods})
            except Exception as e:
                results.append({"pod": pod, "result": f"失败: {e}"})

        return ok(results, "链路排查完成")
    except Exception as e:
        return fail(f"链路排查失败: {e}")


@app.get("/", summary="服务说明")
def root():
    """首页：提示接口文档地址"""
    return {"service": "Arthas 注入 + 诊断 API 服务", "docs": "/docs"}
