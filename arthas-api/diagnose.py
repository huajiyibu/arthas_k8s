"""
诊断命令封装（阶段 5）
通过 Pod 里的 arthas-client 连接已注入的 Arthas 服务端(3658)，
非交互执行诊断命令，对应需求文档 3.2 的 4 类诊断接口。
"""
import re
import subprocess
import threading
import time


def run_arthas_command(pod, command, namespace="default",
                       copy_path="/tmp/arthas", timeout=30, retries=3):
    """在 Pod 里用 arthas-client 非交互执行一条 Arthas 命令。

    原理:
        attach 后 Arthas 服务端监听在 Pod 内的 127.0.0.1:3658。
        arthas-client.jar 可以非交互连接服务端执行命令（-c 参数指定命令）。
        我们 kubectl exec 到 Pod 里运行它，把命令传进去，拿到结果。
        带自动重试：应对集群偶发连接抖动（TLS 握手超时）。

    参数:
        pod:       目标 Pod 名称
        command:   Arthas 命令字符串，如 "trace demo.MathGame primeFactors -n 1"
        namespace: 命名空间
        copy_path: arthas 工具在 Pod 内的路径，默认 /tmp/arthas
        timeout:   单次命令超时秒数，默认 30（需求 4.3：命令执行超时统一 30s）
        retries:   失败重试次数，默认 3
    返回:
        命令执行输出
    异常:
        重试仍失败时抛 RuntimeError
    """
    client_jar = f"{copy_path}/arthas-client.jar"   # arthas 客户端在 Pod 内的位置

    last_err = ""
    for attempt in range(retries):
        proc = subprocess.Popen(
            ["kubectl", "exec", "-n", namespace, pod, "--",
             "java", "-jar", client_jar, "-c", command],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            output = stdout + stderr
            if proc.returncode == 0:
                return output
            last_err = output          # 退出码非0：记录错误，准备重试
        except subprocess.TimeoutExpired:
            # 超时：watch/trace 这类命令要凑满 -n 才退出，流量不够时会一直跑。
            # 此时已捕获到的部分结果仍然是有效的，不能直接丢弃。
            proc.kill()
            stdout, stderr = proc.communicate()
            partial = stdout + stderr
            if has_match(partial):
                return partial         # 有真实捕获数据，直接作为结果返回
            # 30s 内没有捕获到任何匹配调用（= 无匹配流量/无满足阈值请求）。
            # 这里不重试、也不报错，直接把输出返回给上层；
            # 上层用 has_match 判断为 False 后会提示"无匹配耗时请求/方法"。
            # 这样符合需求 4.3.3：无匹配时提示"无匹配耗时请求"，而不是报"失败"。
            return partial

    raise RuntimeError(f"执行诊断命令失败: {last_err}")


def generate_traffic(pod, path="/", port=8080, namespace="default",
                     duration=45, interval=2):
    """在 Pod 内部自己给自己发 HTTP 请求，生成监控要抓的流量。

    原理：kubectl exec 进 Pod，用容器内的 curl 访问 127.0.0.1:port/path。
    这样无论宿主机能否直接访问 Pod IP，都能产生真实的业务请求。
    适合监控型接口（watch/trace/monitor）：开着监控的同时造流量，才能抓到数据。
    """
    url = f"http://127.0.0.1:{port}{path}"
    end = time.time() + duration
    while time.time() < end:
        try:
            subprocess.run(
                ["kubectl", "exec", "-n", namespace, pod, "--",
                 "sh", "-c", f"curl -s -m 5 -o /dev/null '{url}'"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            pass
        time.sleep(interval)


def run_with_auto_traffic(pod, func, namespace="default", traffic_path="/slow",
                          traffic_port=8080, duration=45, interval=2):
    """后台自动生成流量，同时执行诊断函数 func(pod)。

    返回 func(pod) 的结果；流量线程是 daemon，诊断结束后最多等 interval 秒。
    """
    t = threading.Thread(
        target=generate_traffic,
        args=(pod, traffic_path, traffic_port, namespace, duration, interval),
        daemon=True,
    )
    t.start()
    try:
        return func(pod)
    finally:
        t.join(timeout=interval + 1)


def has_match(output):
    """粗略判断命令输出里是否捕获到了实际数据。

    需求 4.3：无满足阈值的请求/方法时，要提示"无匹配耗时请求/方法"。
    Arthas 捕获到数据时，输出里会出现 "result=" 或调用栈记录；
    如果只有 banner/提示，说明没有匹配的调用发生。
    """
    # 只有真正捕获到方法调用/结果才算有数据：
    #   - watch/trace：result= / [cost= / `---[
    #   - monitor：输出里有"有调用数据"的行（日期开头，且 total>0）
    # "Affect(class" 只是"命令生效"，不代表捕获到了调用，不算匹配。
    markers = ("result=", "[cost=", "`---[")
    if any(m in output for m in markers):
        return True
    # monitor 数据行示例：
    #   2026-08-04  com.example.demo.  slow  2  2  0  2005.94  0.00%
    # （第一列是日期，第二列类名，第三列方法名，后面依次是 total success fail）
    return re.search(r"^\s*\d{4}-\d{2}-\d{2}.*\b([1-9]\d*)\s+\d+\s+\d+\b",
                     output, re.MULTILINE) is not None


def extract_uris(watch_output):
    """从 watch 输出里提取请求路径 URI。

    Arthas 的 watch 输出里，URI 形如：@String[/api/loop]
    用正则把 /xxx 部分提取出来，供链路接口逐条匹配业务方法。
    返回:
        URI 字符串列表（去重）
    """
    uris = re.findall(r"@String\[(/[^\]]+)\]", watch_output)
    # 去重并保持顺序
    seen = set()
    result = []
    for u in uris:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def watch_slow_requests(pod, cost_time, namespace="default", copy_path="/tmp/arthas"):
    """接口1: 查询耗时超过 cost_time(ms) 的请求路径（需求文档 3.2.1）"""
    command = (
        "watch org.apache.catalina.core.ApplicationFilterChain doFilter "
        "'{params[0].getRequestURI(), params[1].getStatus()}' -x 2 "
        f"'#cost>{cost_time}' -n 5"
    )
    return run_arthas_command(pod, command, namespace, copy_path)


def match_business_method(pod, request_uri, namespace="default",
                          copy_path="/tmp/arthas"):
    """接口2: 根据请求路径匹配业务类与方法（需求文档 3.2.2）

    ⚠️ 踩坑记录（真实 Web 应用验证发现）：
      1) arthas-client 的 -c 参数会把命令里的单/双引号都剥掉，
         所以 OGNL 条件里写字符串字面量 equals("/slow") 会变成语法错误；
      2) --skipJDKMethod false 会被 arthas 误当成"条件表达式"参数。
      因此这里：不加条件、不加 --skipJDKMethod，watch 全部 doDispatch 调用，
      输出 {请求URI, handler}，由 filter_match_method 按 request_uri 过滤。

    输出格式（真实验证）：
      result=@ArrayList[
          @String[/slow],
          @HandlerExecutionChain[HandlerExecutionChain with \
              [com.example.demo.DemoController#slow()] and 2 interceptors],
      ]
    """
    command = (
        "watch org.springframework.web.servlet.DispatcherServlet doDispatch "
        "'{params[0].getRequestURI(), target.getHandler(params[0])}' "
        "-n 50"
    )
    return run_arthas_command(pod, command, namespace, copy_path)


def filter_match_method(watch_output, request_uri):
    """从接口2的 watch 输出里，按 request_uri 过滤出匹配的业务类与方法。

    返回:
        {"request_uri", "class", "method"} 或 None（未匹配到）
    """
    blocks = re.split(r"result=@ArrayList\[", watch_output)[1:]
    target = f"@String[{request_uri}]"
    for block in blocks:
        if target in block:
            m = re.search(r"([A-Za-z_$][\w.$]*#[A-Za-z_$][\w$]*)", block)
            if m:
                cls, meth = m.group(1).split("#", 1)
                return {"request_uri": request_uri, "class": cls, "method": meth}
    return None


def trace_method(pod, class_name, method_name, cost_time, namespace="default",
                 copy_path="/tmp/arthas"):
    """接口3: 方法耗时调用栈追踪（需求文档 3.2.3）"""
    command = (
        f"trace {class_name} {method_name} -n 5 "
        f"'#cost>{cost_time}' --skipJDKMethod false"
    )
    return run_arthas_command(pod, command, namespace, copy_path)


def monitor_class(pod, class_name, cycle, namespace="default",
                  copy_path="/tmp/arthas"):
    """接口4: 业务方法性能统计排序 Top5（需求文档 3.2.4）

    monitor 是周期性持续输出的，用 timeout 控制执行时长。
    """
    command = f"monitor -c {cycle} {class_name} *"
    # monitor 需要跑一个统计周期，超时多给一点
    return run_arthas_command(pod, command, namespace, copy_path, timeout=cycle + 10)


if __name__ == "__main__":
    # 测试：在 math-game Pod 上跑 trace（注意 math-game 不是 Web 应用，
    # 所以接口1/2 的 Spring/Tomcat 命令在这上面跑不了，只能测 trace/monitor）
    pod_name = "math-game-595f7b8fd5-kvd5d"
    print("=== trace 测试 ===")
    print(trace_method(pod_name, "demo.MathGame", "primeFactors", 0))
