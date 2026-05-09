#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信自动回复机器人 V6 — 红点检测 + 气泡判断 + 逐条回复
"""

import os, sys, time, json, base64, logging, re
from datetime import datetime
from io import BytesIO

import cv2, numpy as np
import requests, pyperclip, pyautogui
from PIL import ImageGrab
from ultralytics import YOLO
import uiautomation as auto

# ========== 配置 ==========
BASE_DIR = os.path.dirname(__file__)
MODEL_PATH = os.path.join(BASE_DIR, "model", "wechat_dot.pt")
REPLY_COOLDOWN = 60  # 回复过的联系人冷却秒数
POLICY_PATH = os.path.join(BASE_DIR, "reply_policy.json")
SNAPSHOT_DIR = os.path.join(BASE_DIR, "snapshots")

BAIDU_API_KEY = os.getenv("BAIDU_API_KEY", "YOUR_BAIDU_OCR_KEY")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "YOUR_BAIDU_OCR_SECRET")
BACKEND_URL = "http://127.0.0.1/shiliu_ai/api_receive_message.php"
LOOP_INTERVAL = 3
CHAT_LOAD_WAIT = 3.0        # 点击联系人后等待加载
SEND_COOLDOWN = 2.0          # 发完消息后冷却
BETWEEN_CONTACTS_WAIT = 2.0  # 处理完一个联系人后等待

NO_REPLY_KEYWORDS = ["谢谢", "好的", "嗯", "哦", "ok", "收到", "[图片]", "[语音]", "[视频]", "[文件]"]

os.makedirs(SNAPSHOT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(os.path.join(BASE_DIR, "wechat_bot.log"), encoding="utf-8"),
              logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ========== 百度OCR（含位置）==========

class BaiduOCR:
    def __init__(self, api_key, secret_key):
        self.api_key = api_key; self.secret_key = secret_key
        self.access_token = self._get_token()

    def _get_token(self):
        url = "https://aip.baidubce.com/oauth/2.0/token"
        r = requests.post(url, params={"grant_type": "client_credentials",
                                        "client_id": self.api_key, "client_secret": self.secret_key})
        return r.json().get("access_token")

    def recognize(self, image_data):
        """返回 [(text, left, top, width, height), ...]"""
        if not self.access_token:
            return []
        url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={self.access_token}"
        payload = {"image": base64.b64encode(image_data).decode(),
                   "language_type": "CHN_ENG", "detect_direction": "true", "probability": "true"}
        try:
            r = requests.post(url, data=payload, timeout=10)
            if r.status_code == 200:
                res = r.json()
                if "words_result" in res:
                    items = []
                    for w in res["words_result"]:
                        if w.get("probability", {}).get("average", 0.9) < 0.6:
                            continue
                        loc = w.get("location", {})
                        items.append((w["words"], loc.get("left", 0), loc.get("top", 0),
                                       loc.get("width", 0), loc.get("height", 0)))
                    return items
        except Exception as e:
            logger.error(f"OCR失败: {e}")
        return []


# ========== 回复策略 ==========

def load_policy():
    d = {"default": "ask", "always_reply": [], "never_reply": ["文件传输助手", "微信团队", "公众号", "服务号", "微信支付", "订阅号"],
         "contact_overrides": {}}
    if os.path.exists(POLICY_PATH):
        with open(POLICY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    with open(POLICY_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return d


def should_reply_to(name, policy):
    name = name.strip()
    if not name:
        return policy.get("default", "skip") != "skip"
    # 模糊匹配：OCR可能读出不精确的名字
    for blocked in policy.get("never_reply", []):
        if blocked.strip() in name or name in blocked.strip():
            return False
    for allowed in policy.get("always_reply", []):
        if allowed.strip() in name or name in allowed.strip():
            return True
    return policy.get("default", "skip") != "skip"


# ========== 微信机器人V5 ==========

class WechatBotV6:
    def __init__(self):
        if not os.path.exists(MODEL_PATH):
            logger.error(f"红点模型不存在: {MODEL_PATH}，请先运行 train.py")
            sys.exit(1)
        self.dot_model = YOLO(MODEL_PATH)
        self.last_reply = {}
        self.last_mouse_pos = pyautogui.position()  # 鼠标活动检测
        self.ocr = BaiduOCR(BAIDU_API_KEY, BAIDU_SECRET_KEY)
        self.policy = load_policy()
        self.wechat = auto.WindowControl(searchDepth=1, Name="微信")
        if not self.wechat.Exists(0, 0):
            raise Exception("未找到微信窗口")
        logger.info("微信窗口已找到")
        self.running = False

    # ---- 窗口区域 ----

    def get_wr(self):
        r = self.wechat.BoundingRectangle
        return {"l": r.left, "t": r.top, "r": r.right, "b": r.bottom,
                "w": r.right - r.left, "h": r.bottom - r.top}

    def contact_region(self, wr):
        return (wr["l"] + 10, wr["t"] + 50,
                wr["l"] + int(wr["w"] * 0.25) - 10, wr["b"] - 50)

    def chat_region(self, wr):
        return (wr["l"] + int(wr["w"] * 0.30), wr["t"] + int(wr["h"] * 0.10),
                wr["r"] - 20, wr["b"] - int(wr["h"] * 0.20))

    def name_region(self, wr):
        cl, ct, cr, cb = self.chat_region(wr)
        return (cl, ct, cr, ct + 40)

    # ---- YOLO检测 ----

    def _yolo_detect(self, region, model, min_conf=0.3):
        """通用YOLO检测，返回中心点+完整框，低于置信度的过滤"""
        shot = ImageGrab.grab(bbox=region)
        img = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
        results = model(img, verbose=False, conf=min_conf)
        dots = []
        if results[0].boxes is not None:
            for box in results[0].boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                if conf < min_conf:
                    continue
                dots.append({
                    "x": int((x1 + x2) / 2) + region[0],
                    "y": int((y1 + y2) / 2) + region[1],
                    "x1": int(x1) + region[0], "y1": int(y1) + region[1],
                    "x2": int(x2) + region[0], "y2": int(y2) + region[1],
                    "conf": conf
                })
        return dots

    def detect_bubbles(self, wr):
        """检测绿色气泡，返回其Y范围列表 [(y1, y2), ...]（屏幕坐标）"""
        cr = self.chat_region(wr)
        if not self.bubble_model:
            return []
        bubbles = self._yolo_detect(cr, self.bubble_model)
        return [(b["y1"], b["y2"]) for b in bubbles]

    def detect_red_dots_in_view(self, wr):
        """检测当前可见区域的红点（不滚动）"""
        region = self.contact_region(wr)
        dots = self._yolo_detect(region, self.dot_model)
        # 合并Y相近的红点
        return self._merge_dots(dots) if dots else []

    def _merge_dots(self, dots, y_thr=30):
        if not dots: return []
        dots = sorted(dots, key=lambda d: d["y"])
        merged, used = [], set()
        for i, d in enumerate(dots):
            if i in used: continue
            group = [d]
            for j, o in enumerate(dots):
                if j != i and j not in used and abs(d["y"] - o["y"]) < y_thr:
                    group.append(o); used.add(j)
            merged.append({"x": int(sum(g["x"] for g in group) / len(group)),
                           "y": int(sum(g["y"] for g in group) / len(group))})
            used.add(i)
        return merged

    # ---- 截图去重 ----

    def snap_chat_bottom(self, wr):
        cr = self.chat_region(wr)
        return ImageGrab.grab(bbox=(cr[0], wr["b"] - 220, cr[2], wr["b"] - 20))

    def snap_hash(self, img):
        return np.array(img.resize((32, 32)).convert("L"), dtype=np.float32)

    def has_new_content(self, wr, ck):
        cur = self.snap_chat_bottom(wr)
        cur_arr = self.snap_hash(cur)
        sp = os.path.join(SNAPSHOT_DIR, f"{ck}.npy")
        if not os.path.exists(sp):
            return True
        saved = np.load(sp)
        mse = np.mean((cur_arr - saved) ** 2)
        logger.info(f"  截图MSE: {mse:.1f}")
        return mse > 80

    def save_snap(self, wr, ck):
        cur = self.snap_chat_bottom(wr)
        np.save(os.path.join(SNAPSHOT_DIR, f"{ck}.npy"), self.snap_hash(cur))

    # ---- 鼠标活动检测 ----

    def mouse_moved(self):
        """检测鼠标是否被人为移动，是则返回True（中断当前操作）"""
        cur = pyautogui.position()
        moved = cur != self.last_mouse_pos
        self.last_mouse_pos = cur
        return moved

    # ---- 聊天操作 ----

    def click_contact(self, dot, wr):
        """点击红点左侧的联系人名字区域，避免点错对话框"""
        region = self.contact_region(wr)
        # 在红点左侧60px点击（联系人名字/头像区域），不点列表正中
        click_x = dot["x"] - 60
        click_y = dot["y"] + 8  # 稍微下移，确保命中
        pyautogui.click(click_x, click_y)
        time.sleep(CHAT_LOAD_WAIT)
        logger.info(f"  点击联系人 ({click_x}, {click_y})")

    def pageup(self, n=2):
        for _ in range(n):
            pyautogui.press("pageup"); time.sleep(0.2)
        time.sleep(0.3)

    def send_text(self, text):
        self.wechat.SetActive(); time.sleep(0.2)
        wr = self.get_wr()
        pyautogui.click(wr["l"] + wr["w"] // 2, wr["b"] - 100)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a"); time.sleep(0.05)
        pyautogui.press("delete"); time.sleep(0.05)
        pyperclip.copy(text); time.sleep(0.15)
        pyautogui.hotkey("ctrl", "v"); time.sleep(0.3)
        pyautogui.press("enter"); time.sleep(SEND_COOLDOWN)
        logger.info(f"已发送: {text[:50]}...")

    # ---- 读取消息 ----

    def get_contact_name(self, wr):
        region = self.name_region(wr)
        buf = BytesIO(); ImageGrab.grab(bbox=region).save(buf, format="PNG")
        items = self.ocr.recognize(buf.getvalue())
        texts = [t for t, *_ in items]
        return max(texts, key=len) if texts else ""

    def get_other_messages(self, wr, bubble_y_ranges=None):
        """返回对方消息列表 [(text, y), ...]（左半侧 + 不在气泡范围内）"""
        region = self.chat_region(wr)
        buf = BytesIO(); ImageGrab.grab(bbox=region).save(buf, format="PNG")
        items = self.ocr.recognize(buf.getvalue())

        bubble_y_ranges = bubble_y_ranges or []
        aw = region[2] - region[0]
        msgs = []
        for text, left, top, w, h in items:
            text_y = region[1] + top  # 转为屏幕坐标

            # 条件1：左半侧（对方发的）
            if left + w >= aw * 0.55:
                continue

            # 条件2：不在任何绿色气泡的Y范围内
            in_bubble = any(by1 - 10 <= text_y <= by2 + 10 for by1, by2 in bubble_y_ranges)
            if in_bubble:
                logger.debug(f"  过滤气泡内消息: {text}")
                continue

            msgs.append((text, text_y))

        msgs.sort(key=lambda x: x[1])
        return msgs

    # ---- 后端AI ----

    def get_ai_reply(self, msg):
        try:
            r = requests.post(BACKEND_URL, json={"content": msg, "wx_user_id": "v5_bot",
                                                  "wx_nickname": "用户"}, timeout=65)
            if r.status_code == 200:
                d = r.json()
                if d.get("success") and d.get("should_reply"):
                    return (d.get("reply_text") or "").strip()
        except Exception as e:
            logger.error(f"后端失败: {e}")
        return None

    def should_skip(self, text):
        if not text or len(text) < 2: return True
        tl = text.lower()
        if any(kw.lower() in tl for kw in NO_REPLY_KEYWORDS): return True
        if text.isdigit(): return True
        # 过滤纯时间字符串（如 11:11、11：11、上午11:11），但保留包含时间的对话
        if re.match(r'^(上午|下午|凌晨|早上|中午|晚上)?[\s]*\d{1,2}[:：]\d{2}[\s]*(AM|PM)?$', text, re.IGNORECASE):
            return True
        return False

    # ---- 预检：从列表直接读名字 ----

    def read_name_in_list(self, wr, dot):
        """点击前从联系人列表OCR名字（红点左侧区域），避免浪费点击"""
        region = self.contact_region(wr)
        # 红点左右取名字区域
        name_left = region[0] + 20
        name_right = dot["x"] - 30
        name_top = dot["y"] - 12
        name_bottom = dot["y"] + 12
        try:
            shot = ImageGrab.grab(bbox=(name_left, name_top, name_right, name_bottom))
            buf = BytesIO(); shot.save(buf, format="PNG")
            items = self.ocr.recognize(buf.getvalue())
            texts = [t for t, *_ in items]
            if texts:
                return "".join(texts)
        except Exception:
            pass
        return ""

    # ---- 核心流程：处理单个联系人 ----

    def process_one_contact(self, dot, wr, idx):
        """先查黑名单 → 冷却检查 → 进入 → 逐条回复"""
        ck = f"{dot['x']}_{dot['y']}"

        # 1. 列表里先读名字，黑名单直接跳过
        name = self.read_name_in_list(wr, dot)
        logger.info(f"[{idx}] 列表名: '{name}'")
        if not should_reply_to(name, self.policy):
            logger.info(f"[{idx}] 黑名单跳过（未点击）")
            return

        # 2. 冷却检查：最近回复过的1分钟内不重复打开
        if ck in self.last_reply:
            elapsed = time.time() - self.last_reply[ck]
            if elapsed < REPLY_COOLDOWN:
                logger.info(f"[{idx}] 冷却中（{elapsed:.0f}s前回复过），跳过")
                return

        # 3. 鼠标动了就放弃本轮
        if self.mouse_moved():
            logger.info(f"[{idx}] 鼠标活动，跳过")
            return

        # 4. 点击进入
        self.click_contact(dot, wr)

        # 4. 截图对比：有新内容才继续
        if not self.has_new_content(wr, ck):
            logger.info(f"[{idx}] 无新消息")
            return

        # 5. 翻1页
        self.pageup(1)

        # 6. 获取对方消息（OCR位置：左半侧=对方），只取最近5条
        all_msgs = self.get_other_messages(wr)
        other_msgs = all_msgs[-5:] if len(all_msgs) > 5 else all_msgs
        if not other_msgs:
            logger.info(f"[{idx}] 无对方消息")
            return
        logger.info(f"[{idx}] 共 {len(all_msgs)} 条，处理最近 {len(other_msgs)} 条")

        # 7. 只回复最后1条（最新消息），避免翻旧账
        msg_text, msg_y = other_msgs[-1]
        if self.should_skip(msg_text):
            logger.info(f"[{idx}] 跳过: {msg_text[:40]}")
            return

        logger.info(f"[{idx}] 回复: {msg_text[:40]}...")
        reply = self.get_ai_reply(msg_text)
        if reply:
            if self.mouse_moved():
                logger.info(f"[{idx}] 鼠标活动，取消发送")
                return
            self.send_text(reply)
            self.last_reply[ck] = time.time()

        # 8. 保存截图
        self.save_snap(wr, ck)

    # ---- 主循环 ----

    def run(self):
        print("=" * 60)
        print("微信自动回复 V5 — 即时回复 + 逐条回复 + OCR位置过滤")
        print("=" * 60)
        print("监听中... Ctrl+C 停止\n")

        self.running = True
        round_n = 0

        while self.running:
            try:
                round_n += 1
                print(f"\n[第{round_n}轮] {datetime.now().strftime('%H:%M:%S')}")

                wr = self.get_wr()

                # 检测可见区域红点（从上到下已排序）
                dots = self.detect_red_dots_in_view(wr)
                if not dots:
                    # 滚到底部再看一次（置顶太多可能下面有红点）
                    region = self.contact_region(wr)
                    mx = region[0] + (region[2] - region[0]) // 2
                    my = region[1] + (region[3] - region[1]) // 2
                    pyautogui.click(mx, my); time.sleep(0.2)
                    pyautogui.scroll(-5000); time.sleep(0.5)
                    dots = self.detect_red_dots_in_view(wr)
                    pyautogui.scroll(5000); time.sleep(0.2)  # 滚回去

                if not dots:
                    print("未检测到未读消息")
                    time.sleep(LOOP_INTERVAL)
                    continue

                print(f"检测到 {len(dots)} 个未读联系人")

                # 逐个即时处理（_merge_dots已按Y从上到下排序）
                for i, dot in enumerate(dots, 1):
                    if self.mouse_moved():
                        print("鼠标活动，本轮剩余跳过")
                        break
                    print(f"\n--- [{i}/{len(dots)}] ---")
                    self.process_one_contact(dot, wr, i)
                    time.sleep(BETWEEN_CONTACTS_WAIT)

                print(f"\n本轮完成，等待 {LOOP_INTERVAL}s...")
                time.sleep(LOOP_INTERVAL)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"循环出错: {e}")
                import traceback; traceback.print_exc()
                time.sleep(3)

        self.running = False
        print("\n已停止")


if __name__ == "__main__":
    try:
        WechatBotV6().run()
    except KeyboardInterrupt:
        print("\n已停止")
    except Exception as e:
        print(f"错误: {e}")
        import traceback; traceback.print_exc()
