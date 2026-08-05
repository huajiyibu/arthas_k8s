"""
Arthas 注入封装
把"手动注入 Arthas 到 Pod"的步骤封装成 Python 函数。
本文件先封装第 1 步：拷贝 arthas 工具到 Pod。
"""
import subprocess

from kubectl_utils import run_kubectl  # 复用带重试的 kubectl 执行函数
from config import ARTHAS_PARENT_DIR  # 本地 arthas 工具所在目录（可配置，见 config.py）

# 说明：ARTHAS_PARENT_DIR 是 arthas 工具文件夹的父目录。
# 用它作为工作目录、用相对路径 "arthas" 拷贝，避开 Windows 盘符冒号(c:)的坑。
# 默认指向 <项目根>/arthas/arthas，可用环境变量 ARTHAS_PARENT_DIR 覆盖。


def copy_arthas_to_pod(pod, namespace="default", copy_path="/tmp/arthas"):
    """把本地 arthas 工具拷到 Pod 的指定路径（注入第 1 步）。

    参数:
        pod:       目标 Pod 名称
        namespace: Pod 所在命名空间，默认 default
        copy_path: arthas 在 Pod 内的存放路径，默认 /tmp/arthas（需求 3.1.2）
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


def start_arthas(pod, namespace="default", copy_path="/tmp/arthas",
                 timeout=25, retries=2):
    """在 Pod 里启动 arthas 并自动 attach 到 Java 进程（注入第 2 步）。

    原理:
        arthas-boot 通过 stdin 读取你选择的进程序号来完成 attach。
        attach 成功后，Arthas 服务端(3658端口)会常驻在目标进程里。
        注意：attach 后的"交互界面"走的是 telnet(网络)，不再读 stdin，
        所以 quit 无法通过管道生效，界面会一直挂着直到超时。
        因此策略是：只喂 "1" 完成 attach，然后让命令超时被终止即可——
        attach 的成果（3658服务端）已经留在 math-game 里了。

    参数:
        pod:       目标 Pod 名称
        namespace: 命名空间，默认 default
        copy_path: arthas 工具在 Pod 内的路径，默认 /tmp/arthas
        timeout:   等待 attach 完成的秒数（attach 很快，默认 25 秒足够）
        retries:   attach 失败重试次数，默认 2（需求 4.3：注入失败自动重试1次）
    返回:
        命令完整输出（含 attach 结果）
    异常:
        attach 重试仍失败时抛 RuntimeError
    """
    boot_jar = f"{copy_path}/arthas-boot.jar"   # arthas 引导程序在 Pod 内的位置

    last_output = ""
    for attempt in range(retries):
        # 启动 arthas-boot，通过 stdin 喂 "1" 选择进程 1 完成 attach
        p = subprocess.Popen(
            ["kubectl", "exec", "-i", "-n", namespace, pod, "--", "sh", "-c",
             f'printf "1\\n" | java -jar {boot_jar}'],
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
        #   情况2：之前已注入过  -> 输出含 "skip attach"（3658端口已在）
        attach_ok = (
            ("Attach process" in output and "success" in output)
            or ("skip attach" in output)
        )
        if attach_ok:
            return output

        # 失败：记录输出，稍后重试
        last_output = output

    raise RuntimeError(f"Arthas attach 失败(重试{retries}次): {last_output}")


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
