# `brain/actions/` · 合法动作枚举与执行器

诊断大脑输出的修复指令仅允许在预设白名单动作中选择。每个动作对应一个独立执行器，统一由 `registry.py` 注册与派发。

## 白名单动作（来自 PRD）

| 动作 | 文件 | 职责 |
|------|------|------|
| `MODIFY_JVM_ARGS` | `jvm_args.py` | 修改 JVM 内存参数（如解决 OOM） |
| `DISABLE_COMPONENT` | `disable_component.py` | 改后缀禁用模组（如隔离冲突 Mod） |
| `UPDATE_CONFIG` | `update_config.py` | 修改配置文件键值对（如 server.properties） |
| — | `registry.py` | 动作注册表与派发入口，未注册动作一律拒绝 |

## 设计约束

- **枚举锁定**：执行器仅接受白名单动作，任何未注册指令直接报错拦截。
- **路径安全**：所有动作执行前必须经 `brain/sandbox/path_guard.py` 校验（实例根目录锁定）。
- **可审计**：每个动作执行后产出审计记录，供 `memory/chatops/postmortem.py` 渲染战报。

## 多重故障处理

支持排队处理并发故障（如 OOM + 模组冲突）：第一轮 `MODIFY_JVM_ARGS` 解决内存，第二轮 `DISABLE_COMPONENT` 解决冲突，通过多次图流转层层剥离。
