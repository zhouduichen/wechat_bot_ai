# 识流 AI 助手 — 微信智能回复系统

基于 YOLO 视觉检测 + OCR 文字识别 + DeepSeek 大模型的微信自动化回复机器人。

## 架构

```
微信客户端 ←→ Python Bot (YOLO+OCR+自动化) ←→ PHP 后端 (规则+AI) ←→ DeepSeek API
                                                ↕
                                           MySQL 数据库
                                                ↕
                                          Web 管理后台
```

### 核心组件

| 组件 | 技术 | 说明 |
|------|------|------|
| 红点检测 | YOLOv11s | 训练模型检测联系人列表未读红点 |
| 消息识别 | 百度 OCR | 返回文字内容 + 像素坐标 |
| 气泡过滤 | OCR 位置 | 左半侧=对方消息，右半侧=自己已发 |
| 界面操作 | pyautogui + uiautomation | 点击、翻页、发送 |
| AI 回复 | DeepSeek API | 自然语言生成回复 |
| Web 后台 | PHP + MySQL | 规则管理、黑白名单、消息记录 |

## 项目结构

```
shiliu_ai/
├── admin.html              # Web 管理后台
├── config.php              # 配置文件（数据库/AI/API密钥）
├── db.php                  # 数据库连接
├── database.sql            # 数据库建表语句
├── ai_helper.php           # AI 调用逻辑（DeepSeek/Dify/OpenAI）
├── api_receive_message.php # 消息接收 & 回复生成接口
├── api_rules.php           # 关键词规则 CRUD 接口
├── api_policy.php          # 回复策略（黑白名单）接口
├── nginx.htaccess          # Nginx 重写规则
│
└── wechat_bot_v3/          # Python 机器人
    ├── wechat_bot.py       # 主程序
    ├── collect.py          # 收集红点训练样本
    ├── label.py            # 红点标注工具
    ├── train.py            # 训练红点检测模型
    ├── collect_bubble.py   # 收集绿色气泡训练样本
    ├── label_bubble.py     # 气泡标注工具
    ├── train_bubble.py     # 训练气泡检测模型
    ├── reply_policy.json   # 联系人回复策略
    ├── dataset/            # 红点训练数据
    ├── dataset_bubble/     # 气泡训练数据
    ├── model/              # 训练好的模型
    └── snapshots/          # 聊天截图缓存（去重用）
```

## 环境要求

- **Python 3.10+**，CUDA 显卡（推荐 RTX 3060+）
- **PHP 7.4+** + MySQL（phpstudy 即可）
- **Windows**（微信客户端 + UI 自动化依赖）

### Python 依赖

```bash
pip install ultralytics opencv-python numpy pillow pyautogui pyperclip uiautomation requests
```

### PHP 环境

确保 phpstudy 运行 Apache/Nginx + MySQL，项目放在网站根目录下。

导入数据库：

```bash
mysql -u root -p < database.sql
```

## 快速开始

### 1. 配置密钥

所有密钥支持环境变量，不写死明文：

| 密钥 | 环境变量 | 配置文件 |
|------|---------|---------|
| 数据库密码 | `DB_PASS` | config.php |
| DeepSeek API Key | `DEEPSEEK_API_KEY` | config.php |
| 百度 OCR Key | `BAIDU_API_KEY` | wechat_bot.py |
| 百度 OCR Secret | `BAIDU_SECRET_KEY` | wechat_bot.py |

或直接修改对应文件（不提交到 Git）。

### 2. 训练模型

**红点检测模型（必须）：**

```bash
cd wechat_bot_v3

# 收集截图（微信需要有未读红点）
python collect.py

# 标注红点（左键点击红点标注，D 下一张）
python label.py

# 训练
python train.py
# 输出 → model/wechat_dot.pt
```

**绿色气泡模型（可选，已有 OCR 位置过滤可替代）：**

```bash
python collect_bubble.py
python label_bubble.py
python train_bubble.py
# 输出 → model/wechat_bubble.pt
```

### 3. 启动

```bash
cd wechat_bot_v3
python wechat_bot.py
```

首次运行自动下载 YOLO 预训练权重。

### 4. 管理后台

浏览器打开 `http://127.0.0.1/shiliu_ai/admin.html`

- **总开关**：自动回复 + AI 回复独立控制
- **回复策略**：三种默认模式 + 白名单/黑名单管理
- **关键词规则**：先匹配规则，未命中走 AI
- **消息记录**：最近 50 条消息查看

## 工作流程

```
循环检测（每3秒）
  │
  ├─ 1. 截图联系人列表 → YOLO 检测红点
  │     └─ 无红点 → 滚到底部再查 → 仍无 → 等待下一轮
  │
  ├─ 2. 逐个红点处理（从上到下）
  │     │
  │     ├─ OCR 列表里读名字 → 命中黑名单？→ 跳过（不点击）
  │     ├─ 1 分钟内回复过？→ 跳过（冷却期）
  │     ├─ 鼠标被人为移动？→ 停止本轮
  │     │
  │     ├─ 点击联系人 → 截图对比判断有无新消息
  │     ├─ PageUp 翻页 → OCR 对方消息（左半侧，最多5条）
  │     ├─ 过滤关键词（谢谢/好的/纯时间/纯数字）
  │     │
  │     └─ 调 AI 生成回复 → 发送
  │
  └─ 等待 3 秒 → 下一轮
```

## 回复策略 (reply_policy.json)

```json
{
  "default": "reply",       // 默认模式: reply=全部回复 skip=仅白名单
  "always_reply": [],       // 白名单联系人
  "never_reply": [          // 黑名单联系人
    "文件传输助手", "微信团队",
    "公众号", "服务号", "订阅号", "微信支付"
  ],
  "contact_overrides": {}   // 单个联系人覆盖规则
}
```

黑名单采用模糊匹配，OCR 读到 "公众号:xxx" 也会命中 "公众号"。

## 模型训练参数

| 参数 | 红点模型 | 气泡模型 |
|------|---------|---------|
| 基础模型 | YOLO11s | YOLO11n |
| 图像尺寸 | 640 | 800 |
| Batch | 32 | 32 |
| Epochs | 30 | 40 |
| 建议数据量 | 200+ 张 | 150+ 张 |

## 常见问题

**Q: 红点检测不准？**
- 确认训练数据充足（200+ 张包含红点的截图）
- 验证 mAP@50 > 0.7
- 提高截图分辨率和标注质量

**Q: DeepSeek 响应慢？**
- API 响应约 1-42 秒，已设置 65 秒超时
- 可切换更快的模型或 API 提供商

**Q: 回复重复/回复自己的消息？**
- OCR 位置过滤：左半侧=对方，右半侧=忽略
- 冷却机制：同一联系人 60 秒内不重复打开

**Q: 群聊不想回复？**
- 黑名单添加群名或含 "群" 的关键词
- 支持模糊匹配

## License

MIT
