#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
收集绿色气泡训练样本 — 截取微信聊天区域
用法：python collect_bubble.py
前提：打开一个有你自己发送消息（绿色气泡）的聊天窗口
"""

import os, time, logging
from PIL import ImageGrab
import uiautomation as auto

BASE = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(BASE, "dataset_bubble", "images")
TOTAL = 80
INTERVAL = 2

os.makedirs(OUTPUT_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    wechat = auto.WindowControl(searchDepth=1, Name="微信")
    if not wechat.Exists(0, 0):
        raise Exception("未找到微信窗口")

    r = wechat.BoundingRectangle
    # 聊天区域
    region = (
        r.left + int((r.right - r.left) * 0.30),
        r.top + int((r.bottom - r.top) * 0.10),
        r.right - 20,
        r.bottom - int((r.bottom - r.top) * 0.20)
    )

    logger.info(f"聊天区域: {region}")
    logger.info("请打开一个有你发送过消息的聊天窗口（绿色气泡越多越好）")
    logger.info(f"目标: {TOTAL} 张 | 间隔: {INTERVAL}s")
    logger.info("建议切换不同聊天窗口增加多样性\n")
    logger.info("3秒后开始...")
    time.sleep(3)

    existing = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".png")])
    for i in range(TOTAL):
        try:
            shot = ImageGrab.grab(bbox=region)
            name = f"bubble_{existing + i + 1:04d}.png"
            shot.save(os.path.join(OUTPUT_DIR, name))
            logger.info(f"[{i+1}/{TOTAL}] {name}")
        except Exception as e:
            logger.error(f"截图失败: {e}")
        if i < TOTAL - 1:
            time.sleep(INTERVAL)

    logger.info(f"\n完成！{TOTAL} 张保存在 {OUTPUT_DIR}")
    logger.info("下一步：python label_bubble.py 标注绿色气泡")


if __name__ == "__main__":
    main()
