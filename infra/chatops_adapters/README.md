# `infra/chatops_adapters/` · IM 平台适配器

各 IM 平台的具体推送实现，由 `memory/chatops/notifier.py` 按配置选择调用。

## 文件职责

| 文件 | 平台 | 职责 |
|------|------|------|
| `discord.py` | Discord | Webhook / Bot 推送战报卡片 + 反馈按钮交互回调 |
| `qq.py` | QQ | 机器人推送战报（卡片/文本）+ 反馈回调 |
| `dingtalk.py` | 钉钉 | 群机器人 Webhook 推送战报 + 反馈回调 |

## 设计原则

- **统一接口**：三个适配器实现相同的推送/回调接口，`notifier.py` 按配置注入，无需关心平台差异。
- **反馈回调**：每个适配器需接收用户的 👍/👎 操作并回传给 `memory/chatops/feedback.py` 触发留存或回滚。
