#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YOLO标注工具 v2 — 支持红点(类别0) + 绿色气泡(类别1)
用法：python label.py

操作：
  左键点击  = 标注当前类别（默认红点）
  右键点击  = 删除最近的框
  1 = 切换为 红点(类别0)
  2 = 切换为 绿色气泡(类别1)
  D/A = 下一张/上一张（自动保存）
  S = 保存
  Q = 退出

框颜色：绿色=红点  蓝色=绿色气泡
"""

import os, glob, json, tkinter as tk
from PIL import Image, ImageTk

BASE = os.path.dirname(__file__)
IMAGE_DIR = os.path.join(BASE, "dataset", "images")
LABEL_DIR = os.path.join(BASE, "dataset", "labels")
BOX_SIZE = 20

os.makedirs(LABEL_DIR, exist_ok=True)

images = sorted(
    glob.glob(os.path.join(IMAGE_DIR, "*.png")) +
    glob.glob(os.path.join(IMAGE_DIR, "*.jpg")) +
    glob.glob(os.path.join(IMAGE_DIR, "*.jpeg"))
)

if not images:
    print(f"错误：{IMAGE_DIR} 下没有图片，请先运行 collect.py")
    exit(1)

CLASS_COLORS = {0: "#00ff00", 1: "#4488ff"}
CLASS_NAMES = {0: "红点", 1: "绿色气泡"}


class LabelApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("YOLO Label Tool v2")
        self.root.geometry("1400x900")
        self.root.configure(bg="#1e1e1e")

        self.idx = 0
        self.current_class = 0
        self.boxes = []      # [(cx, cy, class_id), ...]
        self.rect_ids = []
        self.circle_ids = []
        self.photo = None
        self.pil_img = None
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

        self._build_ui()
        self._bind_keys()
        self.load()

    def _build_ui(self):
        top = tk.Frame(self.root, bg="#2d2d2d", height=40)
        top.pack(fill=tk.X, side=tk.TOP)
        top.pack_propagate(False)

        self.info_label = tk.Label(top, text="", bg="#2d2d2d", fg="#cccccc",
                                   font=("Microsoft YaHei", 11))
        self.info_label.pack(side=tk.LEFT, padx=12, pady=8)

        self.class_label = tk.Label(top, text="当前: 红点(类别0)", bg="#4e8cff",
                                    fg="#fff", font=("Microsoft YaHei", 10), padx=10)
        self.class_label.pack(side=tk.LEFT, padx=8, pady=6)

        btn = tk.Frame(top, bg="#2d2d2d")
        btn.pack(side=tk.RIGHT, padx=8)
        tk.Button(btn, text="上一张(A)", command=self.prev_img,
                  bg="#3d3d3d", fg="#ccc", relief=tk.FLAT, padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(btn, text="保存(S)", command=self.save,
                  bg="#4e8cff", fg="#fff", relief=tk.FLAT, padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(btn, text="下一张(D)", command=self.next_img,
                  bg="#3d3d3d", fg="#ccc", relief=tk.FLAT, padx=10).pack(side=tk.LEFT, padx=2)

        self.canvas = tk.Canvas(self.root, bg="#1e1e1e", cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-3>", self.on_right_click)

        bottom = tk.Frame(self.root, bg="#2d2d2d", height=28)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        bottom.pack_propagate(False)
        tk.Label(bottom, text="1=红点 | 2=绿色气泡 | 左键=标注 | 右键=删除 | D/A=翻页 | S=保存 | Q=退出",
                 bg="#2d2d2d", fg="#888", font=("Microsoft YaHei", 8)).pack(side=tk.LEFT, padx=12, pady=4)

    def _bind_keys(self):
        for k in ['d', 'D']:
            self.root.bind(f"<KeyPress-{k}>", lambda e: self.next_img())
        for k in ['a', 'A']:
            self.root.bind(f"<KeyPress-{k}>", lambda e: self.prev_img())
        for k in ['s', 'S']:
            self.root.bind(f"<KeyPress-{k}>", lambda e: self.save())
        for k in ['q', 'Q']:
            self.root.bind(f"<KeyPress-{k}>", lambda e: self.quit())
        self.root.bind("<Right>", lambda e: self.next_img())
        self.root.bind("<Left>", lambda e: self.prev_img())
        self.root.bind("<KeyPress-1>", lambda e: self.set_class(0))
        self.root.bind("<KeyPress-2>", lambda e: self.set_class(1))

    def set_class(self, cls):
        self.current_class = cls
        self.class_label.config(text=f"当前: {CLASS_NAMES[cls]}(类别{cls})",
                                bg=CLASS_COLORS[cls])

    def load(self):
        path = images[self.idx]
        pil_img = Image.open(path)
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 100: cw = 1350
        if ch < 100: ch = 800
        scale = min(1.0, cw / pil_img.width, ch / pil_img.height)
        new_w, new_h = int(pil_img.width * scale), int(pil_img.height * scale)
        pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

        self.scale = scale
        self.pil_img = pil_img
        self.photo = ImageTk.PhotoImage(pil_img)
        self.offset_x = max(0, (cw - new_w) // 2)
        self.offset_y = max(0, (ch - new_h) // 2)

        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.photo)
        self.load_labels()
        self._redraw()
        self._update_info()

    def load_labels(self):
        self.boxes = []
        base = os.path.splitext(os.path.basename(images[self.idx]))[0]
        lp = os.path.join(LABEL_DIR, base + ".txt")
        if os.path.exists(lp):
            with open(lp) as f:
                for line in f:
                    p = line.strip().split()
                    if len(p) >= 5:
                        cls = int(p[0])
                        x = int(float(p[1]) * self.pil_img.width)
                        y = int(float(p[2]) * self.pil_img.height)
                        self.boxes.append((x, y, cls))

    def save_labels(self):
        base = os.path.splitext(os.path.basename(images[self.idx]))[0]
        lp = os.path.join(LABEL_DIR, base + ".txt")
        iw, ih = self.pil_img.width, self.pil_img.height
        with open(lp, "w") as f:
            for cx, cy, cls in self.boxes:
                x = cx / iw; y = cy / ih
                w = BOX_SIZE / iw; h = BOX_SIZE / ih
                f.write(f"{cls} {max(0,min(1,x)):.6f} {max(0,min(1,y)):.6f} {w:.6f} {h:.6f}\n")

    def _redraw(self):
        self.rect_ids.clear()
        self.circle_ids.clear()
        for cx, cy, cls in self.boxes:
            sx, sy = self.offset_x + cx, self.offset_y + cy
            r = BOX_SIZE // 2
            color = CLASS_COLORS.get(cls, "#00ff00")
            rid = self.canvas.create_rectangle(sx-r, sy-r, sx+r, sy+r, outline=color, width=2)
            cid = self.canvas.create_oval(sx-3, sy-3, sx+3, sy+3, fill="#ff0000" if cls == 0 else color, outline="")
            self.rect_ids.append(rid)
            self.circle_ids.append(cid)

    def _update_info(self):
        name = os.path.basename(images[self.idx])
        red = sum(1 for _, _, c in self.boxes if c == 0)
        green = sum(1 for _, _, c in self.boxes if c == 1)
        self.info_label.config(text=f"[{self.idx+1}/{len(images)}] {name}  红点:{red}  气泡:{green}")

    def on_click(self, event):
        cx, cy = event.x - self.offset_x, event.y - self.offset_y
        if cx < 0 or cy < 0 or cx >= self.pil_img.width or cy >= self.pil_img.height:
            return
        self.boxes.append((cx, cy, self.current_class))
        self._redraw()
        print(f"  + {CLASS_NAMES[self.current_class]} @ ({cx},{cy})  共{len(self.boxes)}个")

    def on_right_click(self, event):
        if not self.boxes:
            return
        cx, cy = event.x - self.offset_x, event.y - self.offset_y
        closest = min(self.boxes, key=lambda b: (b[0]-cx)**2 + (b[1]-cy)**2)
        self.boxes.remove(closest)
        self._redraw()
        print(f"  - 已删除  剩余{len(self.boxes)}个")

    def next_img(self):
        if self.idx < len(images) - 1:
            self.save_labels()
            self.idx += 1
            self.load()

    def prev_img(self):
        if self.idx > 0:
            self.save_labels()
            self.idx -= 1
            self.load()

    def save(self):
        self.save_labels()
        base = os.path.splitext(os.path.basename(images[self.idx]))[0]
        red = sum(1 for _, _, c in self.boxes if c == 0)
        green = sum(1 for _, _, c in self.boxes if c == 1)
        print(f"  已保存 {base}.txt (红点:{red} 气泡:{green})")
        self.next_img()

    def quit(self):
        if self.boxes:
            self.save_labels()
        all_lbl = glob.glob(os.path.join(LABEL_DIR, "*.txt"))
        total = 0
        for p in all_lbl:
            with open(p) as f:
                total += sum(1 for _ in f)
        print(f"\n完成！{len(all_lbl)}张已标注，共{total}个目标")
        if total > 0:
            print("下一步：python train.py")
        self.root.destroy()

    def run(self):
        print("=" * 50)
        print("操作：1=红点 | 2=绿色气泡 | 左键标注 | 右键删除 | D/A翻页")
        print("=" * 50)
        print(f"\n共{len(images)}张图片\n")
        self.root.mainloop()


if __name__ == "__main__":
    LabelApp().run()
