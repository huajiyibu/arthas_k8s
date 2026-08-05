"""
Arthas 注入封装
把"手动注入 Arthas 到 Pod"的步骤封装成 Python 函数。
本文件先封装第 1 步：拷贝 arthas 工具到 Pod。
"""
import re
import subprocess

from config import ARTHAS_PARENT_DIR  # 本地 arthas 工具所在目录（可配置，见 config.py）
from kubectl_utils import run_kubectl  # 复用带重试的 kubectl 执行函数

# 注入结果注册表：(namespace, pod) -> [{"pid","process","port"}, ...]
# 诊断层通过 get_attached_processes() 读取，实现"每进程独立诊断"。
# 放在注入模块里，是为了让"注入了什么"和"诊断什么"低耦合：
# 诊断层只需要 get_attached_processes()，不关心注入内部怎么做到的。
ARTHAS_PROCESS_REGISTRY: dict = {}


def register_attached_processes(namespace, pod, processes):
    """记录某 Pod 已 attach 的进程及其 Arthas 端口（供诊断层遍历）。"""
    ARTHAS_PROCESS_REGISTRY[(namespace, pod)] = list(processes)


def get_attached_processes(namespace, pod):
    """取某 Pod 已 attach 的进程列表；未记录则回退默认端口 3658（不影响老流程）。"""
    procs = ARTHAS_PROCESS_REGISTRY.get((namespace, pod))
    if procs:
        return procs
    return [{"pid": "", "process": "(未注入记录，用默认端口)", "port": 3658}]

# 说明：ARTHAS_PARENT_DIR 是 arthas 工具文件夹的父目录。
# 用它作为工作目录、用相对路径 "arthas" 拷贝，避开 Windows 盘符冒号(c:)的坑。
# 默认指向 <项目根>/arthas/arthas，可用环境变量 ARTHAS_PARENT_DIR 覆盖。


def copy_arthas_to_pod(pod, namespace="default", copy_path="/tmp/arthas"):
    """把本地 arthas 工具拷到 Pod 的指定路径（注入第 1 步）。

    参数:
        pod:        目标 Pod 名称
        namespace:  Pod 所在命名空间，默认 default
        copy_path:  arthas 在 Pod 内的存放路径，默认 /tmp/arthas（需求 3.1.2）
    返回:
        成功提示信息
    异常:
        拷贝失败时抛 RuntimeError
    """
    # copy_path 的父目录，例如 /tmp/arthas -> /tmp
    parent_dir = copy_path.rsplit("/", 1)[0] or "/"

    # ① 先确保 Pod 里父目录存在（kubectl exec mkdir -p）
    mkdir = subprocess.run(
        ["kubectl", "exec", "-n", namespace, pod, "--", "sh", "-c",
         f"mkdir -p {parent_dir}"],
        capture_output=True, text=True,
    )
    if mkdir.returncode != 0:
        raise RuntimeError(f"在 Pod 里创建目录失败: {mkdir.stderr}")

    # ② 把本地 arthas 目录拷贝到父目录下，形成 copy_path
    result = subprocess.run(
        ["kubectl", "cp", "arthas", f"{namespace}/{pod}:{parent_dir}/"],
        cwd=ARTHAS_PARENT_DIR,   # 让 kubectl 在 arthas 父目录下执行，用相对路径避开盘符坑
        capture_output=True,
        text=True,
    )

    # 退出码非 0 = 失败
    if result.returncode != 0:
        raise RuntimeError(f"拷贝 arthas 失败: {result.stderr}")

    return f"✅ 已拷贝 arthas 到 {namespace}/{pod}:{copy_path}"


def _parse_jps(output):
    """解析 `jps -l` 的输出，返回 [(pid, 描述), ...]（纯函数，便于单测）。

    只认"数字 + 空格 + 主类/jar"的行，其余（警告、报错、空行）一律忽略。
    """
    procs = []
    for line in output.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            procs.append((parts[0], parts[1]))
    return procs


def list_java_processes(pod, namespace="default"):
    """在 Pod 里用 `jps -l` 列出所有 Java 进程（一个不漏，支持 Pod 内多 JVM）。

    返回: [(pid, 主类/jar 描述), ...]，按 jps 输出顺序。
    异常: 一个 Java 进程都没发现时抛 RuntimeError。
    """
    output = run_kubectl(["exec", "-n", namespace, pod, "--", "jps", "-l"])
    procs = _parse_jps(output)
    if not procs:
        raise RuntimeError(
            f"Pod {pod} 里没有发现 Java 进程（jps 无输出）。"
            "请确认应用是 JDK 版（jps 属于 JDK，纯 JRE 镜像里没有）"
        )
    return procs


def _extract_telnet_port(output, default):
    """从 arthas-boot 输出里解析实际 telnet 端口，解析不到用默认值。

    例如输出里有 "The telnet port is 3658"，就返回 3658。
    （覆盖"已 attach 过、skip attach"时端口可能不是我们分配的情况）
    """
    m = re.search(r"telnet port is (\d+)", output, re.IGNORECASE)
    return int(m.group(1)) if m else default


def _attach_one(pod, namespace, boot_jar, pid, telnet_port, http_port,
                timeout, retries):
    """把 Arthas attach 到指定 PID 的 JVM，返回 (attach_ok, 实际端口, 输出)。

    与旧版"喂菜单序号 1"不同：直接 `java -jar arthas-boot.jar <PID>`，
    跳过交互菜单，精准锁定目标 JVM；并用 --telnet-port/--http-port 显式分配端口，
    这样多个 JVM 各自有独立端口（3658, 3659, ...），诊断时能逐个连。
    """
    last_output = ""
    for _attempt in range(retries):
        p = subprocess.Popen(
            ["kubectl", "exec", "-i", "-n", namespace, pod, "--",
             "sh", "-c",
             f"java -jar {boot_jar} "
             f"--telnet-port {telnet_port} "
             f"--http-port {http_port} {pid}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            out, err = p.communicate(timeout=timeout)  # 等待 attach
        except subprocess.TimeoutExpired:
            # attach 已完成，只是界面挂着不退出：杀掉 arthas-boot 即可
            p.kill()
            out, err = p.communicate()

        output = out + err

        # 注入成功判断（两种情况都算）：
        #   情况1：新 attach     -> 输出含 "Attach process" 且含 "success"
        #   情况2：之前已注入过  -> 输出含 "skip attach"（端口已在）
        attach_ok = (
            ("Attach process" in output and "success" in output)
            or ("skip attach" in output)
        )
        if attach_ok:
            return True, _extract_telnet_port(output, telnet_port), output

        # 失败：记录输出，稍后重试
        last_output = output

    return False, telnet_port, last_output


def start_arthas(pod, namespace="default", copy_path="/tmp/arthas",
                 timeout=25, retries=2):
    """在 Pod 里启动 arthas，并对 Pod 内**所有** Java 进程逐个 attach（注入第 2 步）。

    为什么是全进程、而不是只喂 "1" 选第一个？
        一个 Pod 里可能有多个 JVM（应用 + 边车 agent 等），性能瓶颈可能藏在任何
        一个 JVM 里（比如边车日志卡住拖慢全链路）。所以先 `jps -l` 列出全部 Java
        进程，再逐个按 PID attach，并为每个 JVM 显式分配独立 Arthas 端口
        （3658, 3659, ...），把 {pid, process, port} 记进注册表，供诊断层"每进程诊断"。

    参数:
        pod:       目标 Pod 名称
        namespace: 命名空间，默认 default
        copy_path: arthas 工具在 Pod 内的路径，默认 /tmp/arthas
        timeout:   单个进程 attach 等待秒数（attach 很快，默认 25 秒足够）
        retries:   attach 失败重试次数，默认 2（需求 4.3：注入失败自动重试1次）
    返回:
        汇总信息（每个 Java 进程的 pid / 描述 / 端口 / 是否 attach 成功）
    异常:
        没有 Java 进程，或 attach 仍有失败时抛 RuntimeError
    """
    boot_jar = f"{copy_path}/arthas-boot.jar"   # arthas 引导程序在 Pod 内的位置
    procs = list_java_processes(pod, namespace)

    results = []
    for idx, (pid, desc) in enumerate(procs):
        telnet_port = 3658 + idx   # 第 1 个 JVM -> 3658，第 2 个 -> 3659，...
        http_port = 8658 + idx     # http 端口同样错开，避免冲突
        ok, port, _output = _attach_one(pod, namespace, boot_jar, pid,
                                        telnet_port, http_port,
                                        timeout, retries)
        results.append({"pid": pid, "process": desc, "attached": ok, "port": port})

    failed = [r for r in results if not r["attached"]]
    if failed:
        raise RuntimeError(f"Arthas attach 部分失败: {failed}")

    # 记录到注册表：诊断层据此对每个进程逐个诊断
    register_attached_processes(namespace, pod, results)

    summary = "、".join(
        f"[{r['pid']}] {r['process']}(端口{r['port']}, {'成功' if r['attached'] else '失败'})"
        for r in results
    )
    return f"✅ 已对 Pod {pod} 的 {len(results)} 个 Java 进程全部 attach: {summary}"


if __name__ == "__main__":
    # 直接运行本文件时，做一次完整的注入测试
    pod_name = "math-game-595f7b8fd5-kvd5d"  # 你的 math-game Pod

    # ① 拷贝 arthas 进 Pod
    print(copy_arthas_to_pod(pod_name))

    # ② 验证：列出 Pod 里 /tmp/arthas 的内容
    print("\n=== 验证 Pod 内 /tmp/arthas 内容 ===")
    print(run_kubectl(["exec", pod_name, "--", "ls", "/tmp/arthas"]))

    # ③ 启动 arthas 并自动 attach（注入第 2 步）
    print("\n=== 启动 arthas 并 attach ===")
    print(start_arthas(pod_name))
