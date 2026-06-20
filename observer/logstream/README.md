# `observer/logstream/` · 阶段二：日志流滑动窗口捕获

以极低开销（非阻塞 IO）附加到 `docker.logs(stream=True)`，实时正则清洗并维护 200 行滑动窗口，命中高危报错时冻结上下文。

## 文件职责

| 文件 | 职责 |
|------|------|
| `ring_buffer.py` | 内存中维护 200 行滑动窗口（Ring Buffer）；命中报错即冻结，保证截取**报错前 100 行 + 后 100 行**完整堆栈 |
| `regex_filter.py` | 正则匹配高危特征词：`[FATAL]`、`Exception`、`java.lang.OutOfMemoryError`、`net.minecraft.crash` 等；忽略普通聊天/跑图日志 |
| `rate_limiter.py` | **日志风暴兜底**：单秒读取行数超阈值即截断丢弃，标记 `LOG_SPAM_DETECTED`，防撑爆内存与 IO |

## 关键约束

- **非阻塞 IO**：流式监听必须非阻塞，避免拖垮主进程。
- **上下文冻结**：一旦正则命中，立即冻结 Ring Buffer，确保 AI 诊断拿到完整堆栈语料。
- **限速防风暴**：写得糟糕的 Mod 无限死循环喷日志时（每秒万行），必须限速截断。

## 上游/下游

- 上游：`infra/docker_client.py` 提供 logs(stream)
- 下游：`dispatcher/anomaly_emitter.py` 接收冻结的 200 行上下文
