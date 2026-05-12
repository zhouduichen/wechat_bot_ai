#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信自动回复机器人 V7 — OCR三区方向判断 + 逐页红点扫描 + 多条逐条回复
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

# 优先使用 wechat_red_dot 训练结果，否则用 wechat_dot.pt
_red_dot_best = os.path.join(BASE_DIR, "model", "wechat_red_dot", "weights", "best.pt")
_red_dot_default = os.path.join(BASE_DIR, "model", "wechat_dot.pt")
MODEL_PATH = _red_dot_best if os.path.exists(_red_dot_best) else _red_dot_default
REPLY_COOLDOWN = 60  # 回复过的联系人冷却秒数
POLICY_PATH = os.path.join(BASE_DIR, "reply_policy.json")

BAIDU_API_KEY = os.getenv("BAIDU_API_KEY", "ElIQN30iAqpEGi9zv0VlrtQX")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "7wrO2wDTx7FehuelgG0NCBDFOklnqSz0")
BACKEND_URL = "http://127.0.0.1/shiliu_ai/api_receive_message.php"

# DeepSeek 直连兜底（PHP后端不可用时）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-857181bbff16442cb7c9d37fc1e592e2")
DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
LOOP_INTERVAL = 3
CHAT_LOAD_WAIT = 3.0        # 点击联系人后等待加载
SEND_COOLDOWN = 3.0          # 发完消息后冷却
BETWEEN_CONTACTS_WAIT = 2.0  # 处理完一个联系人后等待

SKIP_KEYWORDS_PATH = os.path.join(BASE_DIR, "skip_keywords.json")

from dataclasses import dataclass
from typing import List, Any

@dataclass
class DetectorResult:
    """统一检测结果接口，预留红点/气泡 AI 兜底用"""
    items: List[Any]
    confidence: float
    source: str  # "primary" | "ai_fallback"

def load_skip_keywords():
    """加载不回复关键词配置"""
    default = {"keywords": [
        {"keyword": "拍了拍", "match_type": "contain", "is_active": True},
        {"keyword": "[图片]", "match_type": "contain", "is_active": True},
        {"keyword": "[语音]", "match_type": "contain", "is_active": True},
        {"keyword": "[视频]", "match_type": "contain", "is_active": True},
        {"keyword": "[文件]", "match_type": "contain", "is_active": True},
        {"keyword": "[表情]", "match_type": "contain", "is_active": True},
        {"keyword": "[链接]", "match_type": "contain", "is_active": True},
        {"keyword": "[小程序]", "match_type": "contain", "is_active": True},
        {"keyword": "[红包]", "match_type": "contain", "is_active": True},
        {"keyword": "[转账]", "match_type": "contain", "is_active": True},
    ]}
    if os.path.exists(SKIP_KEYWORDS_PATH):
        try:
            with open(SKIP_KEYWORDS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


# 微信系统文字（OCR可能识别到的时间戳/日期/系统提示）
WECHAT_SYSTEM_PATTERNS = [
    r'^\d{1,2}[:：]\d{2}$',
    r'^(上午|下午|晚上|凌晨)\s*\d{1,2}[:：]\d{2}$',
    r'^(昨天|前天|今天)\s*\d{1,2}[:：]\d{2}$',
    r'^\d{1,2}月\d{1,2}日(\s*\d{1,2}[:：]\d{2})?$',
    r'^(周一|周二|周三|周四|周五|周六|周日|星期一|星期二|星期三|星期四|星期五|星期六|星期日)$',
    r'^(你已添加了|以上是打招呼)',
    r'^共\d+条(新消息)?$',              # 共2条 / 共5条新消息
    r'^\d+分钟前$',                      # 14分钟前
    r'^\d{1,2}:\d{2}([-~]\d{1,2}:\d{2})?$',  # 15:30 或 15:30-16:00
    r'^[a-zA-Z0-9_-]+[：:]\d+[@\w]+$',  # 晨曦：3221350@ / wxid_xxx
]

DEBUG_SHOT_DIR = os.path.join(BASE_DIR, "debug_screenshots")
os.makedirs(DEBUG_SHOT_DIR, exist_ok=True)

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
        self.access_token = None
        self._token_expiry = 0
        if "YOUR_BAIDU" in api_key:
            logger.warning("⚠ 百度OCR API Key 未配置！请设置环境变量 BAIDU_API_KEY / BAIDU_SECRET_KEY")

    def _ensure_token(self):
        """获取或刷新 token（有效期30天，提前1天刷新）"""
        if self.access_token and time.time() < self._token_expiry:
            return True
        try:
            url = "https://aip.baidubce.com/oauth/2.0/token"
            r = requests.post(url, params={"grant_type": "client_credentials",
                                            "client_id": self.api_key, "client_secret": self.secret_key})
            resp = r.json()
            token = resp.get("access_token")
            if token:
                self.access_token = token
                self._token_expiry = time.time() + 29 * 86400
                logger.info("OCR token 已获取")
                return True
            else:
                logger.error(f"OCR token获取失败: {resp.get('error_description', resp)}")
        except Exception as e:
            logger.error(f"OCR token请求异常: {e}")
        return False

    def recognize(self, image_data):
        """返回 [(text, left, top, width, height), ...]"""
        if not self._ensure_token():
            msg = "!!! OCR token无效，无法识别文字！请检查 BAIDU_API_KEY / BAIDU_SECRET_KEY"
            logger.error(msg)
            print(msg)
            return []
        url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={self.access_token}"
        payload = {"image": base64.b64encode(image_data).decode(),
                   "language_type": "CHN_ENG", "detect_direction": "true", "probability": "true"}
        try:
            r = requests.post(url, data=payload, timeout=10)
            # token 过期 → 刷新后重试一次
            if r.status_code == 401 or (r.status_code == 200 and "error_code" in r.text and "expired" in r.text.lower()):
                logger.info("OCR token 过期，刷新重试...")
                self.access_token = None
                self._token_expiry = 0
                if self._ensure_token():
                    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={self.access_token}"
                    r = requests.post(url, data=payload, timeout=10)
            if r.status_code == 200:
                res = r.json()
                if "error_code" in res:
                    logger.error(f"OCR API错误: code={res.get('error_code')} msg={res.get('error_msg')}")
                    return []
                if "words_result" in res:
                    items = []
                    n_dropped = 0
                    for w in res["words_result"]:
                        prob = w.get("probability", {}).get("average", 0.9)
                        if prob < 0.3:
                            n_dropped += 1
                            continue
                        loc = w.get("location", {})
                        items.append((w["words"], loc.get("left", 0), loc.get("top", 0),
                                       loc.get("width", 0), loc.get("height", 0)))
                    if n_dropped > 0:
                        logger.info(f"  OCR概率过滤: {n_dropped}条(低置信度) 保留{len(items)}条")
                    return items
                else:
                    msg = f"OCR返回无words_result: {json.dumps(res, ensure_ascii=False)[:200]}"
                    logger.warning(msg)
                    print(msg)
            else:
                logger.error(f"OCR HTTP错误: {r.status_code} {r.text[:200]}")
        except Exception as e:
            logger.error(f"OCR请求失败: {e}")
        return []


# ========== 回复策略 ==========

def load_policy():
    d = {"default": "ask", "always_reply": [], "never_reply": ["文件传输助手", "微信团队", "公众号", "服务号", "微信支付", "订阅号", "视频号"],
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
        b = blocked.strip()
        if not b:
            continue
        if b in name or name in b:
            return False
    for allowed in policy.get("always_reply", []):
        a = allowed.strip()
        if a and (a in name or name in a):
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
        self._last_user_click = 0
        self._recent_replies = {}  # 防重复回复: {text: timestamp}（跨轮）
        self._round_replied = set()  # 本轮已回复: {(ck, text), ...}
        self._sent_messages = set()  # 本次启动已发送: {text, ...}
        self.ocr = BaiduOCR(BAIDU_API_KEY, BAIDU_SECRET_KEY)
        self.policy = load_policy()
        self.skip_keywords = load_skip_keywords().get("keywords", [])
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

    def detect_red_dots_in_view(self, wr):
        """检测当前可见区域的红点（不滚动），min_conf=0.35 减少误检"""
        region = self.contact_region(wr)
        dots = self._yolo_detect(region, self.dot_model, min_conf=0.35)
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

    # ---- 人为操作检测 ----

    def mouse_clicked(self):
        """检测是否有点击行为：当前按下 或 1秒内点击过，则返回True"""
        import ctypes
        VK_LBUTTON = 0x01
        if ctypes.windll.user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000 != 0:
            self._last_user_click = time.time()
            return True
        return time.time() - self._last_user_click < 1.0

    # ---- 聊天操作 ----

    def _verify_red_dot(self, dot):
        """点击前确认红点仍存在：截取20x20区域检测红色像素"""
        r = 10
        try:
            shot = ImageGrab.grab(bbox=(dot["x"] - r, dot["y"] - r,
                                        dot["x"] + r, dot["y"] + r))
            hsv = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2HSV)
            lower1, upper1 = np.array([0, 100, 100]), np.array([10, 255, 255])
            lower2, upper2 = np.array([160, 100, 100]), np.array([180, 255, 255])
            mask1 = cv2.inRange(hsv, lower1, upper1)
            mask2 = cv2.inRange(hsv, lower2, upper2)
            red_pixels = cv2.countNonZero(mask1) + cv2.countNonZero(mask2)
            return red_pixels > 15  # 至少有15个红色像素
        except Exception:
            return True  # 截取失败不阻塞，放行

    def click_contact(self, dot, wr):
        """直接点击红点中心"""
        pyautogui.click(dot["x"], dot["y"])
        time.sleep(CHAT_LOAD_WAIT)
        logger.info(f"  点击红点 ({dot['x']}, {dot['y']})")

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
        pyautogui.hotkey("ctrl", "v"); time.sleep(0.5)
        pyautogui.press("enter"); time.sleep(SEND_COOLDOWN)
        self._sent_messages.add(text.strip())
        logger.info(f"已发送: {text[:50]}...")

    # ---- 读取消息 ----

    def get_contact_name(self, wr):
        region = self.name_region(wr)
        buf = BytesIO(); ImageGrab.grab(bbox=region).save(buf, format="PNG")
        items = self.ocr.recognize(buf.getvalue())
        texts = [t for t, *_ in items]
        return max(texts, key=len) if texts else ""

    def _detect_green_bubbles(self, pil_image, region):
        """检测绿色气泡位置【has_reply用——精准】只认明确的绿色大气泡"""
        import numpy as np
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2HSV)
        lower = np.array([48, 40, 40])
        upper = np.array([72, 255, 255])
        mask = cv2.inRange(img, lower, upper)
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        bubbles = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w > 50 and h > 25:
                bubbles.append((region[1] + y, region[1] + y + h))
        return sorted(bubbles)

    def _mask_green_bubbles(self, pil_image):
        """遮罩绿色气泡【OCR用——凶猛】宁可多涂，确保自己不出现"""
        import numpy as np
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2HSV)
        lower = np.array([38, 25, 20])
        upper = np.array([85, 255, 255])
        mask = cv2.inRange(img, lower, upper)
        kernel = np.ones((15, 15), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=4)
        from PIL import Image
        result = np.array(pil_image.convert("RGB"))
        result[mask > 0] = [255, 255, 255]
        return Image.fromarray(result)

    def get_all_messages(self, wr):
        """OCR聊天区：遮罩绿色气泡后识别对方消息，同时检测绿色气泡位置（自己消息）
        返回 (msgs, self_bubbles)
        msgs: [(text, screen_y, is_self=False, left, w, h), ...]
        self_bubbles: [(y1, y2), ...] 自己气泡的屏幕Y范围"""
        region = self.chat_region(wr)
        shot = ImageGrab.grab(bbox=region)

        # 保存调试用时间戳
        ts = datetime.now().strftime("%H%M%S")

        # 检测绿色气泡位置（自己消息，纯本地，不花钱）
        self_bubbles = self._detect_green_bubbles(shot, region)

        # 保存绿色气泡标注图
        import numpy as np
        debug_green = np.array(shot.convert("RGB"))
        for by1, by2 in self_bubbles:
            y1 = by1 - region[1]
            y2 = by2 - region[1]
            cv2.rectangle(debug_green, (0, y1), (debug_green.shape[1] - 1, y2), (0, 255, 0), 2)
        from PIL import Image
        Image.fromarray(debug_green).save(os.path.join(DEBUG_SHOT_DIR, f"green_{ts}_{len(self_bubbles)}bubbles.png"))

        # 遮罩绿色后OCR对方消息
        masked = self._mask_green_bubbles(shot)
        # 限制尺寸（百度OCR限制base64<4MB，大图先缩放）
        w, h = masked.size
        if w * h > 2000000:  # >2M像素就缩放
            scale = (2000000 / (w * h)) ** 0.5
            masked = masked.resize((int(w * scale), int(h * scale)))
        buf = BytesIO()
        masked.convert("RGB").save(buf, format="JPEG", quality=75)
        items = self.ocr.recognize(buf.getvalue())

        msgs = []
        for text, left, top, w, h in items:
            text_y = region[1] + top
            msgs.append((text, text_y, False, left, w, h))
        msgs.sort(key=lambda x: x[1])

        # 保存调试截图
        shot.save(os.path.join(DEBUG_SHOT_DIR, f"raw_{ts}.png"))
        masked.save(os.path.join(DEBUG_SHOT_DIR, f"masked_{ts}_{len(items)}items.png"))

        print(f"  OCR: {len(items)}条对方消息  绿色气泡: {len(self_bubbles)}个")
        logger.info(f"  OCR: {len(items)}条对方消息  绿色气泡: {len(self_bubbles)}个")
        if msgs:
            logger.info(f"  样本: {' | '.join(t[:12] for t, _, _, _, _, _ in msgs[:6])}")
        return msgs, self_bubbles

    @staticmethod
    def _merge_message_lines(msgs):
        """合并同一消息的多行文字: [(text, y, left), ...] → [(merged_text, y), ...]"""
        if not msgs:
            return []
        msgs = sorted(msgs, key=lambda x: x[1])
        merged, group = [], [msgs[0]]

        for i in range(1, len(msgs)):
            if msgs[i][1] - group[-1][1] < 9 and abs(msgs[i][2] - group[-1][2]) < 5:
                group.append(msgs[i])
            else:
                merged.append((''.join(t for t, _, _ in group), group[0][1]))
                group = [msgs[i]]

        merged.append((''.join(t for t, _, _ in group), group[0][1]))
        return merged

    # ---- 后端AI ----

    def get_ai_reply(self, msg):
        # 1. 先查本地规则（auto_reply_rules.json，和网页管理面板同步）
        rules_path = os.path.join(BASE_DIR, "auto_reply_rules.json")
        if os.path.exists(rules_path):
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    rules = json.load(f).get("rules", [])
                for rule in rules:
                    if not rule.get("is_active", 1):
                        continue
                    kw = rule["keyword"]
                    if rule.get("match_type") == "equal":
                        if msg.strip() == kw:
                            logger.info(f"本地规则命中(完全匹配): {kw}")
                            return rule["reply_text"]
                    else:
                        if kw in msg:
                            logger.info(f"本地规则命中(包含匹配): {kw}")
                            return rule["reply_text"]
            except Exception:
                pass

        # 2. 再试 PHP 后端
        try:
            r = requests.post(BACKEND_URL, json={"content": msg, "wx_user_id": "v5_bot",
                                                  "wx_nickname": "用户"}, timeout=5)
            if r.status_code == 200:
                d = r.json()
                if d.get("success") and d.get("should_reply"):
                    return (d.get("reply_text") or "").strip()
        except Exception:
            pass  # PHP 后端不可用，走直连兜底

        # 直连 DeepSeek 兜底
        try:
            url = f"{DEEPSEEK_API_BASE}/chat/completions"
            headers = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
            payload = {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "你是一个真人微信客服，回复控制在20字以内，直奔主题，不寒暄不客套，像朋友聊天一样自然。"},
                    {"role": "user", "content": msg}
                ],
                "temperature": 0.4,
                "max_tokens": 60
            }
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            if r.status_code == 200:
                d = r.json()
                content = d.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    logger.info(f"DeepSeek直连回复: {content[:40]}...")
                    return content.strip()
            else:
                logger.error(f"DeepSeek直连失败: {r.status_code} {r.text[:100]}")
        except Exception as e:
            logger.error(f"DeepSeek直连异常: {e}")
        return None

    # 消息中包含的时间/日期格式（模糊匹配，用于剔除而非整条过滤）
    _TIME_PATTERNS = [
        r'\d{1,2}[:：]\d{2}',                          # 17:11 / 17：11
        r'(上午|下午|晚上|凌晨)\s*\d{1,2}[:：]\d{2}',  # 上午 10:30
        r'(昨天|前天|今天)\s*\d{1,2}[:：]\d{2}',        # 昨天 17:11
        r'\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{2}',     # 5月11日 17:11
        r'\d{1,2}月\d{1,2}日',                          # 5月11日
        r'(周一|周二|周三|周四|周五|周六|周日|星期一|星期二|星期三|星期四|星期五|星期六|星期日)',
    ]

    def _clean_time_text(self, text):
        """剔除消息中嵌入的时间/日期片段，返回清洗后文本。清洗后为空返回None"""
        t = text.strip()
        for pat in self._TIME_PATTERNS:
            t = re.sub(pat, '', t)
        t = t.strip()
        return t if t else None

    def _skip_reason(self, text):
        """返回跳过原因，不跳过返回None"""
        if not text or len(text.strip()) < 2:
            return "空/太短"
        t = text.strip()
        # 整条消息就是纯数字
        if t.isdigit():
            return "纯数字"
        # 整条消息就是时间/日期/系统文字（精确匹配）
        for pat in WECHAT_SYSTEM_PATTERNS:
            if re.match(pat, t):
                return "系统文字"
        # skip_keywords.json 规则
        tl = t.lower()
        for kw in self.skip_keywords:
            if not kw.get("is_active", True):
                continue
            keyword = kw["keyword"].lower()
            if kw.get("match_type") == "equal":
                if tl == keyword:
                    return f"关键词'{kw['keyword']}'（完全匹配）"
            else:  # contain
                if keyword in tl:
                    return f"关键词'{kw['keyword']}'（包含匹配）"
        return None

    def should_skip(self, text):
        return self._skip_reason(text) is not None

    def _should_reply_to_text(self, text):
        """判断消息是否值得回复。True=回复, False=跳过, None=不确定(AI判定)"""
        t = text.strip()
        if not t:
            return False

        # ---- 必须回复 ----
        if re.search(r'[吗呢吧啊呀]|[?？]|谁|哪|怎么|什么|为啥|为什么|几时|多少|能不能|可不可以', t):
            return True
        if '@' in t:
            return True
        if len(t) > 8:
            return True
        if re.search(r'[我你]', t) and re.search(r'[了想过要会能可以去来给说看吃买用找问告诉帮让发到在]', t):
            return True

        # ---- 必须跳过 ----
        if len(t) < 2:
            return False
        if t in ('好的', 'OK', 'ok', '嗯', '知道了', '行', '收到', '好', '对', '是的',
                 '没错', '明白', '懂了', '谢谢', '不客气', '没事', '好吧', 'okk', '哦'):
            return False
        if re.match(r'^[哈嘿呵嘻啊嗯哦噢]{2,}$', t):
            return False
        if t in self._sent_messages:
            return False

        # ---- 不确定 → AI ----
        return None

    def _ai_should_reply(self, texts):
        """批量AI判断边界消息是否需要回复。返回 {'reply': [idx], 'skip': [idx]}"""
        if not texts:
            return {'reply': [], 'skip': []}
        prompt_parts = [f"[{i}]{t}" for i, t in enumerate(texts)]
        prompt = "\n".join(prompt_parts)
        try:
            url = f"{DEEPSEEK_API_BASE}/chat/completions"
            headers = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
            payload = {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content":
                     "判断以下微信消息是否需要回复。返回JSON: {\"reply\":[序号],\"skip\":[序号]}"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1, "max_tokens": 100,
            }
            r = requests.post(url, headers=headers, json=payload, timeout=3)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
                data = json.loads(content)
                reply_ids = data.get('reply', [])
                skip_ids = data.get('skip', [])
                logger.info(f"  AI判断: 回复{reply_ids} 跳过{skip_ids} (共{len(texts)}条)")
                return {'reply': reply_ids, 'skip': skip_ids}
            else:
                logger.warning(f"  AI判断HTTP错误: {r.status_code}")
        except requests.Timeout:
            logger.info(f"  AI判断超时，全跳过")
        except Exception as e:
            logger.info(f"  AI判断失败: {e}")
        # 失败时保守处理：全跳过
        return {'reply': [], 'skip': list(range(len(texts)))}

    # ---- 预检：从列表直接读名字 ----

    def read_name_in_list(self, wr, dot):
        """点击前从联系人列表OCR名字（红点左侧大片区域），避免浪费点击"""
        region = self.contact_region(wr)
        # 从列表左边界到红点左侧，覆盖完整名字区域
        name_left = region[0] + 10
        name_right = dot["x"] - 20   # 红点中心左20px
        name_top = dot["y"] - 18
        name_bottom = dot["y"] + 18
        try:
            shot = ImageGrab.grab(bbox=(name_left, name_top, name_right, name_bottom))
            buf = BytesIO(); shot.save(buf, format="PNG")
            items = self.ocr.recognize(buf.getvalue())
            texts = [t for t, *_ in items]
            name = "".join(texts) if texts else ""
            if name:
                logger.info(f"  列表OCR名字: '{name}'")
            else:
                logger.info(f"  列表OCR名字: (未读到)")
            return name
        except Exception:
            pass
        return ""

    # ---- 核心流程：处理单个联系人 ----

    def process_one_contact(self, dot, wr, idx):
        """黑名单预检 → 冷却 → 进入 → 综合扫描 → 逐条回复 → 尾扫新消息"""
        ck = f"{dot['x']}_{dot['y']}"
        self._round_replied.clear()  # 每轮清空本轮去重集

        # 1. 列表预读名字，黑名单跳过
        name = self.read_name_in_list(wr, dot)
        print(f"  [{idx}] 🔍 OCR读名: '{name}'")
        if not should_reply_to(name, self.policy):
            print(f"  [{idx}] 🚫 黑名单拦截: '{name}' → 不点击")
            logger.info(f"[{idx}] 黑名单跳过: '{name}'")
            return False

        # 2. 冷却检查
        if ck in self.last_reply:
            elapsed = time.time() - self.last_reply[ck]
            if elapsed < REPLY_COOLDOWN:
                logger.info(f"[{idx}] 冷却中（{elapsed:.0f}s前），跳过")
                return False

        # 3. 鼠标点击检测
        if self.mouse_clicked():
            logger.info(f"[{idx}] 鼠标点击，跳过")
            return False

        # 4. 点击前确认红点仍在
        if not self._verify_red_dot(dot):
            logger.info(f"[{idx}] 红点已消失，跳过")
            return False

        # 5. 点击进入
        self.click_contact(dot, wr)

        print(f"  [{idx}] 📨 进入聊天，开始OCR...")

        # 5. OCR-1: 当前可见聊天区（遮罩绿色后只读对方消息 + 检测绿色气泡位置）
        page1_msgs, page1_bubbles = self.get_all_messages(wr)
        retried = False
        if not page1_msgs:
            logger.info(f"[{idx}] 当前屏无文字，翻页重试...")
            self.pageup(1)
            page1_msgs, page1_bubbles = self.get_all_messages(wr)
            retried = True

        if not page1_msgs:
            logger.info(f"[{idx}] 聊天区无文字")
            return False

        # 6. PageUp翻第二屏（补翻过则跳过，避免翻到更久远消息）
        page2_msgs, page2_bubbles = [], []
        if not retried:
            self.pageup(1)
            page2_msgs, page2_bubbles = self.get_all_messages(wr)

        pages_msgs = [page1_msgs, page2_msgs]
        all_self_bubbles = page1_bubbles + page2_bubbles

        # 7. 收集所有对方消息（OCR已遮罩绿色，全是对方消息，is_self恒False）
        all_other = []
        for page in pages_msgs:
            for t, y, _, l, w, h in page:
                all_other.append((t, y, l, w, h))

        # 先逐条 should_skip 过滤
        raw_unanswered = []
        n_skipped = 0
        for text, y, l, w, h in all_other:
            skip_reason = self._skip_reason(text)
            if skip_reason:
                n_skipped += 1
                print(f"  [{idx}] ⏭ 过滤 [{text[:30]}] 原因: {skip_reason}")
                logger.info(f"[{idx}] should_skip: {text[:40]}")
                continue
            raw_unanswered.append((text, y))

        # 不合并，每条OCR结果独立作为候选消息
        # 剔除嵌入的时间/日期（"17:11你好" → "你好"），剔除后为空则跳过
        cleaned = []
        for t, y in raw_unanswered:
            ct = self._clean_time_text(t)
            if ct is None:
                print(f"  [{idx}] ⏭ 纯时间/日期: [{t[:30]}]")
                continue
            cleaned.append((ct, y))
        candidates = cleaned

        if not candidates:
            print(f"  [{idx}] ❌ 无可见对方消息（OCR{len(all_other)}条，过滤{n_skipped}条）")
            return False

        print(f"  [{idx}] 📋 候选 {len(candidates)} 条:")
        for t, y in candidates:
            print(f"      ── [{t[:50]}]")

        # 8. 逐条判断是否值得回复
        has_self_bubbles = len(all_self_bubbles) > 0
        all_unanswered = []
        ambiguous = []  # [(idx, text, y), ...] 边界消息
        n_has_reply = 0

        for text, y in candidates:
            # 绿泡存在 + 文本匹配已发消息 → 已回复
            if has_self_bubbles and text.strip() in self._sent_messages:
                n_has_reply += 1
                print(f"  [{idx}] ✅ 已回复 [{text[:30]}]")
                continue

            # 消息意图判断
            decision = self._should_reply_to_text(text)
            if decision is True:
                print(f"  [{idx}] 🔔 待回复 [{text[:30]}]")
                all_unanswered.append((text, y))
            elif decision is False:
                n_has_reply += 1
                print(f"  [{idx}] ⏭ 跳过 [{text[:30]}]（无意图）")
            else:
                ambiguous.append((len(all_unanswered), text, y))
                all_unanswered.append((text, y))  # 暂存，AI后再定

        # AI批量判断边界消息
        if ambiguous:
            ai_texts = [t for _, t, _ in ambiguous]
            ai_result = self._ai_should_reply(ai_texts)
            ai_skip_idx = set(ai_result.get('skip', []))
            # 从all_unanswered中移除AI判跳过的
            filtered = []
            ai_skip_n = 0
            for i, (text, y) in enumerate(all_unanswered):
                ambig_idx = next((ai_i for ai_i, (orig_i, _, _) in enumerate(ambiguous) if orig_i == i), None)
                if ambig_idx is not None and ambig_idx in ai_skip_idx:
                    ai_skip_n += 1
                    print(f"  [{idx}] ⏭ AI跳过 [{text[:30]}]")
                    continue
                filtered.append((text, y))
            if ai_skip_n > 0:
                logger.info(f"[{idx}] AI跳过{ai_skip_n}条边界消息")
            all_unanswered = filtered

        logger.info(f"[{idx}] 筛选: should_skip过滤{n_skipped}条 已回复/跳过{n_has_reply}条 → 待回复{len(all_unanswered)}条")

        unanswered = all_unanswered
        unanswered.sort(key=lambda x: x[1] if x[1] else 0)

        if not unanswered:
            print(f"  [{idx}] 无需回复")
            logger.info(f"[{idx}] 无需回复")
            return False

        print(f"  [{idx}] ✅ 待回复 {len(unanswered)} 条消息")
        # 9. 从旧到新逐条回复，最多5条
        if len(unanswered) > 5:
            logger.info(f"[{idx}] 待回复{len(unanswered)}条，截断至5条")
            unanswered = unanswered[:5]
        sent_any = False
        for msg_text, _ in unanswered:
            if self.mouse_clicked():
                logger.info(f"[{idx}] 鼠标点击，取消后续回复")
                break

            # 防重复：3分钟内相同内容不再回复
            now = time.time()
            key = msg_text.strip()
            last_t = self._recent_replies.get(key, 0)
            # 清理超过3分钟的旧记录
            self._recent_replies = {k: v for k, v in self._recent_replies.items() if now - v < 180}
            if now - last_t < 180:
                print(f"  [{idx}] ⏭ 重复消息（{now-last_t:.0f}s前回过）: {msg_text[:30]}")
                logger.info(f"[{idx}] 重复消息跳过: {msg_text[:30]}")
                continue
            # 本轮去重：同一联系人同一条消息不重复回
            round_key = (ck, key)
            if round_key in self._round_replied:
                print(f"  [{idx}] ⏭ 本轮重复: {msg_text[:30]}")
                logger.info(f"[{idx}] 本轮重复跳过: {msg_text[:30]}")
                continue

            logger.info(f"[{idx}] 回复: {msg_text[:40]}...")
            reply = self.get_ai_reply(msg_text)
            if reply:
                self.send_text(reply)
                sent_any = True
                self.last_reply[ck] = now
                self._recent_replies[key] = now
                self._round_replied.add(round_key)
                time.sleep(1.5)

        # 10. 回复后尾扫：捕获对方秒回的新消息（最多3轮）
        if sent_any and not self.mouse_clicked():
            seen_texts = {t.strip() for t, _, _, _, _ in all_other}
            seen_texts.update(t.strip() for t, _ in unanswered)
            for tail_round in range(3):
                if self.mouse_clicked():
                    break
                time.sleep(3.0)
                logger.info(f"[{idx}] 尾扫第{tail_round+1}轮...")
                tail_msgs, _ = self.get_all_messages(wr)
                if not tail_msgs:
                    logger.info(f"[{idx}] 尾扫无消息，结束")
                    break
                new_msgs = []
                for text, y, _, l, w, h in tail_msgs:
                    t = text.strip()
                    if t and t not in seen_texts:
                        new_msgs.append((t, y))
                        seen_texts.add(t)
                if not new_msgs:
                    logger.info(f"[{idx}] 尾扫无新消息，结束")
                    break
                candidates = []
                for text, y in new_msgs:
                    if self._skip_reason(text):
                        print(f"  [{idx}] 尾扫过滤 [{text[:30]}]")
                        continue
                    ct = self._clean_time_text(text)
                    if ct is None:
                        continue
                    candidates.append((ct, y))
                if not candidates:
                    logger.info(f"[{idx}] 尾扫候选为空，结束")
                    break
                print(f"  [{idx}] 🔔 尾扫发现 {len(candidates)} 条新消息")
                candidates.sort(key=lambda x: x[1])
                for msg_text, _ in candidates:
                    if self.mouse_clicked():
                        break
                    now = time.time()
                    key = msg_text.strip()
                    last_t = self._recent_replies.get(key, 0)
                    self._recent_replies = {k: v for k, v in self._recent_replies.items() if now - v < 180}
                    if now - last_t < 180:
                        print(f"  [{idx}] 尾扫重复跳过: {msg_text[:30]}")
                        continue
                    round_key = (ck, key)
                    if round_key in self._round_replied:
                        print(f"  [{idx}] 尾扫本轮重复: {msg_text[:30]}")
                        continue
                    logger.info(f"[{idx}] 尾扫回复: {msg_text[:40]}...")
                    reply = self.get_ai_reply(msg_text)
                    if reply:
                        self.send_text(reply)
                        self.last_reply[ck] = now
                        self._recent_replies[key] = now
                        self._round_replied.add(round_key)
                        time.sleep(1.5)

        # 确保焦点回到联系人列表，防止下次点击偏移
        wr2 = self.get_wr()
        cr = self.contact_region(wr2)
        pyautogui.click(cr[0] + (cr[2] - cr[0]) // 2, cr[1] + 50)
        time.sleep(0.5)

        return sent_any

    # ---- 主循环 ----

    def run(self):
        print("=" * 60)
        print("微信自动回复 V7 — OCR三区方向判断 + 逐页红点扫描 + 多条逐条回复")
        print("=" * 60)
        print("监听中... Ctrl+C 停止\n")

        self.running = True
        round_n = 0

        while self.running:
            try:
                round_n += 1
                print(f"\n[第{round_n}轮] {datetime.now().strftime('%H:%M:%S')}")

                wr = self.get_wr()
                region = self.contact_region(wr)
                mx = region[0] + (region[2] - region[0]) // 2
                my = region[1] + (region[3] - region[1]) // 2

                # 滚回列表顶部
                pyautogui.click(mx, my); time.sleep(0.15)
                pyautogui.scroll(5000); time.sleep(0.3)

                total = 0
                scroll_step = int((region[3] - region[1]) * 0.7)
                max_pages = 2

                for page in range(max_pages):
                    dots = self.detect_red_dots_in_view(wr)

                    if dots:
                        print(f"  [页{page+1}] 🔴 检测到 {len(dots)} 个红点")
                    elif page == 0:
                        print(f"  [页{page+1}] 无红点")

                    aborted = False
                    single_effective = True  # 单红点是否有效
                    if dots:
                        for i, dot in enumerate(dots, 1):
                            if self.mouse_clicked():
                                print("  鼠标点击，本轮跳过")
                                aborted = True
                                break
                            print(f"  --- [{total + i}] ---")
                            effective = self.process_one_contact(dot, wr, total + i)
                            if len(dots) == 1:
                                single_effective = effective
                            time.sleep(BETWEEN_CONTACTS_WAIT)

                    # 单红点无效：微滚补扫，防止顶部误检挡住下面未读消息
                    if not aborted and len(dots) == 1 and not single_effective:
                        logger.info("  单红点无效，微滚补扫...")
                        pyautogui.scroll(-scroll_step // 2); time.sleep(0.3)
                        dots2 = self.detect_red_dots_in_view(wr)
                        if dots2:
                            print(f"  [页{page+1}补扫] 🔴 检测到 {len(dots2)} 个红点")
                            for i, dot in enumerate(dots2, 1):
                                if self.mouse_clicked():
                                    break
                                print(f"  --- [{total + i}] ---")
                                self.process_one_contact(dot, wr, total + i)
                                time.sleep(BETWEEN_CONTACTS_WAIT)
                            total += len(dots2)

                    if aborted:
                        break

                    if dots:
                        total += len(dots)

                    # 第一页没红点，不翻页
                    if page == 0 and total == 0:
                        break

                    # 最后一页不翻
                    if page >= max_pages - 1:
                        break

                    pyautogui.scroll(-scroll_step); time.sleep(0.4)

                if total == 0:
                    print("  未检测到未读消息")
                else:
                    print(f"  本轮共处理 {total} 个联系人")

                print(f"等待 {LOOP_INTERVAL}s...")
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
