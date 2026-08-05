# 🛠️ Arthas 注入 + 诊断命令 API 服务

对 K8s 集群里运行的 Java 应用 Pod，**自动注入 Arthas**，并提供 **4 类诊断命令**的 HTTP API。
对应需求文档：`../Pod注入Arthas工具及诊断命令API服务需求文档.md`

---

## 📁 目录结构

| 文件 | 作用 |
|---|---|
| `kubectl_utils.py` | 带自动重试的 kubectl 执行封装（`run_kubectl`） |
| `injector.py` | 注入三步：`copy_arthas_to_pod`（拷文件）+ `start_arthas`（启动+attach） |
| `diagnose.py` | 诊断命令执行：`run_arthas_command`（arthas-client 非交互）+ 4 个诊断函数 |
| `app.py` | Flask 服务入口（所有 HTTP 接口） |
| `app_fastapi_backup.py` | （备份）旧版 FastAPI 入口，仅作对照参考 |

---

## 🚀 启动服务（Flask）

```powershell
Set-Location arthas-api
& ..\.venv\Scripts\python.exe app.py        # 方式1：直接跑
# 或
& ..\.venv\Scripts\flask.exe --app app run --port 8000   # 方式2：flask 命令
```

- 服务地址：**http://127.0.0.1:8000**，简易接口文档：**http://127.0.0.1:8000/docs**
- 依赖：`flask`（已装到 .venv）
- 注：默认 `app.run(host='127.0.0.1', port=8000)`；老师要求 Flask 框架，已从 FastAPI 迁移完成。

---

## 📡 接口清单

| 接口 | 方法 | 说明 | 关键入参 |
|---|---|---|---|
| `/` | GET | 服务说明 | - |
| `/inject` | POST | **批量注入 Arthas** | region, cluster, account, namespace, pod[], copy_path |
| `/diagnose/slow-requests` | POST | 接口1：慢接口查询 | pod, cost_time(ms) |
| `/diagnose/match-method` | POST | 接口2：匹配业务类方法 | pod, request_uri |
| `/diagnose/trace` | POST | 接口3：方法耗时栈追踪 | pod, class_name, method_name, cost_time |
| `/diagnose/monitor` | POST | 接口4：方法性能统计 | pod, class_name, cycle |
| `/diagnose/chain` | POST | 完整链路：慢接口→绑方法 | pod, cost_time |

**统一返回格式**：`{code: 200/500, msg, data}`

**🆕 自动打流量**：所有诊断接口支持可选参数 `auto_traffic`（默认 false）、`traffic_path`（默认 `/slow`）、`traffic_port`（默认 8080）。
开启后，服务会在诊断监控的同时，自动 `kubectl exec` 进 Pod 内 `curl 127.0.0.1:port/path` 造流量，
这样监控型接口（慢接口/匹配方法/链路）**点一下就能自动抓到数据，不用手动打流量**。
（网页控制台默认勾选"自动打流量"，路径默认 `/slow`。）

---

## ✅ 完成情况

**已实现并验证（2026-08-04/05，真实 Web 应用 demo-web 上全部跑通）：**
- Flask 框架迁移完成：全部 6 个 HTTP 接口在 Flask 下验证可用（含 `/inject` 注入、`/diagnose/match-method` 匹配到 `DemoController.slow`）
- 注入三步（拷文件 + 自动 attach，支持批量 + 自定义 `copy_path`）
- 5 个诊断接口（慢接口/绑方法/trace/monitor/chain）全部在真实 Spring Boot 应用上验证成功
- `region/cluster/account` 入参（预留多集群/鉴权扩展）
- 无匹配数据提示（`无匹配耗时请求/方法`）
- 命令执行 30s 超时、注入失败自动重试、单批次上限 50 Pod
- 诊断命令踩坑修复：arthas-client 剥引号→OGNL 不用字符串字面量；超时带回已捕获的部分结果

---

## 🗓️ 明天回来可以做什么（优先级）

1. **部署一个真实 Spring Boot 应用**（或找现成的 Web 应用镜像）→ 验证接口 1 / 2 / chain
2. 打开 **http://127.0.0.1:8000/docs** 在线体验各个接口
3. （可选）加账户鉴权、把服务 Docker 化部署到集群
4. （可选）给诊断输出做结构化解析（从 watch/trace 输出提取 URI/类名/方法名）

---

## ⚠️ 注意事项（踩过的坑）

- PowerShell 里 `curl` 是 `Invoke-WebRequest` 别名 → 用 `curl.exe` 或 `Invoke-RestMethod`
- PowerShell 传中文 JSON 会乱码 → 用 UTF-8 客户端（浏览器 /docs、Python requests）正常
- `kubectl cp` 支持 `ns/pod:路径`；`kubectl exec` 用 `-n ns pod`（不能用斜杠）
- 本地路径含盘符 `C:` 会被 kubectl cp 误判 → 用 `cwd=` + 相对路径
- Arthas attach 后的界面走 telnet(3658) 不读 stdin → 自动化只喂进程序号、超时终止即可
