#!/bin/bash

# 用法: ./inject_arthas.sh <namespace> <target_pod>
# 例如: ./inject_arthas.sh default my-java-app

NAMESPACE=${1:-default}
TARGET_POD=$2
# TARGET_CONTAINER=${3:-$(kubectl get pod -n $NAMESPACE $TARGET_POD -o jsonpath='{.spec.containers[0].name}')}

# 参数检查
if [ -z "$NAMESPACE" ] || [ -z "$TARGET_POD" ]; then
  echo "用法: ./inject_arthas.sh <namespace> <target_pod> [target_container]"
  exit 1
fi

echo "目标命名空间: $NAMESPACE, Pod: $TARGET_POD, 容器: $TARGET_CONTAINER"

# 创建临时 Pod
echo "1. 创建临时 arthas 工具 Pod..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: arthas-injector
  namespace: default
spec:
  containers:
  - name: arthas-injector
    image: 10.124.142.91/istio/arthas-file:1.0
    imagePullPolicy: IfNotPresent
  restartPolicy: Never
EOF

echo "2. 等待 Pod 就绪..."
kubectl wait --for=condition=Ready pod/arthas-injector --timeout=30s

# 把 arthas 从 Pod 复制到主机 /tmp
echo "3. 将 arthas 复制到主机临时目录..."
rm -rf /tmp/arthas
mkdir -p /tmp/arthas
kubectl cp arthas-injector:/arthas /tmp/arthas

# 从主机复制到目标 Pod
echo "4. 注入 arthas 到目标 Pod..."
kubectl cp /tmp/arthas $NAMESPACE/$TARGET_POD:/tmp

echo "5. 清理临时资源..."
# 删除临时 Pod
kubectl delete pod arthas-injector --force
# 删除临时文件
rm -rf /tmp/arthas

echo "完成！arthas 已注入到 $NAMESPACE/$TARGET_POD:/tmp 目录"
echo "可以通过以下命令连接到目标 Pod 使用 arthas:"
echo "kubectl exec -it -n $NAMESPACE $TARGET_POD -- bash"
echo "然后在 Pod 内运行: cd /arthas && java -jar arthas-boot.jar"

kubectl exec -n $NAMESPACE $TARGET_POD -- bash -c "ls -l /tmp/arthas && cd /tmp/arthas && java -jar arthas-boot.jar" > /tmp/arthas_output.txt
kubectl exec -n $NAMESPACE $TARGET_POD -- rm -rf /tmp/arthas
# echo "arthas 文件夹内容如下："
# ls -l /tmp/arthas

# cd /tmp/arthas && java -jar arthas-boot.jar
# rm -rf /tmp/arthas
cat /tmp/arthas_output.txt
rm -f /tmp/arthas_output.txt