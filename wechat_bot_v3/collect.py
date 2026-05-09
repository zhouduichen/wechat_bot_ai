#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
收集YOLO训练样本
用法：
  python collect.py          → 收集联系人列表截图（红点）
  python collect.py chat     → 收集聊天区域截图（绿色气泡）
"""

import os, sys, time, logging
from PIL import ImageGrab
import uiautomation as auto

BASE = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(BASE, "dataset", "images")
TOTAL = 100
INTERVAL = 2

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

MODE = sys.argv[1] if len(sys.argv) > 1 else "contact"


def get_wechat_rect():
    wechat = auto.WindowControl(searchDepth=1, Name="微信")
    if not wechat.Exists(0, 0):
        raise Exception("未找到微信窗口")
    r = wechat.BoundingRectangle
    return {"l": r.left, "t": r.top, "r": r.right, "b": r.bottom,
            "w": r.right - r.left, "h": r.bottom - r.top}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    wr = get_wechat_rect()

    if MODE == "chat":
        # 聊天区域：右侧70%
        region = (
            wr["l"] + int(wr["w"] * 0.30),
            wr["t"] + int(wr["h"] * 0.10),
            wr["r"] - 20,
            wr["b"] - int(wr["h"] * 0.20)
        )
        prefix = "chat_"
        tip = "请打开一个有你已发送消息（绿色气泡）的聊天窗口"
    else:
        # 联系人列表：左侧25%
        region = (
            wr["l"] + 10,
            wr["t"] + 50,
            wr["l"] + int(wr["w"] * 0.25) - 10,
            wr["b"] - 50
        )
        prefix = "contact_"
        tip = "请确保联系人列表有几条未读消息（红点）"

    logger.info(f"模式: {MODE} | 区域: {region}")
    logger.info(tip)
    logger.info(f"目标: {TOTAL} 张 | 间隔: {INTERVAL}s")
    logger.info("3秒后开始...\n")
    time.sleep(3)

    existing = len([f for f in os.listdir(OUTPUT_DIR) if f.startswith(prefix)])
    for i in range(TOTAL):
        try:
            shot = ImageGrab.grab(bbox=region)
            name = f"{prefix}{existing + i + 1:04d}.png"
            shot.save(os.path.join(OUTPUT_DIR, name))
            logger.info(f"[{i+1}/{TOTAL}] {name}")
        except Exception as e:
            logger.error(f"截图失败: {e}")
        if i < TOTAL - 1:
            time.sleep(INTERVAL)

    logger.info(f"\n完成！{TOTAL} 张保存在 {OUTPUT_DIR}")
    logger.info("下一步：python label.py")


if __name__ == "__main__":
    main()
