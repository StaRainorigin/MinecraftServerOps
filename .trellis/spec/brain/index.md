# brain 模块编码规范

> 模块三：AI 决策大脑与自愈闭环 (LangGraph 图状态机)
> 状态：[骨架] 阶段（仅占位 docstring）

---

## 当前状态

所有文件均为占位骨架，仅包含模块 docstring，逻辑待后续填充。

---

## 设计规划

根据 PRD，brain 模块应实现：

- **LangGraph 图状态机**：snapshot → diagnose → execute → verify → critique 节点流转
- **LLM 诊断**：根因分析，输出结构化 `ActionPlan`（禁止自然语言）
- **安全沙箱执行**：`brain/sandbox/path_guard.py` — 路径守卫，防止修复操作越界
- **闭环验证**：execute 后自动 verify，critique 评估修复质量
- **反思重试**：验证失败时回滚快照（`brain/rollback/restorer.py`）并重试

---

## 预期文件结构

```
brain/
├── graph.py          # LangGraph 状态机构建与节点流转
├── state.py          # 图状态定义（当前轮次/历史 ActionPlan/反思上下文/MAX_RETRIES）
├── nodes/
│   ├── diagnose.py   # 根因诊断节点
│   ├── execute.py    # 修复执行节点
│   ├── verify.py     # 闭环验证节点
│   ├── critique.py   # Critic 评估节点
│   └── snapshot.py   # 快照管理节点
├── actions/
│   ├── registry.py   # 动作注册表与派发入口
│   ├── update_config.py   # 配置修改动作
│   ├── disable_component.py  # 组件禁用动作
│   └── jvm_args.py   # JVM 参数调整动作
├── rollback/
│   └── restorer.py   # 快照回滚恢复
└── sandbox/
    └── path_guard.py # 路径安全守卫
```

---

## 实现前的注意事项

- 实现前先加载 `/brain-ref` 技能，参考 LangGraph/Swarms/LangChain 的验证 API
- 动作注册表必须严格校验，未注册动作一律拒绝执行
- 快照回滚必须验证完整性（防止部分恢复导致不一致状态）
- LLM 输出必须用 Pydantic 强约束，禁止自然语言格式
