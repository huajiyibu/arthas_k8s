"""
kubectl 工具封装
把调用 kubectl 的通用逻辑封装成函数，并带自动重试（应对集群偶发连接抖动）。
"""
import subprocess  # 用来在 Python 里执行外部命令（kubectl）
import time        # 用来让程序"睡一会儿"（重试间隔）


def run_kubectl(args, retries=3):
    """执行 kubectl 命令，失败自动重试。

    参数:
        args:    命令参数列表，例如 ["get", "pods", "-o", "wide"]
        retries: 最多尝试次数，默认 3 次
    返回:
        命令的标准输出（字符串）
    异常:
        重试完仍失败时抛出 RuntimeError
    """
    # 循环尝试，最多 retries 次
    for attempt in range(retries):
        # 用 subprocess 执行 "kubectl" + 参数 组成的完整命令
        result = subprocess.run(
            ["kubectl"] + args,   # 把 "kubectl" 和 args 拼成一个列表
            capture_output=True,  # 捕获 stdout 和 stderr（不直接刷到屏幕）
            text=True             # 让输出是文本字符串
        )

        # 退出码 0 = 命令成功，直接返回正常输出
        if result.returncode == 0:
            return result.stdout

        # 非 0 = 失败：打印错误原因，等 2 秒后重试
        print(f"第{attempt + 1}次失败: {result.stderr.strip()}, 1秒后重试...")
        time.sleep(1)

    # 重试多次仍失败，抛出异常让上层知道出了问题
    raise RuntimeError(f"kubectl 执行失败: {result.stderr}")


def list_pods(namespace="default"):
    """获取指定命名空间下所有 Pod 的名称列表。

    用 kubectl 的 jsonpath 只取名字，返回字符串列表。
    参数:
        namespace: 命名空间
    返回:
        Pod 名称列表（没有则为空列表）
    """
    output = run_kubectl(
        ["get", "pods", "-n", namespace,
         "-o", "jsonpath={.items[*].metadata.name}"]
    )
    # 输出是空格分隔的 Pod 名，拆成列表
    return [p for p in output.split() if p]


if __name__ == "__main__":
    # 当直接运行这个文件时（python kubectl_utils.py），执行下面的测试
    print(run_kubectl(["get", "pods", "-o", "wide"]))
