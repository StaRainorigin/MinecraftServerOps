# 契约定义

> `core/contracts/` — 所有跨阶段、跨模块的 Pydantic 模型定义规范

---

## 核心规则

1. **所有跨模块通信必须使用 Pydantic 模型，禁止裸 `dict`**
2. 契约文件按职责分拆，不要把所有模型塞进一个文件
3. 使用 `Field(default_factory=list)` 而非 `Field(default=[])` 避免可变默认值
4. 枚举继承 `(str, Enum)` 以支持 JSON 序列化
5. 在 `__init__.py` 中重新导出，简化导入路径

---

## 当前契约文件

| 文件 | 包含 |
|---|---|
| `manifest.py` | `Manifest`, `ModEntry`, `LoaderType`, `ModSource` |
| `build_results.py` | `BuildResult`, `InputMode`, `EulaDecision`, `UnpackResult`, `MissingMod`, `DownloadReport`, `IntegrityReport` |

---

## 新增契约的步骤

1. 确定归属文件（manifest 相关 → `manifest.py`；流程结果 → `build_results.py`；新领域 → 新文件）
2. 定义 Pydantic `BaseModel`，所有字段添加类型注解和 docstring
3. 在 `core/contracts/__init__.py` 中 `from .xxx import Yyy` 并加入 `__all__`
4. 在 builder spec 的 [contracts.md](../builder/contracts.md) 中记录生产者/消费者
5. 编写使用该契约的阶段函数签名

---

## 反模式

- [禁止] 在契约模型中包含方法逻辑（契约只承载数据）
- [禁止] 使用 `Optional[X] = None` 而非 `X | None = None`（本项目使用 `from __future__ import annotations`）
- [禁止] 忘记在 `__init__.py` 中重新导出（导致 `from core.contracts import X` 失败）
