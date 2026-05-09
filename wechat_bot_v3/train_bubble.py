#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
训练绿色气泡检测模型 → model/wechat_bubble.pt
用法：python train_bubble.py
"""

import os, glob, random, shutil
from ultralytics import YOLO

BASE = os.path.dirname(__file__)
IMAGE_DIR = os.path.join(BASE, "dataset_bubble", "images")
LABEL_DIR = os.path.join(BASE, "dataset_bubble", "labels")
MODEL_DIR = os.path.join(BASE, "model")
os.makedirs(MODEL_DIR, exist_ok=True)

EPOCHS = 40
IMG_SIZE = 800
BATCH = 64
WORKERS = 4
PATIENCE = 10


def auto_split():
    train_img = os.path.join(BASE, "dataset_bubble", "train", "images")
    train_lbl = os.path.join(BASE, "dataset_bubble", "train", "labels")
    val_img = os.path.join(BASE, "dataset_bubble", "val", "images")
    val_lbl = os.path.join(BASE, "dataset_bubble", "val", "labels")

    if os.path.exists(train_img):
        print("已有 train/val 分集")
        return os.path.join(BASE, "dataset_bubble", "data.yaml")

    print("自动分割 8:2 ...")
    images = sorted(glob.glob(os.path.join(IMAGE_DIR, "*.png")) +
                    glob.glob(os.path.join(IMAGE_DIR, "*.jpg")))
    random.shuffle(images)
    split = int(len(images) * 0.8)

    for d in [train_img, train_lbl, val_img, val_lbl]:
        os.makedirs(d, exist_ok=True)

    for img in images[:split]:
        shutil.move(img, os.path.join(train_img, os.path.basename(img)))
        lbl = os.path.join(LABEL_DIR, os.path.splitext(os.path.basename(img))[0] + ".txt")
        if os.path.exists(lbl):
            shutil.move(lbl, os.path.join(train_lbl, os.path.basename(lbl)))

    for img in images[split:]:
        shutil.move(img, os.path.join(val_img, os.path.basename(img)))
        lbl = os.path.join(LABEL_DIR, os.path.splitext(os.path.basename(img))[0] + ".txt")
        if os.path.exists(lbl):
            shutil.move(lbl, os.path.join(val_lbl, os.path.basename(lbl)))

    print(f"训练集: {split} 张 | 验证集: {len(images)-split} 张")

    yaml_path = os.path.join(BASE, "dataset_bubble", "data.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"path: {os.path.join(BASE, 'dataset_bubble')}\n")
        f.write("train: train/images\nval: val/images\n\n")
        f.write("names:\n  0: green_bubble\n")
    return yaml_path


def main():
    data_yaml = auto_split()

    print("\n加载 YOLO11s 预训练模型...")
    model = YOLO("yolo11n.pt")

    print(f"\n开始训练（{EPOCHS} epochs）\n")
    model.train(
        data=data_yaml, epochs=EPOCHS, imgsz=IMG_SIZE, batch=BATCH,
        patience=PATIENCE, name="wechat_bubble", project=MODEL_DIR, exist_ok=True,
        verbose=True, workers=WORKERS, cache=True,
        cos_lr=True, warmup_epochs=5, lr0=0.0005, lrf=0.01,
        momentum=0.937, weight_decay=0.0005,
        hsv_h=0.015, hsv_s=0.7, hsv_v=0.4, degrees=5.0, translate=0.1,
        scale=0.5, fliplr=0.5, mosaic=0.5, mixup=0.1,
    )

    best = os.path.join(MODEL_DIR, "wechat_bubble", "weights", "best.pt")
    final = os.path.join(MODEL_DIR, "wechat_bubble.pt")
    if os.path.exists(best):
        shutil.copy(best, final)
        print(f"\n模型已导出: {final}")

    metrics = model.val()
    print(f"mAP@50: {metrics.box.map50:.3f} | mAP@50-95: {metrics.box.map:.3f}")
    print("\n完成！")


if __name__ == "__main__":
    main()
