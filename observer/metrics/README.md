# `observer/metrics/` · 阶段三：业务水位巡检

周期性采集硬件资源与游戏 TPS，判定服务器是否陷入"假死/僵尸状态"，生成"软宕机事件"。

## 文件职责

| 文件 | 职责 |
|------|------|
| `sampler.py` | 硬件采样：每 5 秒采集一次内存占用百分比与 CPU 负载（Cgroups 数据） |
| `tps_probe.py` | TPS 嗅探：解析 `Can't keep up!` 警告，或通过 RCON 发送 `tps` 指令；**静默崩溃兜底**：连续 3 次 RCON 超时强制触发异常 |
| `thresholds.py` | 触发判定：CPU 持续 100% 且 TPS 连续 60 秒 `< 10.0` → 软宕机事件 |

## 关键约束

- **采样频率**：5 秒一次，平衡精度与开销。
- **静默崩溃最后一道防线**：Java 进程在、内存没满、无报错日志但玩家掉线（网络死锁/主线程挂起）时，依赖 RCON 超时强制判定。

## 上游/下游

- 上游：`infra/docker_client.py`（Cgroups）、`infra/rcon_client.py`（RCON）
- 下游：`dispatcher/anomaly_emitter.py`
