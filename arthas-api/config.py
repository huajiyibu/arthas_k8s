"""
项目配置（集中管理可配置项）

目标：避免把"机器相关"的路径/参数硬编码在代码里，方便别人 clone 下来直接跑。
规则：环境变量优先；未设置时使用相对项目根目录的默认路径。
"""
import os

# 项目根目录（本文件在 arthas-api/ 下，上一级即项目根）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve(name, default_rel):
    """取配置项：优先环境变量，否则用相对项目根目录的默认路径。"""
    v = os.environ.get(name)
    if v:
        return v
    return os.path.join(PROJECT_ROOT, default_rel)


# 本地 Arthas 工具所在目录的"父目录"。
# 其下的 `arthas/` 子目录就是要拷贝进 Pod 的工具本体（arthas-boot.jar 等）。
# 默认：<项目根>/arthas/arthas
# 可用环境变量 ARTHAS_PARENT_DIR 覆盖（比如装到别处时：set ARTHAS_PARENT_DIR=D:/tools/arthas）
ARTHAS_PARENT_DIR = _resolve("ARTHAS_PARENT_DIR", os.path.join("arthas", "arthas"))
