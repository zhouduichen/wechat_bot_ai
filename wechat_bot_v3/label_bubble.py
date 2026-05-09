#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
绿色气泡标注工具 — 鼠标拖拽框选
用法：python label_bubble.py
  按住左键拖拽框选气泡 | 右键删框 | D=下一张 | A=上一张 | S=保存 | Q=退出
"""

import os, glob, tkinter as tk
from PIL import Image, ImageTk

BASE = os.path.dirname(__file__)
IMAGE_DIR = os.path.join(BASE, "dataset_bubble", "images")
LABEL_DIR = os.path.join(BASE, "dataset_bubble", "labels")

os.makedirs(LABEL_DIR, exist_ok=True)
images = sorted(glob.glob(os.path.join(IMAGE_DIR, "*.png")) +
                glob.glob(os.path.join(IMAGE_DIR, "*.jpg")))

if not images:
    print(f"错误：{IMAGE_DIR} 下没有图片，请先运行 python collect_bubble.py")
    exit(1)


class BubbleLabeler:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("绿色气泡标注工具 — 拖拽框选")
        self.root.geometry("1400x900")
        self.root.configure(bg="#1e1e1e")
        self.idx = 0
        self.boxes = []       # [(x1, y1, x2, y2), ...] 气泡矩形
        self.pil_img = None
        self.photo = None
        self.ox, self.oy = 0, 0
        self.drag_start = None
        self.drag_rect = None

        self._build()
        self._bind()
        self.load()

    def _build(self):
        top = tk.Frame(self.root, bg="#2d2d2d", height=40)
        top.pack(fill=tk.X, side=tk.TOP); top.pack_propagate(False)
        self.info = tk.Label(top, text="", bg="#2d2d2d", fg="#ccc", font=("Microsoft YaHei", 11))
        self.info.pack(side=tk.LEFT, padx=12, pady=8)
        btn = tk.Frame(top, bg="#2d2d2d"); btn.pack(side=tk.RIGHT, padx=8)
        for t, c in [("上一张(A)", self.prev), ("保存(S)", self.save), ("下一张(D)", self.next)]:
            tk.Button(btn, text=t, command=c, bg="#3d3d3d" if "保存" not in t else "#4e8cff",
                      fg="#fff" if "保存" in t else "#ccc", relief=tk.FLAT, padx=10).pack(side=tk.LEFT, padx=2)

        self.canvas = tk.Canvas(self.root, bg="#1e1e1e", cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.rclick)

        bot = tk.Frame(self.root, bg="#2d2d2d", height=28); bot.pack(fill=tk.X, side=tk.BOTTOM); bot.pack_propagate(False)
        tk.Label(bot, text="按住左键拖拽框选气泡 | 右键删框 | D/A=翻页 | S=保存 | Q=退出",
                 bg="#2d2d2d", fg="#888", font=("Microsoft YaHei", 8)).pack(side=tk.LEFT, padx=12, pady=4)

    def _bind(self):
        for k in ['d','D']: self.root.bind(f"<KeyPress-{k}>", lambda e: self.next())
        for k in ['a','A']: self.root.bind(f"<KeyPress-{k}>", lambda e: self.prev())
        for k in ['s','S']: self.root.bind(f"<KeyPress-{k}>", lambda e: self.save())
        for k in ['q','Q']: self.root.bind(f"<KeyPress-{k}>", lambda e: self.quit())
        self.root.bind("<Right>", lambda e: self.next())
        self.root.bind("<Left>", lambda e: self.prev())

    def load(self):
        path = images[self.idx]
        pil = Image.open(path)
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 100: cw = 1350
        if ch < 100: ch = 800
        s = min(1.0, cw/pil.width, ch/pil.height)
        pil = pil.resize((int(pil.width*s), int(pil.height*s)), Image.LANCZOS)
        self.pil_img = pil
        self.photo = ImageTk.PhotoImage(pil)
        self.ox = max(0, (cw - pil.width)//2)
        self.oy = max(0, (ch - pil.height)//2)
        self.canvas.delete("all")
        self.canvas.create_image(self.ox, self.oy, anchor=tk.NW, image=self.photo)
        self.load_labels()
        self._redraw()
        self.info.config(text=f"[{self.idx+1}/{len(images)}] {os.path.basename(path)}  气泡:{len(self.boxes)}")

    def load_labels(self):
        self.boxes = []
        lp = os.path.join(LABEL_DIR, os.path.splitext(os.path.basename(images[self.idx]))[0] + ".txt")
        if os.path.exists(lp):
            with open(lp) as f:
                for line in f:
                    p = line.strip().split()
                    if len(p) >= 5:
                        # YOLO: class x_center y_center width height (归一化)
                        cx, cy, w, h = float(p[1]), float(p[2]), float(p[3]), float(p[4])
                        x1 = int((cx - w/2) * self.pil_img.width)
                        y1 = int((cy - h/2) * self.pil_img.height)
                        x2 = int((cx + w/2) * self.pil_img.width)
                        y2 = int((cy + h/2) * self.pil_img.height)
                        self.boxes.append((x1, y1, x2, y2))

    def save_labels(self):
        lp = os.path.join(LABEL_DIR, os.path.splitext(os.path.basename(images[self.idx]))[0] + ".txt")
        iw, ih = self.pil_img.width, self.pil_img.height
        with open(lp, "w") as f:
            for x1, y1, x2, y2 in self.boxes:
                cx = ((x1 + x2) / 2) / iw
                cy = ((y1 + y2) / 2) / ih
                w = (x2 - x1) / iw
                h = (y2 - y1) / ih
                f.write(f"0 {max(0,min(1,cx)):.6f} {max(0,min(1,cy)):.6f} {max(0,min(1,w)):.6f} {max(0,min(1,h)):.6f}\n")

    def _redraw(self):
        for x1, y1, x2, y2 in self.boxes:
            self.canvas.create_rectangle(self.ox+x1, self.oy+y1, self.ox+x2, self.oy+y2,
                                         outline="#44ff44", width=2)
            self.canvas.create_oval(self.ox+(x1+x2)//2-3, self.oy+(y1+y2)//2-3,
                                    self.ox+(x1+x2)//2+3, self.oy+(y1+y2)//2+3,
                                    fill="#00ff00", outline="")

    # ---- 拖拽框选 ----

    def on_press(self, e):
        self.drag_start = (e.x - self.ox, e.y - self.oy)
        if self.drag_rect:
            self.canvas.delete(self.drag_rect)
            self.drag_rect = None

    def on_drag(self, e):
        if not self.drag_start:
            return
        x1, y1 = self.drag_start
        x2, y2 = e.x - self.ox, e.y - self.oy
        if self.drag_rect:
            self.canvas.delete(self.drag_rect)
        self.drag_rect = self.canvas.create_rectangle(
            self.ox+x1, self.oy+y1, self.ox+x2, self.oy+y2,
            outline="#ffff00", width=2, dash=(4, 4))

    def on_release(self, e):
        if not self.drag_start:
            return
        x1, y1 = self.drag_start
        x2, y2 = e.x - self.ox, e.y - self.oy
        if self.drag_rect:
            self.canvas.delete(self.drag_rect)
            self.drag_rect = None

        # 至少10像素才算有效框选
        if abs(x2 - x1) > 10 and abs(y2 - y1) > 10:
            x1, x2 = sorted([x1, x2])
            y1, y2 = sorted([y1, y2])
            x1 = max(0, x1); y1 = max(0, y1)
            x2 = min(self.pil_img.width, x2); y2 = min(self.pil_img.height, y2)
            self.boxes.append((x1, y1, x2, y2))
            self._redraw()
            print(f"  + 气泡 ({x1},{y1})-({x2},{y2})  {x2-x1}x{y2-y1}px  共{len(self.boxes)}个")

        self.drag_start = None

    # ---- 右键删除 ----

    def rclick(self, e):
        if not self.boxes:
            return
        cx, cy = e.x - self.ox, e.y - self.oy
        # 找包含点击位置的框
        for i, (x1, y1, x2, y2) in enumerate(self.boxes):
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                self.boxes.pop(i)
                self._redraw()
                print(f"  - 已删除  剩余{len(self.boxes)}个")
                return
        # 没点到框内，删最近的
        def dist(b):
            bx = (b[0] + b[2]) / 2; by = (b[1] + b[3]) / 2
            return (bx - cx) ** 2 + (by - cy) ** 2
        self.boxes.remove(min(self.boxes, key=dist))
        self._redraw()
        print(f"  - 已删除(最近)  剩余{len(self.boxes)}个")

    # ---- 翻页保存 ----

    def next(self):
        if self.idx < len(images)-1:
            self.save_labels(); self.idx += 1; self.load()

    def prev(self):
        if self.idx > 0:
            self.save_labels(); self.idx -= 1; self.load()

    def save(self):
        self.save_labels(); print(f"  已保存 ({len(self.boxes)}个气泡)"); self.next()

    def quit(self):
        if self.boxes: self.save_labels()
        all_lbl = glob.glob(os.path.join(LABEL_DIR, "*.txt"))
        total = sum(sum(1 for _ in open(p)) for p in all_lbl)
        print(f"\n完成！{len(all_lbl)}张已标注，共{total}个气泡")
        if total > 0: print("下一步：python train_bubble.py")
        self.root.destroy()

    def run(self):
        print(f"共{len(images)}张图片")
        print("按住左键拖拽框选绿色气泡，松开即标注\n")
        self.root.mainloop()


if __name__ == "__main__":
    BubbleLabeler().run()
