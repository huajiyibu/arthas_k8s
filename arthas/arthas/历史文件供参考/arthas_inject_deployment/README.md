# Arthas 批量注入工具使用指南

## 简介

本工具旨在帮助开发和运维人员快速、便捷地将阿里巴巴开源的Java诊断工具Arthas批量注入到运行在Kubernetes (K8s)集群中的多个目标Java应用的Pod中。通过注入Arthas，您可以对线上应用进行实时的性能分析、问题排查和在线诊断，而无需重启应用或修改代码。
## warning "注意"
- 本工具仅适用于Kubernetes环境，且仅支持Java应用。
- 请确保您的Kubernetes集群已正确配置，并且具备访问目标应用的权限。
- 此工具不会修改目标应用的代码或配置，仅通过Kubernetes的Job机制注入Arthas。
- 此文件请勿外传，更不要在任何情况下修改此文件以变更生产环境，如果如此操作造成任何生产环境问题，作者概不负责。
## 准备工作

在开始之前，请确保您已满足以下条件：

1.  **`kubectl` 命令行工具**: 您的电脑上已安装 `kubectl`，并且已配置好访问目标Kubernetes集群的权限。
2.  **YAML配置文件**: 您已获取以下三个YAML配置文件：
    * `arthas-targets-configmap.yaml`: 用于定义需要注入Arthas的目标应用列表。
    * `arthas-injector.yaml`: 用于定义注入Arthas的Job。

## 1. 配置目标应用 (ConfigMap)

工具通过读取一个名为 `arthas-targets` 的 `ConfigMap` 来确定要向哪些应用的Pod注入Arthas。

**`ConfigMap` 文件内容示例 (`configmap-arthas-targets.yaml`):**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: arthas-targets
  namespace: default # ConfigMap所在的命名空间，默认为default
data:
  targets.txt: |
    # 这是注释行：每行指定一个目标应用
    # 格式为: [命名空间]:[Deployment名称], 注意换行
    # 如果应用在 "default" 命名空间, 可以省略命名空间前缀

    # 示例1: 注入 default 命名空间下的 image-cache-controller Deployment
    default:image-cache-controller
    # 或者简写为 (如果它在default命名空间):
    # image-cache-controller

    # 示例2: 注入 csm-system 命名空间下的 srvmesh-mng-controller-api-v2-3-8 Deployment
    csm-system:srvmesh-mng-controller-api-v2-3-8

    # 您可以在下面添加更多目标应用:
    # another-namespace:another-deployment
    # my-app-in-default
```

## 2. 注入工具使用方法
在做好上述准备后，您可以按照以下步骤使用工具：

1.  **创建ConfigMap**: 使用以下命令创建 `ConfigMap`:
    ```bash
    kubectl apply -f configmap-arthas-targets.yaml
    ```
2.  **运行注入工具**: 执行以下命令来运行注入工具:
    ```bash
    kubectl apply -f arthas-injector.yaml

## 3. 查看注入结果
注入工具会自动创建一个名为 `arthas-injector-job` 的 `Job`，该Job会根据 `ConfigMap` 中的目标应用列表，为每个应用的Pod注入Arthas。

您可以使用以下命令来查看注入结果:
```bash
kubectl get pods -n default -l job-name=arthas-batch-injector
kubectl logs -f -n default <pod-name-from-above>
```
成功注入的日志片段示例:
```bash
准备arthas文件，文件目录为/tmp/arthas...
从Configmap读取deloyment： /config/targets.txt...
正在处理： [default:image-cache-controller]
-----------------------------------------------------
正在处理: [default/image-cache-controller]
Label selector for Deployment 'default/image-cache-controller': [app=image-cache-controller]
Found Pods for Deployment 'default/image-cache-controller': [image-cache-controller-6484958d77-68p5x]
  正在注入: [default/image-cache-controller-6484958d77-68p5x] ...
  注入成功 [default/image-cache-controller-6484958d77-68p5x]
成功读取: [default/image-cache-controller]
-----------------------------------------------------
正在处理： [csm-system:srvmesh-mng-controller-api-v2-3-8]
-----------------------------------------------------
正在处理: [csm-system/srvmesh-mng-controller-api-v2-3-8]
Label selector for Deployment 'csm-system/srvmesh-mng-controller-api-v2-3-8': [app=srvmesh-mng-controller-api]
Found Pods for Deployment 'csm-system/srvmesh-mng-controller-api-v2-3-8': [srvmesh-mng-controller-api-v2-3-8-786749cd8c-v285g]
  正在注入: [csm-system/srvmesh-mng-controller-api-v2-3-8-786749cd8c-v285g] ...
  注入成功 [csm-system/srvmesh-mng-controller-api-v2-3-8-786749cd8c-v285g]
成功读取: [csm-system/srvmesh-mng-controller-api-v2-3-8]
-----------------------------------------------------
所有指定注入已完成。
清理/tmp/arthas文件...
清理RBAC资源...
Attempting to delete ClusterRole 'arthas-batch-injector-clusterrole'...
clusterrole.rbac.authorization.k8s.io "arthas-batch-injector-clusterrole" deleted
ClusterRole 'arthas-batch-injector-clusterrole' deletion command sent (or it was not found).
清理完成
```
## 4. 任务自动清理
注入工具会在任务完成后自动清理临时文件和RBAC资源，以确保环境的干净状态。

注入任务 (Job) 在执行完毕后，会尝试自动清理其在执行过程中使用的RBAC资源，即 `ClusterRoleBinding ("arthas-batch-injector-binding")` 和 `ClusterRole ("arthas-batch-injector-clusterrole")`。您可以在Job的日志末尾看到相关的清理尝试信息。

Job本身（及其Pod，如果成功完成）通常会保留，直到被手动删除或由集群的自动清理策略处理

## 再次声明：此文件请勿外传，更不要在任何情况下修改此文件以变更生产环境，如果如此操作造成任何生产环境问题，作者概不负责。
