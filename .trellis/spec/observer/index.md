# observer 模块编码规范

> 模块二：全天候可观测性与异常感知（低开销守护进程）
> 状态：[骨架] 阶段（仅占位 docstring）

---

## 当前状态

所有文件均为占位骨架，仅包含模块 docstring，逻辑待后续填充。

---

## 设计规划

根据 PRD，observer 模块应实现：

- **守护进程**：`daemon.py` — 并发调度四子任务
- **容器看门狗**：`watchdog/container_probe.py` — 容器生命周期监控
- **日志流**：`logstream/ring_buffer.py` + `regex_filter.py` + `rate_limiter.py`
- **水位巡检**：`metrics/tps_probe.py` + `thresholds.py` + `sampler.py`
- **异常派发**：`dispatcher/anomaly_emitter.py` — AnomalyEvent → brain

---

## 预期文件结构

```
observer/
├── daemon.py
├── watchdog/
│   └── container_probe.py
├── logstream/
│   ├── ring_buffer.py
│   ├── regex_filter.py
│   └── rate_limiter.py
├── metrics/
│   ├── tps_probe.py
│   ├── thresholds.py
│   └── sampler.py
└── dispatcher/
    └── anomaly_emitter.py
```

---

## 实现前的注意事项

- 实现前先加载 `/observer-ref` 技能，参考 docker-py 和 mc-server-runner 的设计模式
- 日志流使用环形缓冲区，避免内存无限增长
- 事件防抖：短时间内同一异常不重复派发
- 守护进程必须低开销，不能影响服务端性能
