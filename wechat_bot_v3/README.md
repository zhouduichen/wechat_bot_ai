# 微信 AI 自动回复机器人

基于 YOLO 红点检测 + 百度 OCR + DeepSeek AI 的微信自动回复机器人。

## 功能

- **红点检测**：YOLO 模型检测未读消息红点，含固定红点过滤和点击前验证
- **智能 OCR**：百度 OCR 识别聊天文字，自动遮罩绿色气泡（自己消息）
- **消息意图判断**：规则 + AI 双层判断，过滤无意义消息和人名
- **防重复**：绿泡检测 + 已发文字集合 + 3分钟跨轮去重 + 本轮去重
- **逐条回复**：从旧到新最多 5 条，尾扫最多 3 轮
- **策略管理**：黑名单/白名单、跳过关键词、冷却机制

## 环境要求

- Python 3.8+
- Windows（依赖 uiautomation、pyautogui）
- 微信 PC 客户端

## 安装

```bash
pip install ultralytics opencv-python numpy pillow requests pyperclip pyautogui uiautomation
```

## 配置

| 变量 | 说明 |
|------|------|
| `BAIDU_API_KEY` | 百度 OCR API Key |
| `BAIDU_SECRET_KEY` | 百度 OCR Secret Key |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |

默认值在 `wechat_bot.py` 顶部，可通过环境变量覆盖。

## 文件说明

| 文件 | 作用 |
|------|------|
| `wechat_bot.py` | 主程序 |
| `train.py` | YOLO 红点检测模型训练 |
| `bot_gui.py` | GUI 管理面板 |
| `admin_panel.html` | Web 管理面板 |
| `reply_policy.json` | 回复策略（黑名单/白名单） |
| `skip_keywords.json` | 不回复关键词 |
| `auto_reply_rules.json` | 本地自动回复规则 |
| `model/wechat_dot.pt` | 训练好的红点检测模型 |

## 使用

```bash
python wechat_bot.py
```

启动前确保微信 PC 客户端已打开并登录。
