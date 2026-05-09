#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
训练YOLOv11m检测微信红点（针对小数据集优化）
用法：python train.py
"""

import os
import glob
import random
import shutil
from ultralytics import YOLO

# ========== 配置 ==========
BASE = os.path.dirname(__file__)
IMAGE_DIR = os.path.join(BASE, "dataset", "images")
LABEL_DIR = os.path.join(BASE, "dataset", "labels")
MODEL_DIR = os.path.join(BASE, "model")
os.makedirs(MODEL_DIR, exist_ok=True)

EPOCHS = 30
IMG_SIZE = 640
BATCH = 32
WORKERS = 4
PATIENCE = 10


def auto_split():
    """如果没有分集，自动按 8:2 分成 train/val"""
    train_img = os.path.join(BASE, "dataset", "train", "images")
    train_lbl = os.path.join(BASE, "dataset", "train", "labels")
    val_img   = os.path.join(BASE, "dataset", "val", "images")
    val_lbl   = os.path.join(BASE, "dataset", "val", "labels")

    if os.path.exists(train_img):
        print("检测到已有 train/val 分集，跳过自动分割")
        return BASE + "/dataset/data.yaml"

    print("自动分割训练集/验证集 (8:2)...")

    images = sorted(
        glob.glob(os.path.join(IMAGE_DIR, "*.png")) +
        glob.glob(os.path.join(IMAGE_DIR, "*.jpg")) +
        glob.glob(os.path.join(IMAGE_DIR, "*.jpeg"))
    )
    random.shuffle(images)
    split = int(len(images) * 0.8)
    train_imgs = images[:split]
    val_imgs = images[split:]

    for d in [train_img, train_lbl, val_img, val_lbl]:
        os.makedirs(d, exist_ok=True)

    for img in train_imgs:
        shutil.move(img, os.path.join(train_img, os.path.basename(img)))
        lbl = os.path.join(LABEL_DIR, os.path.splitext(os.path.basename(img))[0] + ".txt")
        if os.path.exists(lbl):
            shutil.move(lbl, os.path.join(train_lbl, os.path.basename(lbl)))

    for img in val_imgs:
        shutil.move(img, os.path.join(val_img, os.path.basename(img)))
        lbl = os.path.join(LABEL_DIR, os.path.splitext(os.path.basename(img))[0] + ".txt")
        if os.path.exists(lbl):
            shutil.move(lbl, os.path.join(val_lbl, os.path.basename(lbl)))

    print(f"训练集: {len(train_imgs)} 张 | 验证集: {len(val_imgs)} 张")

    # 生成 data.yaml
    yaml_path = os.path.join(BASE, "dataset", "data.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"path: {os.path.join(BASE, 'dataset')}\n")
        f.write("train: train/images\n")
        f.write("val: val/images\n\n")
        f.write("names:\n")
        f.write("  0: red_dot\n")
        f.write("  1: green_bubble\n")

    return yaml_path


def main():
    # 1. 分割数据集
    data_yaml = auto_split()

    # 2. 加载预训练模型
    print("\n加载 YOLO11s 预训练模型...")
    model = YOLO("yolo11s.pt")

    # 3. 训练（针对小数据集优化）
    print(f"\n开始训练（{EPOCHS} epochs, batch={BATCH}, size={IMG_SIZE}, patience={PATIENCE}）\n")
    results = model.train(
        data=data_yaml,
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH,
        patience=PATIENCE,
        name="wechat_red_dot",
        project=MODEL_DIR,
        exist_ok=True,
        verbose=True,
        workers=WORKERS,       # 多线程加载数据
        cache=True,            # 缓存图片到内存，减少IO
        # 针对小数据集的优化参数
        cos_lr=True,           # cosine学习率衰减
        warmup_epochs=5,       # 预热轮数（小数据集多预热几轮）
        lr0=0.0005,            # 学习率（小数据集用更小的lr）
        lrf=0.01,              # 最终lr因子
        momentum=0.937,
        weight_decay=0.0005,
        # 数据增强（小数据集加强增强）
        hsv_h=0.015,           # 色调变化
        hsv_s=0.7,             # 饱和度变化
        hsv_v=0.4,             # 明度变化
        degrees=5.0,           # 旋转角度
        translate=0.1,         # 平移
        scale=0.5,             # 缩放
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.5,
        mosaic=0.5,            # mosaic增强（小目标检测降低比例）
        mixup=0.1,             # mixup增强
        copy_paste=0.1,        # copy-paste增强（小目标友好）
    )

    # 4. 导出最佳模型到 model/wechat_dot.pt
    best_path = os.path.join(MODEL_DIR, "wechat_red_dot", "weights", "best.pt")
    final_path = os.path.join(MODEL_DIR, "wechat_dot.pt")
    if os.path.exists(best_path):
        shutil.copy(best_path, final_path)
        print(f"\n模型已导出: {final_path}")
    else:
        print("\n警告：未找到 best.pt，检查训练结果")

    # 5. 验证精度
    print("\n验证模型精度...")
    metrics = model.val()
    print(f"\nmAP@50: {metrics.box.map50:.3f}")
    print(f"mAP@50-95: {metrics.box.map:.3f}")

    print("\n训练完成！模型路径: model/wechat_dot.pt")
    print("下一步：python wechat_bot.py 启动新版机器人")


if __name__ == "__main__":
    main()
