# `brain/` · 【模块三】AI 决策大脑与自愈闭环

MC-SRE 系统的"核心调度层"与"行动层"（决策与自愈控制面）。完全由事件驱动、具备反思能力的图状态机（State Graph）。接收异常感知层的故障事件，利用 LLM 语义推理进行根因分析，在宿主机安全沙箱内执行精细化修复，实现故障无人值守自愈。

## 5 节点图状态机

```
[AnomalyEvent]
      │
      ▼
①snapshot ──失败──▶ 熔断(转人工告警)
      │成功
      ▼
②diagnose (LLM 根因 + Pydantic 强约束 ActionPlan)
      │
      ▼
③execute (安全沙箱,白名单/路径穿越拦截)
      │
      ▼
④verify (180s 观察期)
      ├──分支A 成功──▶ ⑤critique (Critic 打分)
      └──分支B 再崩──▶ 反思 ──回──▶ ②diagnose (轮次 < MAX_RETRIES)
                              │
                              └──轮次≥3──▶ 绝对事务回滚 + 呼叫人工
```

| 节点 | 子文件 | 职责 |
|------|--------|------|
| ① | `nodes/snapshot.py` | 事务性前置快照（失败即熔断，禁任何修改） |
| ② | `nodes/diagnose.py` | 根因诊断 + Pydantic 强约束输出 `ActionPlan` |
| ③ | `nodes/execute.py` | 安全沙箱执行（白名单动作 + 路径穿越拦截） |
| ④ | `nodes/verify.py` | 180s 观察期 + 反思重试分支 |
| ⑤ | `nodes/critique.py` | Critic Agent 打分（LLM-as-a-Judge，<60 回滚） |

## 入口与状态

- `graph.py`：LangGraph 状态机构建与节点流转编排
- `state.py`：图状态定义（当前轮次 / 历史 ActionPlan / 反思上下文 / 触顶计数）

## 辅助子系统

- `actions/`：合法动作枚举与执行器（`MODIFY_JVM_ARGS` / `DISABLE_COMPONENT` / `UPDATE_CONFIG`）
- `sandbox/`：路径安全校验（实例根目录锁定，`../` 越权拦截）
- `rollback/`：快照回滚（MAX_RETRIES 触顶 / RLHF 踩 触发绝对事务回滚）

## 关键约束

- **MAX_RETRIES = 3**：防 AI 幻觉导致"修改-重启-崩溃-再修改"死循环，触顶即绝对回滚 + 呼叫人工。
- **诊断输出严禁自然语言**：必须 Pydantic 校验的标准 `ActionPlan` JSON。
- **动作白名单锁定**：仅允许预设动作，绝对路径必须锁定在实例根目录下。

## 输入输出

- **输入**：`AnomalyEvent`（硬件指标 + 触发类型 + 200 行截断日志流）
- **输出**：①`ActionPlan` JSON ②事务性快照回滚/恢复状态报告 ③自愈审计日志（投递 ChatOps）
