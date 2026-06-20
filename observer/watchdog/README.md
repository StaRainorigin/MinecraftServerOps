# `observer/watchdog/` · 阶段一：生命周期看门狗

底层探针轮询 Docker Daemon，检测目标容器状态突变，生成"硬宕机事件"。

## 触发条件

容器状态突变为 `Exited`，且满足以下任一：
- `Exit Code != 0`
- 被打上 `OOMKilled` 标签（被 Linux 宿主机杀掉）

命中即立即生成"硬宕机事件"，交由 `dispatcher/` 防抖后唤醒 brain。

## 文件职责

| 文件 | 职责 |
|------|------|
| `container_probe.py` | 轮询容器状态，解析 ExitCode / OOMKilled，产出硬宕机事件 |

## 上游/下游

- 上游：`infra/docker_client.py` 提供 Docker Daemon 访问
- 下游：`dispatcher/anomaly_emitter.py`
