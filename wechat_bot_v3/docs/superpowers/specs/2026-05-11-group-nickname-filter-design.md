# 群聊昵称过滤 V2 + 统一 AI 兜底架构

## 问题

群聊 OCR 识别到 `昵称 + 消息正文`，旧过滤逻辑（左对齐 + ≤8字 + 下方50px有消息）使用绝对像素阈值，在不同窗口/缩放下漏过滤，导致机器人回复昵称。

## 方案

**空间聚类（主力，0延迟）→ AI 兜底（按需，仅含糊块）**

### 核心函数：`filter_group_nicknames(items, ai_client=None)`

输入：`[(text, y, left, w, h), ...]` — OCR 原始条目
输出：`[(text, y), ...]` — 过滤昵称后的消息列表

内部流程：

1. **自适应行高** — `avg_line_h = median(h)`，所有距离阈值以此为倍数
2. **并排归行** — Y 差 < `avg_line_h * 0.3` 的条目合并
3. **行归消息块** — 行间距 ≥ `avg_line_h * 2.5` 处切分
4. **块内识别昵称** — 多行块且首行 ≤15 字 → 首行 = 昵称
5. **群聊判定** — 不同昵称数 ≥ 2 → 群聊，启用过滤；否则跳过
6. **AI 兜底** — 仅在群聊 + 存在单行短文本含糊块时，调用一次 DeepSeek

### 群聊 vs 单聊自动判定

- 空间聚类后统计不同昵称候选数
- ≥ 2 → 群聊，过滤昵称
- < 2 → 单聊，全部当消息，不触发 AI

### AI 兜底接口

```
系统: 你是微信聊天OCR分析助手。从以下文字列表找出群成员昵称（消息上方的小号彩色文字）。
      返回JSON数组：{"names": [序号, ...]}

用户: [0]郑晨曦(y=120) [1]你好在吗(y=145) [2]丰鹏扬(y=260) [3]OK(y=380)
```

降级：超时 3s、格式错误 → 用聚类结果。

### 统一兜底架构（预留接口）

三个视觉检测任务使用同一 `DetectorResult` 接口：

```python
@dataclass
class DetectorResult:
    items: list       # 检测结果
    confidence: float # 0-1
    source: str       # "primary" | "ai_fallback"

class Detector(ABC):
    def detect(self, *args) -> DetectorResult: ...
    def detect_with_fallback(self, *args) -> DetectorResult: ...
```

| 检测任务 | 主检测器 | AI兜底 | 本次实现 |
|---------|---------|--------|---------|
| 群聊昵称 | 空间聚类 | DeepSeek 文本 | ✅ 完整实现 |
| 红点 | YOLO | 视觉模型 | 🔲 预留接口 |
| 绿色气泡 | HSV | 视觉模型 | 🔲 预留接口 |

## 修改范围

仅 `wechat_bot.py`：

1. 删除 `get_all_messages()` 中 L399-411 旧昵称过滤
2. 新增 `filter_group_nicknames()` 方法（空间聚类 + AI兜底）
3. 新增 `_ai_fallback_detect_nicknames()` 方法
4. `process_one_contact()` 中调用新方法替旧过滤

不改动其他文件。

## 验收标准

- 群聊中昵称正确过滤，不回复昵称
- 单聊中消息不受影响，不误杀短消息
- AI 兜底仅在含糊块触发（大部分情况无需调用）
- AI 失败时降级用聚类结果，不影响主流程
