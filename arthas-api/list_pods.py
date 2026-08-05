import subprocess

result = subprocess.run(
    ["kubectl", "get", "pods", "-o", "wide"],
    capture_output=True,
    text=True
)

print("=== 标准输出 stdout ===")
print(result.stdout)
print("=== 错误输出 stderr ===")
print(result.stderr)
print("=== 退出码 returncode (0=成功) ===")
print(result.returncode)