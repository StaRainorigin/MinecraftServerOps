# `brain/nodes/` · 图状态机 5 节点

承载自愈闭环的 5 个核心节点，每个节点对应 PRD 模块三的一个阶段。

| 节点文件 | 阶段 | 职责 |
|----------|------|------|
| `snapshot.py` | 一 | 事务性前置快照：锁定 `server.properties`、`mods/` 等关键目录，创建秒级只读增量快照；**失败即熔断**，禁任何修改，转人工 |
| `diagnose.py` | 二 | 根因诊断：故障上下文喂 LLM 扮演专家（如通过 Mixins 冲突推断模组版本不兼容）；**严禁输出自然语言**，Pydantic 强约束输出 `ActionPlan` JSON |
| `execute.py` | 三 | 安全沙箱执行：白名单动作 + 路径穿越拦截（`../` 与 `/etc/` 越权直接拦截）；校验通过后模拟人工改文件 |
| `verify.py` | 四 | 闭环验证：调容器引擎重启 + 180s 观察期；分支 A 成功→进 critique；分支 B 再崩→捕获新报错+上次失败动作回 diagnose 反思 |
| `critique.py` | 五 | 元智能体审计：独立 Critic Agent 对比前后 TPS/资源健康度打分（0-100）；修复致 TPS 掉到 5.0 判不及格→拒成果+强制回滚 |

## 流转契约

- 节点间通过 `brain/state.py` 的图状态传递（当前轮次、历史 ActionPlan、反思上下文）。
- 反思重试受 `MAX_RETRIES = 3` 全局计数器约束（见 `graph.py`）。
