FROM bitnami/kubectl:1.28

# 安装 bash（如果需要）
USER root
RUN install_packages bash

# 复制 arthas 文件夹到镜像
COPY arthas /arthas

# 默认命令
CMD ["bash"]