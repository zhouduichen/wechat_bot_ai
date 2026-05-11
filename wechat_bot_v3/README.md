# 微信 AI 自动回复机器人

基于 YOLO 红点检测 + OCR 文字识别 + DeepSeek AI 的微信自动回复机器人。

## 功能

- **红点检测**：YOLO 模型检测微信联系人列表中的未读消息红点
- **智能 OCR**：百度 OCR 识别聊天文字，自动遮罩自己发送的绿色气泡
- **群聊昵称过滤**：空间聚类自动识别并过滤群成员昵称，AI 兜底判断
- **逐条回复**：从旧到新逐条回复未读消息，支持多轮尾扫
- **策略管理**：黑名单/白名单联系人、跳过关键词、冷却机制

## 环境要求

- Python 3.8+
- Windows（依赖 uiautomation、pyautogui）
- 微信 PC 客户端

## 安装

```bash
pip install ultralytics opencv-python numpy pillow requests pyperclip pyautogui uiautomation
```

## 配置

设置环境变量（推荐）或直接修改 `wechat_bot.py` 中的默认值：

| 变量 | 说明 |
|------|------|
| `BAIDU_API_KEY` | 百度 OCR API Key |
| `BAIDU_SECRET_KEY` | 百度 OCR Secret Key |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |

## 文件说明

| 文件 | 作用 |
|------|------|
| `wechat_bot.py` | 主程序，自动回复机器人 |
| `train.py` | YOLO 模型训练脚本（红点检测） |
| `bot_gui.py` | GUI 管理面板 |
| `reply_policy.json` | 回复策略（黑名单/白名单） |
| `skip_keywords.json` | 不回复的关键词配置 |
| `auto_reply_rules.json` | 本地自动回复规则 |
| `model/wechat_dot.pt` | 训练好的 YOLO 红点检测模型 |

## 使用

```bash
# 启动机器人
python wechat_bot.py

# 训练红点检测模型
python train.py
```

启动前确保微信 PC 客户端已打开并登录。

## License

MIT
