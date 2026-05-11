# 群聊昵称过滤 V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace absolute-pixel nickname filter with spatial clustering + AI fallback, auto-detecting group vs 1-on-1 chat.

**Architecture:** `get_all_messages()` keeps raw OCR data (w,h included). `filter_group_nicknames()` does spatial clustering using adaptive line-height ratios, identifies nicknames in multi-line message blocks, auto-detects group chat, and calls DeepSeek only for ambiguous single-line blocks.

**Tech Stack:** Python, Baidu OCR, DeepSeek API (existing), OpenCV/numpy (existing)

**Files:**
- Modify: `wechat_bot.py` — delete old filter L399-411, add 3 new methods, update 7 tuple unpacking sites
- No new files

---

### Task 1: Add `DetectorResult` dataclass (reserved for future AI fallback hooks)

**Files:** Modify `wechat_bot.py` (after imports, before class)

- [ ] **Step 1: Add dataclass**

Insert after the `SKIP_KEYWORDS_PATH` block (after line 62) and before `load_skip_keywords()`:

```python
from dataclasses import dataclass
from typing import List, Any

@dataclass
class DetectorResult:
    """统一检测结果接口，预留红点/气泡 AI 兜底用"""
    items: List[Any]
    confidence: float
    source: str  # "primary" | "ai_fallback"
```

- [ ] **Step 2: Commit**

```bash
git add wechat_bot.py
git commit -m "feat: add DetectorResult dataclass for future AI fallback hooks"
```

---

### Task 2: Update `get_all_messages()` — include w,h, delete old filter

**Files:** Modify `wechat_bot.py` L397-422

- [ ] **Step 1: Include w,h in message tuple**

Change line 397 from:
```python
msgs.append((text, text_y, False, left))
```
To:
```python
msgs.append((text, text_y, False, left, w, h))
```

- [ ] **Step 2: Delete old nickname filter**

Delete lines 399-411 (the entire `# 过滤群聊名字` block):
```python
        # 过滤群聊名字：贴左边 + 短 + 下方50px内有另一条对方消息
        n_name = 0
        left_limit = max(55, aw * 0.08)
        filtered = []
        for i, (t, ty, _, l) in enumerate(msgs):
            if (l < left_limit and len(t.strip()) <= 8 and
                any(oy > ty and oy - ty < 50 for _, oy, _, _ in msgs)):
                n_name += 1
                continue
            filtered.append((t, ty, False, l))
        if n_name > 0:
            logger.info(f"  过滤群名: {n_name}条")
        msgs = filtered
```

Also delete line 393 (`aw = region[2] - region[0]`) since `aw` was only used by the old filter:
```python
        aw = region[2] - region[0]
```

- [ ] **Step 3: Update sample log line**

Change line 422 from:
```python
            logger.info(f"  样本: {' | '.join(t[:12] for t, _, _, _ in msgs[:6])}")
```
To:
```python
            logger.info(f"  样本: {' | '.join(t[:12] for t, _, _, _, _, _ in msgs[:6])}")
```

- [ ] **Step 4: Update docstring**

Change line 361 from:
```
        msgs: [(text, screen_y, is_self=False, left), ...]
```
To:
```
        msgs: [(text, screen_y, is_self=False, left, w, h), ...]
```

- [ ] **Step 5: Commit**

```bash
git add wechat_bot.py
git commit -m "refactor: include w,h in OCR tuple, remove old nickname filter"
```

---

### Task 3: Add `_ai_fallback_detect_nicknames()` method

**Files:** Modify `wechat_bot.py` (add inside `WechatBotV6` class, before `filter_group_nicknames`)

- [ ] **Step 1: Add method after `should_skip` (after line 550)**

```python
    def _ai_fallback_detect_nicknames(self, items):
        """AI兜底识别群聊昵称。失败返回空set，调用方降级用聚类结果。
        items: [(text, y, left, w, h), ...]
        """
        prompt_parts = []
        for i, (text, y, left, w, h) in enumerate(items):
            prompt_parts.append(f"[{i}]{text}(y={y})")
        prompt = "\n".join(prompt_parts)

        system_prompt = (
            "你是微信聊天OCR分析助手。"
            "以下是一个群聊窗口OCR识别的文字列表，每项格式为[序号]文字(y=纵向坐标)。"
            "群成员昵称是显示在消息上方的小号彩色文字，通常很短（≤15字），位于消息正文的正上方。"
            "请找出所有群成员昵称，返回JSON：{\"names\": [\"昵称1\", \"昵称2\"]}。"
            "不要返回其他内容。"
        )

        try:
            url = f"{DEEPSEEK_API_BASE}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            }
            payload = {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 100,
            }
            r = requests.post(url, headers=headers, json=payload, timeout=3)
            if r.status_code == 200:
                d = r.json()
                content = d.get("choices", [{}])[0].get("message", {}).get("content", "")
                # 提取JSON（兼容非JSON模式）
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
                data = json.loads(content)
                names = data.get("names", [])
                if isinstance(names, list):
                    logger.info(f"AI昵称兜底识别: {names}")
                    return set(n.strip() for n in names if n.strip())
        except Exception as e:
            logger.info(f"AI昵称兜底失败，降级用聚类结果: {e}")

        return set()
```

- [ ] **Step 2: Commit**

```bash
git add wechat_bot.py
git commit -m "feat: add AI fallback for ambiguous group nickname detection"
```

---

### Task 4: Add `filter_group_nicknames()` method

**Files:** Modify `wechat_bot.py` (add inside `WechatBotV6` class, after `_ai_fallback_detect_nicknames`)

- [ ] **Step 1: Add method**

```python
    def filter_group_nicknames(self, items):
        """空间聚类 + 群聊昵称过滤。必要时AI兜底。
        items: [(text, y, left, w, h), ...]
        返回: [(text, y), ...] 过滤昵称后的消息
        """
        if not items:
            return []

        # 1. 自适应行高
        heights = [h for _, _, _, _, h in items if h > 0]
        if not heights:
            return [(t, y) for t, y, _, _, _ in items]
        avg_h = sorted(heights)[len(heights) // 2]
        if avg_h < 10:
            avg_h = 16

        SAME_LINE = avg_h * 0.3
        NEW_BLOCK = avg_h * 2.5

        # 2. 并排归行：Y差 < SAME_LINE 的条目合并
        sorted_items = sorted(items, key=lambda x: x[1])
        lines = []  # [[(text,y,left,w,h), ...], ...]
        for entry in sorted_items:
            text, y, left, w, h = entry
            placed = False
            for line in lines:
                if abs(y - line[0][1]) < SAME_LINE:
                    line.append(entry)
                    placed = True
                    break
            if not placed:
                lines.append([entry])

        # 3. 行归块：间距 >= NEW_BLOCK 处切分
        blocks = []  # [[(text,y,left), ...], ...]
        # 每行取最长文本
        current = [(max(lines[0], key=lambda x: len(x[0]))[0],
                     lines[0][0][1],
                     min(lines[0], key=lambda x: x[2])[2])]

        for i in range(1, len(lines)):
            prev_max_y = max(it[1] + it[4] for it in lines[i - 1])  # prev line bottom
            curr_min_y = min(it[1] for it in lines[i])              # curr line top
            gap = curr_min_y - prev_max_y

            if gap >= NEW_BLOCK:
                blocks.append(current)
                current = []

            best = max(lines[i], key=lambda x: len(x[0]))
            current.append((best[0], best[1], best[2]))

        blocks.append(current)

        # 4. 块内识别昵称
        nicknames = set()
        ambiguous_blocks = []

        for bi, block in enumerate(blocks):
            if len(block) == 1:
                if len(block[0][0].strip()) <= 15:
                    ambiguous_blocks.append(bi)
            elif len(block) >= 2:
                first = block[0][0].strip()
                if len(first) <= 15:
                    nicknames.add(first)

        # 5. 群聊判定：不同昵称 >= 2 个
        is_group = len(nicknames) >= 2

        if not is_group:
            logger.info(f"  判定为单聊，跳过昵称过滤")
            return [(t, y) for t, y, _, _, _ in items]

        logger.info(f"  判定为群聊，识别昵称: {nicknames}")

        # 6. AI兜底（仅群聊 + 有含糊块）
        if ambiguous_blocks:
            logger.info(f"  存在{len(ambiguous_blocks)}个含糊块，触发AI兜底")
            ai_names = self._ai_fallback_detect_nicknames(items)
            for name in ai_names:
                if len(name.strip()) <= 15:
                    nicknames.add(name.strip())
            if ai_names:
                logger.info(f"  AI补充昵称: {ai_names}")

        # 7. 过滤
        n_filtered = 0
        result = []
        for text, y, left, w, h in items:
            if text.strip() in nicknames:
                n_filtered += 1
                continue
            result.append((text, y))

        logger.info(f"  过滤群名: {n_filtered}条, 保留{len(result)}条消息")
        return result
```

- [ ] **Step 2: Commit**

```bash
git add wechat_bot.py
git commit -m "feat: add spatial clustering nickname filter with auto group detection"
```

---

### Task 5: Wire up `filter_group_nicknames()` in `process_one_contact()`

**Files:** Modify `wechat_bot.py` — L630-631, L636, L643, L648, L726, L738

- [ ] **Step 1: Update all_other collection to include w,h**

Change lines 627-631 from:
```python
        # 7. 收集所有对方消息（OCR已遮罩绿色，全是对方消息，is_self恒False）
        all_other = []
        for page in pages_msgs:
            for t, y, _, l in page:
                all_other.append((t, y, l))
```
To:
```python
        # 7. 收集所有对方消息（OCR已遮罩绿色，全是对方消息，is_self恒False）
        all_other = []
        for page in pages_msgs:
            for t, y, _, l, w, h in page:
                all_other.append((t, y, l, w, h))
```

- [ ] **Step 2: Insert nickname filter call after collecting all_other**

Insert after line 631 (`all_other.append((t, y, l, w, h))`):
```python

        # 7.5 过滤群聊昵称
        filtered_other = self.filter_group_nicknames(all_other)
```

- [ ] **Step 3: Update should_skip loop to use filtered results**

Change lines 633-643 from:
```python
        # 先逐条 should_skip 过滤
        raw_unanswered = []
        n_skipped = 0
        for text, y, l in all_other:
            skip_reason = self._skip_reason(text)
            if skip_reason:
                n_skipped += 1
                print(f"  [{idx}] ⏭ 过滤 [{text[:30]}] 原因: {skip_reason}")
                logger.info(f"[{idx}] should_skip: {text[:40]}")
                continue
            raw_unanswered.append((text, y, l))
```
To:
```python
        # 先逐条 should_skip 过滤
        raw_unanswered = []
        n_skipped = 0
        for text, y in filtered_other:
            skip_reason = self._skip_reason(text)
            if skip_reason:
                n_skipped += 1
                print(f"  [{idx}] ⏭ 过滤 [{text[:30]}] 原因: {skip_reason}")
                logger.info(f"[{idx}] should_skip: {text[:40]}")
                continue
            raw_unanswered.append((text, y))
```

- [ ] **Step 4: Update _clean_time_text loop**

Change lines 645-653 from:
```python
        # 不合并，每条OCR结果独立作为候选消息
        # 剔除嵌入的时间/日期（"17:11你好" → "你好"），剔除后为空则跳过
        cleaned = []
        for t, y, l in raw_unanswered:
            ct = self._clean_time_text(t)
            if ct is None:
                print(f"  [{idx}] ⏭ 纯时间/日期: [{t[:30]}]")
                continue
            cleaned.append((ct, y))
```
To:
```python
        # 不合并，每条OCR结果独立作为候选消息
        # 剔除嵌入的时间/日期（"17:11你好" → "你好"），剔除后为空则跳过
        cleaned = []
        for t, y in raw_unanswered:
            ct = self._clean_time_text(t)
            if ct is None:
                print(f"  [{idx}] ⏭ 纯时间/日期: [{t[:30]}]")
                continue
            cleaned.append((ct, y))
```

(Only changed `for t, y, l` to `for t, y`)

- [ ] **Step 5: Update no-message log line**

Change line 657 from:
```python
            print(f"  [{idx}] ❌ 无可见对方消息（OCR{len(all_other)}条，过滤{n_skipped}条）")
```
To:
```python
            print(f"  [{idx}] ❌ 无可见对方消息（OCR{len(all_other)}条，过滤{n_skipped}条）")
```

(No change needed — `all_other` still exists for counting)

- [ ] **Step 6: Update seen_texts in tail scan**

Change line 726 from:
```python
            seen_texts = {t.strip() for t, _, _ in all_other}
```
To:
```python
            seen_texts = {t.strip() for t, _, _, _, _ in all_other}
```

- [ ] **Step 7: Update tail_msgs unpacking**

Change line 738 from:
```python
                for text, y, _, _ in tail_msgs:
```
To:
```python
                for text, y, _, l, w, h in tail_msgs:
```

- [ ] **Step 8: Commit**

```bash
git add wechat_bot.py
git commit -m "feat: wire up new nickname filter in process_one_contact"
```

---

### Task 6: Final verification

- [ ] **Step 1: Check syntax**

```bash
cd D:/shiliu_ai_github/wechat_bot_v3 && python -c "import py_compile; py_compile.compile('wechat_bot.py', doraise=True); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 2: Review all tuple unpacking consistency**

Run grep to verify no 3-element `all_other` unpackings remain:
```bash
cd D:/shiliu_ai_github/wechat_bot_v3 && grep -n "for.*,.*,.*in all_other" wechat_bot.py
```

Expected: only `for text, y in filtered_other:` appears (2-element unpack). No 3-element unpack of `all_other`.

- [ ] **Step 3: Commit any fixes**

```bash
git add wechat_bot.py && git commit -m "chore: fix tuple unpacking consistency"
```
(Only if fixes were needed)

---

### Self-Review Checklist

- [x] Spec coverage: Deleting old filter (spec line "删除旧昵称过滤") — Task 2 Step 2. Filtering function (spec "空间聚类") — Task 4. AI fallback (spec "AI兜底") — Task 3. DetectorResult hook (spec "预留接口") — Task 1. Wire-up (spec "调用新方法") — Task 5. All covered.
- [x] Placeholder scan: No TBD, TODO, or vague instructions. All code is complete.
- [x] Type consistency: `items` is `[(text, y, left, w, h), ...]` throughout. `filter_group_nicknames` returns `[(text, y), ...]`. `DetectorResult` uses `List[Any]` matching future flexibility.
