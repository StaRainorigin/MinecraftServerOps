---
name: brain-ref
description: 编写 brain 模块（AI 决策大脑与自愈闭环）功能时自动加载的参考指南。当你需要实现图状态机、LLM 诊断、安全沙箱执行、闭环验证、Critic 评估、反思重试等 brain/ 下任何功能时，务必先阅读本技能中的参考项目指引，从 LangGraph/Swarms/LangChain 中找到经过验证的 API 用法和设计模式再动手。
---

# Brain 模块参考指南

编写 `brain/` 模块功能时，核心依赖是 LangGraph 的图状态机 API。所有参考项目位于 `references/` 目录。

## 节点速查表

| 节点 | 子文件 | 你在写什么 | 核心参考项目 |
|------|--------|-----------|-------------|
| ① | `nodes/snapshot.py` | 事务性前置快照 | LangGraph Checkpoint |
| ② | `nodes/diagnose.py` | LLM 根因诊断 + Pydantic 强约束输出 | LangChain、LangGraph |
| ③ | `nodes/execute.py` | 安全沙箱执行 | 自行设计（白名单+路径校验） |
| ④ | `nodes/verify.py` | 180s 观察期 + 反思重试分支 | LangGraph 条件边 |
| ⑤ | `nodes/critique.py` | Critic Agent 打分 | Swarms |
| — | `graph.py` | 图状态机构建 | LangGraph |
| — | `state.py` | 图状态定义 | LangGraph |
| — | `actions/` | 合法动作枚举与执行器 | LangChain Tools |
| — | `sandbox/` | 路径安全校验 | 自行设计 |
| — | `rollback/` | 快照回滚 | LangGraph Checkpoint |

---

## 图状态机构建 → 读 LangGraph

**你要读的文件：**

- `references/langgraph/libs/langgraph/langgraph/graph/state.py` — StateGraph 类：add_node / add_edge / add_conditional_edges / compile
- `references/langgraph/libs/langgraph/langgraph/types.py` — RetryPolicy / TimeoutPolicy / Command / Send / StateSnapshot
- `references/langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py` — BaseCheckpointSaver：put / get / list / delete
- `references/langgraph/libs/checkpoint/langgraph/checkpoint/memory/__init__.py` — InMemorySaver 实现

### StateGraph 核心 API

```python
from langgraph.graph import StateGraph, START, END

# 1. 定义状态（TypedDict，字段可用 Annotated[type, reducer] 指定合并策略）
class HealingState(TypedDict):
    anomaly_event: AnomalyEvent          # 输入：异常事件
    snapshot_id: str                      # 快照 ID
    action_plan: ActionPlan | None        # 诊断产出的修复计划
    retry_count: int                      # 当前重试轮次
    reflection_context: str | None        # 反思上下文（上次失败原因）
    verify_result: str                    # "success" / "retry" / "max_retries"
    critic_score: int                     # 0-100
    error_log: list[str]                  # 执行过程中的错误日志

# 2. 构建图
graph = (
    StateGraph(HealingState)
    .add_node("snapshot", take_snapshot)
    .add_node("diagnose", diagnose_root_cause)
    .add_node("execute", execute_action_plan)
    .add_node("verify", verify_and_observe)
    .add_node("critique", critic_evaluate)
    .add_node("rollback", absolute_rollback)
    # 边
    .add_edge(START, "snapshot")
    .add_edge("snapshot", "diagnose")
    .add_edge("diagnose", "execute")
    .add_edge("execute", "verify")
    # 条件分支
    .add_conditional_edges("verify", route_after_verify, {
        "success": "critique",
        "retry": "diagnose",      # 反思重试
        "max_retries": "rollback",
    })
    .add_conditional_edges("critique", route_after_critique, {
        "pass": END,
        "fail": "rollback",       # 评分不及格 → 回滚
    })
    .add_edge("rollback", END)
    # 编译（带 Checkpoint）
    .compile(checkpointer=InMemorySaver())
)
```

### 条件分支路由函数

```python
def route_after_verify(state: HealingState) -> str:
    """验证节点后的路由逻辑。"""
    if state["verify_result"] == "success":
        return "success"
    if state["retry_count"] >= 3:  # MAX_RETRIES
        return "max_retries"
    return "retry"  # 反思重试

def route_after_critique(state: HealingState) -> str:
    """Critic 评分后的路由逻辑。"""
    if state["critic_score"] >= 60:  # PRD: <60 回滚
        return "pass"
    return "fail"
```

### add_node 高级参数

```python
# 节点级重试策略（基础设施级，如网络超时）
graph.add_node(
    "diagnose",
    diagnose_root_cause,
    retry_policy=RetryPolicy(
        initial_interval=0.5,
        backoff_factor=2.0,
        max_attempts=3,
        retry_on=httpx.TimeoutException,  # 仅对超时重试
    ),
)

# 节点级错误处理（自愈兜底）
graph.add_node(
    "execute",
    execute_action_plan,
    error_handler=execution_fallback,  # 执行失败时的兜底节点
)
```

### Command 动态路由

节点可以返回 `Command` 对象来动态更新状态并路由：

```python
from langgraph.types import Command

def verify_and_observe(state: HealingState) -> Command:
    # 180s 观察期...
    if tps_stable and no_new_errors:
        return Command(update={"verify_result": "success"}, goto="critique")
    elif state["retry_count"] >= 3:
        return Command(update={"verify_result": "max_retries"}, goto="rollback")
    else:
        return Command(
            update={
                "verify_result": "retry",
                "retry_count": state["retry_count"] + 1,
                "reflection_context": "上次修复导致二次崩溃...",
            },
            goto="diagnose",
        )
```

---

## Checkpoint 快照与回滚 → 读 LangGraph Checkpoint

**你要读的文件：**

- `references/langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py` — Checkpoint TypedDict 和 BaseCheckpointSaver
- `references/langgraph/libs/langgraph/langgraph/pregel/main.py` — get_state / get_state_history / update_state

### Checkpoint 数据结构

```python
class Checkpoint(TypedDict):
    v: int                    # 格式版本（当前为 1）
    id: str                   # 单调递增的唯一 ID
    ts: str                   # ISO 8601 时间戳
    channel_values: dict      # 反序列化的状态快照
    channel_versions: dict    # 每个通道的版本字符串
    versions_seen: dict       # 节点 → 通道 → 上次看到的版本
```

### 回滚模式

```python
# 编译时注入 checkpointer
app = graph.compile(checkpointer=InMemorySaver())

# 运行时指定 thread_id（每个服务端实例一个 thread）
config = {"configurable": {"thread_id": instance_id}}

# 正常执行
result = app.invoke(initial_state, config)

# 回滚到初始快照
history = list(app.get_state_history(config))
initial_checkpoint = history[-1]  # 最早的 checkpoint
# 用初始 checkpoint 的 config 重新 invoke
app.invoke(None, initial_checkpoint.config)
```

### 重要区分

LangGraph Checkpoint 保存的是**图状态**（Python 对象），不是文件系统快照。PRD 要求的"事务性前置快照"需要**两层**：

1. **图状态快照**：LangGraph Checkpoint 自动处理（每个节点执行后自动保存）
2. **文件系统快照**：需在 `nodes/snapshot.py` 中自行实现（复制 mods/、config/、server.properties 等关键目录到 `.snapshots/` 隔离区）

如果文件系统快照创建失败（如磁盘空间不足），必须**熔断自愈流程**，禁止进入 diagnose 节点。

---

## LLM 诊断 + Pydantic 强约束输出 → 读 LangChain

**你要读的文件：**

- `references/langchain/libs/core/langchain_core/output_parsers/pydantic.py` — PydanticOutputParser
- `references/langchain/libs/core/langchain_core/language_models/chat_models.py` — with_structured_output（line 2357）
- `references/langchain/libs/core/langchain_core/tools/base.py` — BaseTool、InjectedToolArg、create_schema_from_function

### PRD 要求

"诊断大脑严禁输出自然语言，必须输出标准 ActionPlan JSON"

### 推荐实现：with_structured_output

```python
from pydantic import BaseModel, Field
from typing import Literal
from langchain_core.language_models import BaseChatModel

class Action(BaseModel):
    """单个修复动作。"""
    type: Literal["MODIFY_JVM_ARGS", "DISABLE_COMPONENT", "UPDATE_CONFIG"] = Field(
        description="动作类型"
    )
    target: str = Field(description="目标文件路径或参数名")
    value: str = Field(description="修改值")
    reason: str = Field(description="修改原因（供审计日志）")

class ActionPlan(BaseModel):
    """LLM 诊断输出的修复计划。"""
    root_cause: str = Field(description="一句话根因摘要")
    confidence: float = Field(ge=0, le=1, description="诊断置信度")
    actions: list[Action] = Field(description="修复动作序列（按执行顺序）")

# 使用 with_structured_output（Function Calling 强制输出符合 Schema 的 JSON）
structured_model = model.with_structured_output(ActionPlan)

# 调用
plan: ActionPlan = structured_model.invoke(diagnosis_prompt)
# plan 是经过 Pydantic 校验的 ActionPlan 实例，不可能包含自然语言
```

### 降级方案：PydanticOutputParser

对不支持 Function Calling 的模型：

```python
from langchain_core.output_parsers import PydanticOutputParser

parser = PydanticOutputParser[ActionPlan](pydantic_object=ActionPlan)

# 在 prompt 中注入格式指令
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是 Minecraft 服务端故障诊断专家。{format_instructions}"),
    ("human", "{error_context}"),
]).partial(format_instructions=parser.get_format_instructions())

chain = prompt | model | parser
plan: ActionPlan = chain.invoke({"error_context": error_log})
```

### Tool/Action 抽象

LangChain 的 `BaseTool` 可以用来定义合法动作白名单：

```python
from langchain_core.tools import tool

@tool
def modify_jvm_args(target: str, value: str, reason: str) -> str:
    """修改 JVM 启动参数（如 -Xmx）。target 为参数名，value 为新值。"""
    # 实际执行逻辑在 brain/actions/ 中
    return f"已修改 {target} = {value}"

@tool
def disable_component(target: str, reason: str) -> str:
    """禁用模组（改后缀为 .disabled）。target 为 mods/ 下的文件名。"""
    return f"已禁用 {target}"

@tool
def update_config(target: str, key: str, value: str, reason: str) -> str:
    """修改配置文件键值对。target 为配置文件路径，key 为键名，value 为新值。"""
    return f"已修改 {target}[{key}] = {value}"
```

---

## Critic Agent 评估 → 读 Swarms

**你要读的文件：**

- `references/swarms/swarms/structs/debate_with_judge.py` — Pro vs Con + Judge 辩论模式
- `references/swarms/swarms/structs/council_as_judge.py` — 6 维度并行评估 + 聚合
- `references/swarms/swarms/agents/flexion_agent.py` — Reflexion 框架：Act→Evaluate→Reflect→Refine
- `references/swarms/swarms/agents/agent_judge.py` — 独立 Judge Agent

### 推荐模式：CouncilAsAJudge 多维度评估

PRD 要求 Critic Agent 对修复行为综合打分（0-100），评分不及格则回滚。Swarms 的 CouncilAsAJudge 提供了多维度并行评估模式，比单一打分更可靠：

```python
# 评估维度（参考 CouncilAs_Judge 的 6 维度模式，适配 MC 场景）
EVALUATION_DIMENSIONS = {
    "tps_recovery": "TPS 是否恢复到稳定水平（>=15）",
    "memory_health": "内存使用率是否回到安全区间（<80%）",
    "mod_compatibility": "被禁用的模组是否导致前置缺失",
    "config_consistency": "配置修改是否与现有配置冲突",
}

# 每个维度独立评分 0-100，加权平均
WEIGHTS = {
    "tps_recovery": 0.35,
    "memory_health": 0.25,
    "mod_compatibility": 0.25,
    "config_consistency": 0.15,
}
```

### Reflexion 反思循环

Swarms 的 ReflexionAgent 直接映射 PRD 的反思重试：

```
Act（执行修复）→ Evaluate（验证结果）→ Reflect（生成反思）→ Refine（改进计划）
```

在 LangGraph 中实现为条件边回指 diagnose 节点，每次重试时将上次失败的 ActionPlan 和新的报错日志一起喂给 LLM：

```python
def diagnose_root_cause(state: HealingState) -> dict:
    # 构建反思上下文
    if state.get("reflection_context"):
        prompt = f"""
        上一次修复失败，原因：{state['reflection_context']}
        上一次执行的动作：{state.get('action_plan')}
        新的报错日志：{state['anomaly_event'].log_context}
        请重新制定修复计划，避免重复上次的错误。
        """
    else:
        prompt = f"故障日志：{state['anomaly_event'].log_context}"
    # ...
```

---

## 安全沙箱执行

此部分无直接参考项目，需自行设计。关键约束：

1. **白名单动作**：仅允许 `MODIFY_JVM_ARGS` / `DISABLE_COMPONENT` / `UPDATE_CONFIG`
2. **路径锁定**：所有指令的绝对路径必须被锁定在当前实例根目录下
3. **目录穿越拦截**：任何包含 `../` 的路径直接拒绝
4. **静默修改**：改后缀 `.disabled` 而非删除，确保可逆

```python
from pathlib import Path

def validate_path(target: str, instance_root: Path) -> Path:
    """校验目标路径是否在实例根目录下。"""
    resolved = (instance_root / target).resolve()
    if not str(resolved).startswith(str(instance_root.resolve())):
        raise PathEscapeError(f"路径越权：{target} 试图访问实例根目录之外")
    if ".." in Path(target).parts:
        raise PathEscapeError(f"路径穿越：{target} 包含 '..'")
    return resolved
```

---

## 实操步骤

当你开始实现 brain 某个功能时：

1. 确定节点/子系统，找到上表对应的参考项目
2. 用 Read 工具阅读"你要读的文件"中列出的源码
3. LangGraph API 优先——先看 StateGraph 的 add_node / add_conditional_edges / compile
4. LLM 输出约束用 LangChain 的 with_structured_output
5. Critic 评估参考 Swarms 的多维度模式
6. 确保新代码与 `core/contracts/` 中的 AnomalyEvent 契约兼容
7. 确保文件系统快照与 LangGraph Checkpoint 两层都实现
