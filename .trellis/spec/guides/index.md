# Thinking Guides

> **Purpose**: Expand your thinking to catch things you might not have considered.

---

## Why Thinking Guides?

**Most bugs and tech debt come from "didn't think of that"**, not from lack of skill:

- Didn't think about what happens at layer boundaries → cross-layer bugs
- Didn't think about code patterns repeating → duplicated code everywhere
- Didn't think about edge cases → runtime errors
- Didn't think about future maintainers → unreadable code

These guides help you **ask the right questions before coding**.

---

## Available Guides

| Guide | Purpose | When to Use |
|-------|---------|-------------|
| [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md) | Identify patterns and reduce duplication | When you notice repeated patterns |
| [Cross-Layer Thinking Guide](./cross-layer-thinking-guide.md) | Think through data flow across layers | Features spanning multiple layers |

---

## MC-SRE 特有的跨层边界

本项目的关键跨层边界：

| 边界 | 数据流 | 常见问题 |
|---|---|---|
| metadata → fetcher | `Manifest` + `ModEntry` | CF 占位文件名未解析就传入下载 |
| fetcher → deliver | `DownloadReport` + `MissingMod` | 缺失 mod 被当作异常而非降级 |
| observer → brain | `AnomalyEvent` | 事件防抖不足导致重复诊断 |
| brain → memory | 修复经验 | 错误经验污染知识库 |
| memory → brain | 命中记忆 | 秒修短路未验证就执行 |

---

## Quick Reference: Thinking Triggers

### When to Think About Cross-Layer Issues

- [ ] Feature touches 3+ layers (pipeline stages, core contracts, infra adapters)
- [ ] Data format changes between stages (e.g., CF `(pid, fid)` → `ResolvedFile` → URL list)
- [ ] Multiple consumers need the same data (e.g., `Manifest` used by fetcher + install + launch)
- [ ] You're not sure where to put some logic
- [ ] You are adding a new `LoaderType` enum value, `InputMode` variant, or config field
- [ ] Pipeline code starts casting raw payload fields directly

→ Read [Cross-Layer Thinking Guide](./cross-layer-thinking-guide.md)

### When to Think About Code Reuse

- [ ] You're writing similar code to something that exists
- [ ] You see the same pattern repeated 3+ times
- [ ] You're adding a new field to multiple places
- [ ] **You're modifying any constant or config**
- [ ] **You're creating a new utility/helper function** ← Search first!
- [ ] Two files read the same untyped payload field with local casts

→ Read [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md)

### MC-SRE 枚举扩展检查清单

当新增 `LoaderType` / `InputMode` / `ModSource` 等枚举值时，必须同步更新：

- [ ] `core/contracts/manifest.py` — 枚举定义
- [ ] `builder/fetcher/sources.py` — URL 构造逻辑
- [ ] `builder/install/installer.py` — 安装器执行逻辑
- [ ] `builder/launch/script_gen.py` — 启动脚本生成逻辑
- [ ] `.trellis/spec/builder/contracts.md` — 契约文档

---

## Pre-Modification Rule (CRITICAL)

> **Before changing ANY value, ALWAYS search first!**

```bash
# Search for the value you're about to change
grep -r "value_to_change" .
```

This single habit prevents most "forgot to update X" bugs.

---

## How to Use This Directory

1. **Before coding**: Skim the relevant thinking guide
2. **During coding**: If something feels repetitive or complex, check the guides
3. **After bugs**: Add new insights to the relevant guide (learn from mistakes)

---

**Core Principle**: 30 minutes of thinking saves 3 hours of debugging.
