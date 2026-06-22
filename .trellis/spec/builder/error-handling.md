# 异常处理

> `builder/errors.py` — 流水线异常类型层级与熔断机制

---

## 异常层级

```
Exception
└── BuildError                    ← builder 模块所有异常的基类
    ├── ZipSlipError              ← 解压时检测到目录穿越
    ├── UnrecognizedPackError     ← 既非引导包也非客户端
    ├── EulaRejectedError         ← 用户拒绝/超时未确认 EULA
    └── IntegrityError            ← 封账校验不通过
```

参考文件：`builder/errors.py`

---

## 各异常的触发与处理

| 异常 | 触发场景 | 处理 |
|---|---|---|
| `ZipSlipError` | 解压时 `target.relative_to(dest_resolved)` 抛 `ValueError` | 立即终止解压，pipeline 清理沙箱 |
| `UnrecognizedPackError` | discriminator 判别失败 | pipeline 清理沙箱，提示用户 |
| `EulaRejectedError` | 用户拒绝或超时未确认 EULA | pipeline 清理沙箱，返回终止文案 |
| `IntegrityError` | 封账校验不通过（缺核心/缺 EULA） | pipeline 清理沙箱，列出问题 |

---

## 熔断顺序

异常 → 清理本次沙箱（`_cleanup_sandbox`）→ 向上传播 → 调用方处理

```python
def _cleanup_sandbox(sandbox: Path) -> None:
    if sandbox.is_dir():
        try:
            shutil.rmtree(str(sandbox), ignore_errors=True)
        except Exception:
            pass
```

参考文件：`builder/pipeline.py:273-279`

---

## 降级策略

下载全部断流 → **不熔断**，跳过记入 `missing_mods.log`，交付时提醒服主手动补全。

这是关键设计决策：缺失 mod 不应阻断整个构建流程，因为部分 mod 可能确实在所有源都找不到（如作者撤回、CF 审核中），服主可以后续手动补全。

---

## CLI 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 构建成功 |
| 1 | 构建失败（解包/下载/校验异常） |
| 2 | EULA 拒绝/超时 |
| 130 | 用户 Ctrl+C 中断 |

参考文件：`builder/__main__.py:63-76`

---

## 新增异常的规则

1. 必须继承 `BuildError` 基类
2. 在 `builder/errors.py` 中定义
3. 在 `builder/__init__.py` 中导出并加入 `__all__`
4. 在 pipeline 中对应的 `except` 块中处理（含沙箱清理）
5. 在 CLI 中添加对应的退出码处理

---

## 反模式

- [禁止] 抛出非 `BuildError` 子类的异常（pipeline 无法统一捕获清理）
- [禁止] 在阶段函数中吞掉异常而不向上传播（沙箱不会被清理）
- [禁止] 将缺失 mod 当作异常熔断（应该降级记录，不阻断流程）
- [禁止] 在 `EulaRejectedError` 的 `__init__` 中硬编码中文消息而不区分拒绝/超时语义
