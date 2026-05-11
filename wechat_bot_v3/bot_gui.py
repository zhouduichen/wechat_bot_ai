#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""识流 AI · 桌面控制台"""

import os, sys, time, json, threading, queue, tkinter as tk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path: sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

import customtkinter as ctk
import webbrowser, wechat_bot

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ═══ 配色 ═══
PRI  = "#4f6ef7"     # 靛蓝主色
PRI_H= "#3b5de7"
ACC  = "#7c5cfc"
BG   = "#eef0f5"
SURF = "#ffffff"
TXT  = "#171923"
SUB  = "#555b6e"
BDR  = "#e0e3eb"
GRN  = "#22c55e"
RED  = "#ef4444"
LOG_BG="#10121b"
LOG_TX="#b4c2f0"
INP_BG="#f4f5f9"

POLICY_FILE = os.path.join(BASE_DIR, "reply_policy.json")
SKIP_FILE   = os.path.join(BASE_DIR, "skip_keywords.json")
RULES_FILE  = os.path.join(BASE_DIR, "auto_reply_rules.json")

def load_json(p, d):
    try:
        if os.path.exists(p):
            with open(p,"r",encoding="utf-8") as f: return json.load(f)
    except: pass
    return d

def save_json(p, d):
    with open(p,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)

bot_instance=None; bot_thread=None; bot_queue=queue.Queue()
status={"running":False,"round":0,"contacts":0}

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._fonts()
        self.title("识流 AI")
        self.geometry("920x700")
        self.minsize(780,560)
        self.configure(fg_color=BG)
        self._header()
        self.tabs=ctk.CTkTabview(self,fg_color="transparent",corner_radius=0)
        self.tabs.pack(fill="both",expand=True)
        for n in ["控制台","回复策略","回复规则","不回复关键词"]: self.tabs.add(n)
        sb=self.tabs._segmented_button
        sb.configure(fg_color=BG,selected_color=PRI,unselected_color="#e0e3eb",
                     selected_hover_color=ACC,text_color=TXT,
                     font=ctk.CTkFont(family="Microsoft YaHei UI",size=14,weight="bold"))
        self._console(); self._policy(); self._rules(); self._skip()
        self.log_cache=[]
        self._poll()
        self.protocol("WM_DELETE_WINDOW",self._close)

    def _fonts(self):
        self.f={"h1":ctk.CTkFont("Microsoft YaHei UI",24,"bold"),
                "h2":ctk.CTkFont("Microsoft YaHei UI",16,"bold"),
                "h3":ctk.CTkFont("Microsoft YaHei UI",14,"bold"),
                "b":ctk.CTkFont("Microsoft YaHei UI",14),
                "s":ctk.CTkFont("Microsoft YaHei UI",12),
                "xs":ctk.CTkFont("Microsoft YaHei UI",11),
                "m":ctk.CTkFont("Cascadia Code",11)}

    def _card(self,p,**kw):
        return ctk.CTkFrame(p,fg_color=SURF,corner_radius=12,border_width=1,border_color=BDR,**kw)

    def _sec(self,p,txt,sub=""):
        r=ctk.CTkFrame(p,fg_color="transparent"); r.pack(fill="x",padx=22,pady=(18,8))
        ctk.CTkLabel(r,text=txt,font=self.f["h2"],text_color=TXT).pack(side="left")
        if sub: ctk.CTkLabel(r,text=sub,font=self.f["s"],text_color=SUB).pack(side="right")

    def _tag(self,p,txt,bg,fg):
        t=ctk.CTkFrame(p,fg_color=bg,corner_radius=8)
        ctk.CTkLabel(t,text=txt,font=self.f["xs"],text_color=fg,padx=8,pady=2).pack()
        return t

    def _header(self):
        f=tk.Frame(self,bg=PRI,height=68,bd=0,highlightthickness=0)
        f.pack(fill="x"); f.pack_propagate(False)
        c=tk.Canvas(f,bg=PRI,height=68,bd=0,highlightthickness=0)
        c.pack(fill="both",expand=True)
        # 渐变
        for i in range(68):
            r=int(0x4f+(0x7c-0x4f)*i/68)
            g=int(0x6e+(0x5c-0x6e)*i/68)
            b_=int(0xf7+(0xfc-0xf7)*i/68)
            c.create_line(0,i,920,i,fill=f"#{r:02x}{g:02x}{b_:02x}")
        c.create_text(26,26,anchor="w",text="识流 AI",fill="#fff",font=("Microsoft YaHei UI",22,"bold"))
        c.create_text(26,48,anchor="w",text="微信自动回复机器人",fill="#c8d0f0",font=("Microsoft YaHei UI",11))

    # ═══ 控制台 ═══
    def _console(self):
        t=self.tabs.tab("控制台"); t.configure(fg_color=BG)
        c=self._card(t); c.pack(fill="x",padx=20,pady=(14,10))
        row=ctk.CTkFrame(c,fg_color="transparent"); row.pack(fill="x",padx=22,pady=(16,12))
        # 状态
        self.dc=tk.Canvas(row,width=18,height=18,bg=SURF,highlightthickness=0)
        self.dc.pack(side="left",padx=(0,12))
        self.di=self.dc.create_oval(3,3,15,15,fill="#d1d5db",outline="")
        info=ctk.CTkFrame(row,fg_color="transparent"); info.pack(side="left")
        self.sl=ctk.CTkLabel(info,text="已停止",font=self.f["h1"],text_color="#9ca3af"); self.sl.pack(anchor="w")
        self.ss=ctk.CTkLabel(info,text="准备就绪",font=self.f["s"],text_color=SUB); self.ss.pack(anchor="w")
        # 统计
        st=ctk.CTkFrame(row,fg_color="transparent"); st.pack(side="right")
        for lb,k in [("轮次","round"),("处理","contacts")]:
            bx=ctk.CTkFrame(st,fg_color=INP_BG,corner_radius=12); bx.pack(side="left",padx=5)
            n=ctk.CTkLabel(bx,text="0",font=ctk.CTkFont("Microsoft YaHei UI",26,"bold"),text_color=PRI)
            n.pack(padx=20,pady=(10,0))
            ctk.CTkLabel(bx,text=lb,font=self.f["xs"],text_color=SUB).pack(padx=20,pady=(0,10))
            setattr(self,f"st_{k}",n)
        # 按钮
        br=ctk.CTkFrame(c,fg_color="transparent"); br.pack(fill="x",padx=22,pady=(2,14))
        self.bs=ctk.CTkButton(br,text="▶  启动",font=self.f["h3"],fg_color=GRN,hover_color="#16a34a",
                               width=130,height=40,corner_radius=10,command=self._start)
        self.bs.pack(side="left",padx=(0,10))
        self.bp=ctk.CTkButton(br,text="⏹  停止",font=self.f["h3"],fg_color=RED,hover_color="#dc2626",
                               width=100,height=40,corner_radius=10,command=self._stop,state="disabled")
        self.bp.pack(side="left")
        self.lt=ctk.CTkLabel(br,text="",font=self.f["s"],text_color=SUB); self.lt.pack(side="right")
        # 日志
        c2=self._card(t); c2.pack(fill="both",expand=True,padx=20,pady=(0,10))
        lb2=ctk.CTkFrame(c2,fg_color="transparent"); lb2.pack(fill="x",padx=22,pady=(14,8))
        ctk.CTkLabel(lb2,text="实时日志",font=self.f["h2"],text_color=TXT).pack(side="left")
        self.lc=ctk.CTkLabel(lb2,text="0 条",font=self.f["s"],text_color=SUB); self.lc.pack(side="right",padx=(0,10))
        ctk.CTkButton(lb2,text="清屏",font=self.f["xs"],fg_color="#f1f3f6",text_color=SUB,
                     hover_color="#e2e5ee",width=50,height=26,corner_radius=6,
                     command=self._clog).pack(side="right")
        self.lx=ctk.CTkTextbox(c2,fg_color=LOG_BG,text_color=LOG_TX,font=self.f["m"],
                               corner_radius=8,wrap="word")
        self.lx.pack(fill="both",expand=True,padx=22,pady=(0,14))
        self.lx.insert("end","  就绪。\n"); self.lx.configure(state="disabled")
        # 快捷
        c3=self._card(t); c3.pack(fill="x",padx=20,pady=(0,10))
        bar=ctk.CTkFrame(c3,fg_color="transparent"); bar.pack(fill="x",padx=22,pady=14)
        ctk.CTkLabel(bar,text="快捷入口",font=self.f["h2"],text_color=TXT).pack(side="left")
        for lb,cb in [("🌐 网页后台",lambda:webbrowser.open("http://127.0.0.1/shiliu_ai/admin.html")),
                       ("📁 目录",lambda:os.startfile(BASE_DIR))]:
            ctk.CTkButton(bar,text=lb,font=self.f["s"],fg_color="#f1f3f6",text_color=SUB,
                         hover_color="#e2e5ee",width=100,height=30,corner_radius=8,command=cb).pack(side="right",padx=(8,0))

    # ═══ 回复策略 ═══
    def _policy(self):
        t=self.tabs.tab("回复策略"); t.configure(fg_color=BG)
        c=self._card(t); c.pack(fill="x",padx=20,pady=(14,10))
        self._sec(c,"默认回复模式")
        self._mv=ctk.StringVar(value="reply")
        mr=ctk.CTkFrame(c,fg_color="transparent"); mr.pack(fill="x",padx=22,pady=(4,14))
        for m,lb,sub in [("reply","全部回复","黑名单除外"),("skip","仅白名单","只回复白名单"),("ask","无限制","回复所有人")]:
            opt=ctk.CTkFrame(mr,fg_color="transparent"); opt.pack(side="left",padx=(0,12))
            ctk.CTkRadioButton(opt,text="",variable=self._mv,value=m,font=self.f["b"],
                              fg_color=PRI,hover_color=ACC,command=lambda m=m:self._pm(m)).pack(side="left")
            tx=ctk.CTkFrame(opt,fg_color="transparent"); tx.pack(side="left",padx=(4,0))
            ctk.CTkLabel(tx,text=lb,font=self.f["h3"],text_color=TXT).pack(anchor="w")
            ctk.CTkLabel(tx,text=sub,font=self.f["xs"],text_color=SUB).pack(anchor="w")

        for title,key,bg,fg in [("白名单 · 始终回复","always_reply","#ecfdf5","#065f46"),
                                 ("黑名单 · 永不回复","never_reply","#fef2f2","#991b1b")]:
            c2=self._card(t); c2.pack(fill="x",padx=20,pady=(0,10))
            self._sec(c2,title)
            tf=ctk.CTkFrame(c2,fg_color="transparent"); tf.pack(fill="x",padx=22,pady=(2,8))
            setattr(self,f"_pt_{key}",tf)
            ir=ctk.CTkFrame(c2,fg_color="transparent"); ir.pack(fill="x",padx=22,pady=(0,14))
            inp=ctk.CTkEntry(ir,placeholder_text="输入名字，回车添加",font=self.f["b"],
                            height=36,fg_color=INP_BG,border_color=BDR,corner_radius=8)
            inp.pack(side="left",fill="x",expand=True,padx=(0,8))
            inp.bind("<Return>",lambda e,k=key:self._pa(k))
            setattr(self,f"_pi_{key}",inp)
            ctk.CTkButton(ir,text="添加",font=self.f["b"],fg_color=PRI,hover_color=PRI_H,
                         width=66,height=36,corner_radius=8,command=lambda k=key:self._pa(k)).pack(side="left")
        self._pl()

    def _pl(self):
        self._po=load_json(POLICY_FILE,{"default":"reply","always_reply":[],"never_reply":[],"contact_overrides":{}})
        self._mv.set(self._po.get("default","reply")); self._pr()

    def _ps(self):
        save_json(POLICY_FILE,self._po); self._pr()

    def _pm(self,m): self._po["default"]=m; self._ps()
    def _pa(self,key):
        inp=getattr(self,f"_pi_{key}"); n=inp.get().strip()
        if not n: return
        if n not in self._po[key]: self._po[key].append(n)
        inp.delete(0,"end"); self._ps()

    def _prm(self,key,name):
        self._po[key]=[x for x in self._po[key] if x!=name]; self._ps()

    def _pr(self):
        for key,bg,fg in [("always_reply","#ecfdf5","#065f46"),("never_reply","#fef2f2","#991b1b")]:
            frame=getattr(self,f"_pt_{key}")
            for w in frame.winfo_children(): w.destroy()
            items=self._po.get(key,[])
            if not items:
                ctk.CTkLabel(frame,text="暂无",font=self.f["s"],text_color=SUB).pack(side="left",pady=4); continue
            for name in items:
                tg=ctk.CTkFrame(frame,fg_color=bg,corner_radius=16)
                tg.pack(side="left",padx=3,pady=3)
                ctk.CTkLabel(tg,text=name,font=self.f["s"],text_color=fg).pack(side="left",padx=(14,2),pady=5)
                ctk.CTkButton(tg,text="✕",font=self.f["xs"],fg_color=bg,hover_color=bg,
                             text_color=fg,width=22,height=22,
                             command=lambda n=name,k=key:self._prm(k,n)).pack(side="left",padx=(0,8))

    # ═══ 回复规则 ═══
    def _rules(self):
        t=self.tabs.tab("回复规则"); t.configure(fg_color=BG)
        c=self._card(t); c.pack(fill="x",padx=20,pady=(14,10))
        self._sec(c,"添加规则","先命中规则 → 再走 AI")
        fr=ctk.CTkFrame(c,fg_color="transparent"); fr.pack(fill="x",padx=22,pady=(4,8))
        self._rk=ctk.CTkEntry(fr,placeholder_text="关键词",font=self.f["b"],
                              height=36,fg_color=INP_BG,border_color=BDR,corner_radius=8)
        self._rk.pack(side="left",fill="x",expand=True,padx=(0,6))
        self._rm=ctk.CTkComboBox(fr,values=["包含匹配","完全匹配"],font=self.f["b"],width=110,height=36,
                                  corner_radius=8,fg_color=INP_BG,border_color=BDR,
                                  dropdown_fg_color=SURF,button_color=PRI)
        self._rm.set("包含匹配"); self._rm.pack(side="left",padx=3)
        self._rs=ctk.CTkComboBox(fr,values=["启用","停用"],font=self.f["b"],width=80,height=36,
                                  corner_radius=8,fg_color=INP_BG,border_color=BDR,
                                  dropdown_fg_color=SURF,button_color=PRI)
        self._rs.set("启用"); self._rs.pack(side="left",padx=3)
        fr2=ctk.CTkFrame(c,fg_color="transparent"); fr2.pack(fill="x",padx=22,pady=(2,14))
        self._rt=ctk.CTkEntry(fr2,placeholder_text="回复内容",font=self.f["b"],
                              height=36,fg_color=INP_BG,border_color=BDR,corner_radius=8)
        self._rt.pack(side="left",fill="x",expand=True,padx=(0,8))
        ctk.CTkButton(fr2,text="保存",font=self.f["h3"],fg_color=PRI,hover_color=PRI_H,
                     width=70,height=36,corner_radius=8,command=self._ra).pack(side="left")
        c2=self._card(t); c2.pack(fill="both",expand=True,padx=20,pady=(0,10))
        lb2=ctk.CTkFrame(c2,fg_color="transparent"); lb2.pack(fill="x",padx=22,pady=(16,8))
        ctk.CTkLabel(lb2,text="规则列表",font=self.f["h2"],text_color=TXT).pack(side="left")
        ctk.CTkButton(lb2,text="刷新",font=self.f["xs"],fg_color="#f1f3f6",text_color=SUB,
                     hover_color="#e2e5ee",width=48,height=26,corner_radius=6,
                     command=self._rl).pack(side="right")
        self._rf=ctk.CTkScrollableFrame(c2,fg_color="transparent")
        self._rf.pack(fill="both",expand=True,padx=18,pady=(0,14)); self._rl()

    def _rl(self):
        d=load_json(RULES_FILE,{"rules":[]}); rs=d.get("rules",[]); f=self._rf
        for w in f.winfo_children(): w.destroy()
        if not rs: ctk.CTkLabel(f,text="暂无规则",font=self.f["s"],text_color=SUB).pack(pady=32); return
        for rule in rs:
            rw=ctk.CTkFrame(f,fg_color=SURF,corner_radius=10,border_width=1,border_color=BDR)
            rw.pack(fill="x",pady=2)
            inn=ctk.CTkFrame(rw,fg_color="transparent"); inn.pack(fill="x",padx=16,pady=12)
            ctk.CTkLabel(inn,text=f"#{rule['id']}",font=self.f["xs"],text_color=SUB,
                        fg_color=INP_BG,corner_radius=6,padx=8).pack(side="left")
            ctk.CTkLabel(inn,text=rule["keyword"],font=self.f["h3"],text_color=TXT).pack(side="left",padx=(8,4))
            mt="完全" if rule.get("match_type")=="equal" else "包含"
            self._tag(inn,mt,"#eff6ff","#1e40af").pack(side="left",padx=3)
            ac=rule.get("is_active",1)==1
            self._tag(inn,"启用" if ac else "停用","#ecfdf5" if ac else "#f3f4f6",
                     "#065f46" if ac else "#6b7280").pack(side="left",padx=3)
            ctk.CTkLabel(inn,text=rule.get("reply_text","")[:30],font=self.f["s"],text_color=SUB).pack(side="left",padx=(12,0))
            bt=ctk.CTkFrame(rw,fg_color="transparent"); bt.pack(side="right",padx=16,pady=12)
            ctk.CTkButton(bt,text="切换",font=self.f["xs"],fg_color="#f1f3f6",text_color=SUB,
                         hover_color="#e2e5ee",width=44,height=26,corner_radius=6,
                         command=lambda r=rule:self._rtg(r)).pack(side="left",padx=2)
            ctk.CTkButton(bt,text="删除",font=self.f["xs"],fg_color=RED,hover_color="#dc2626",
                         width=44,height=26,corner_radius=6,
                         command=lambda r=rule:self._rdl(r)).pack(side="left",padx=2)

    def _ra(self):
        kw=self._rk.get().strip(); txt=self._rt.get().strip()
        if not kw or not txt: return
        d=load_json(RULES_FILE,{"rules":[]})
        rid=max((r.get("id",0) for r in d["rules"]),default=0)+1
        mt="equal" if self._rm.get()=="完全匹配" else "contain"
        ac=1 if self._rs.get()=="启用" else 0
        d["rules"].append({"id":rid,"keyword":kw,"match_type":mt,"reply_text":txt,"is_active":ac})
        save_json(RULES_FILE,d)
        self._rk.delete(0,"end"); self._rt.delete(0,"end"); self._rl()

    def _rtg(self,rule):
        d=load_json(RULES_FILE,{"rules":[]})
        for r in d["rules"]:
            if r["id"]==rule["id"]: r["is_active"]=0 if r.get("is_active",1)==1 else 1
        save_json(RULES_FILE,d); self._rl()

    def _rdl(self,rule):
        d=load_json(RULES_FILE,{"rules":[]})
        d["rules"]=[r for r in d["rules"] if r["id"]!=rule["id"]]
        save_json(RULES_FILE,d); self._rl()

    # ═══ 不回复关键词 ═══
    def _skip(self):
        t=self.tabs.tab("不回复关键词"); t.configure(fg_color=BG)
        c=self._card(t); c.pack(fill="x",padx=20,pady=(14,10))
        self._sec(c,"添加关键词","命中则不回复")
        fr=ctk.CTkFrame(c,fg_color="transparent"); fr.pack(fill="x",padx=22,pady=(4,14))
        self._sk=ctk.CTkEntry(fr,placeholder_text="关键词",font=self.f["b"],
                              height=36,fg_color=INP_BG,border_color=BDR,corner_radius=8)
        self._sk.pack(side="left",fill="x",expand=True,padx=(0,6))
        self._sm=ctk.CTkComboBox(fr,values=["包含匹配","完全匹配"],font=self.f["b"],width=110,height=36,
                                  corner_radius=8,fg_color=INP_BG,border_color=BDR,
                                  dropdown_fg_color=SURF,button_color=PRI)
        self._sm.set("包含匹配"); self._sm.pack(side="left",padx=3)
        self._ss=ctk.CTkComboBox(fr,values=["启用","停用"],font=self.f["b"],width=80,height=36,
                                  corner_radius=8,fg_color=INP_BG,border_color=BDR,
                                  dropdown_fg_color=SURF,button_color=PRI)
        self._ss.set("启用"); self._ss.pack(side="left",padx=3)
        ctk.CTkButton(fr,text="添加",font=self.f["h3"],fg_color=PRI,hover_color=PRI_H,
                     width=66,height=36,corner_radius=8,command=self._sadd).pack(side="left",padx=(6,0))
        c2=self._card(t); c2.pack(fill="both",expand=True,padx=20,pady=(0,10))
        lb2=ctk.CTkFrame(c2,fg_color="transparent"); lb2.pack(fill="x",padx=22,pady=(16,8))
        ctk.CTkLabel(lb2,text="关键词列表",font=self.f["h2"],text_color=TXT).pack(side="left")
        ctk.CTkButton(lb2,text="刷新",font=self.f["xs"],fg_color="#f1f3f6",text_color=SUB,
                     hover_color="#e2e5ee",width=48,height=26,corner_radius=6,
                     command=self._sld).pack(side="right")
        self._sf=ctk.CTkScrollableFrame(c2,fg_color="transparent")
        self._sf.pack(fill="both",expand=True,padx=18,pady=(0,14)); self._sld()

    def _sld(self):
        d=load_json(SKIP_FILE,{"keywords":[]}); ks=d.get("keywords",[]); f=self._sf
        for w in f.winfo_children(): w.destroy()
        if not ks: ctk.CTkLabel(f,text="暂无关键词",font=self.f["s"],text_color=SUB).pack(pady=32); return
        for i,kw in enumerate(ks):
            rw=ctk.CTkFrame(f,fg_color=SURF,corner_radius=10,border_width=1,border_color=BDR)
            rw.pack(fill="x",pady=2)
            inn=ctk.CTkFrame(rw,fg_color="transparent"); inn.pack(fill="x",padx=16,pady=12)
            ctk.CTkLabel(inn,text=kw["keyword"],font=self.f["h3"],text_color=TXT).pack(side="left")
            mt="完全" if kw.get("match_type")=="equal" else "包含"
            self._tag(inn,mt,"#eff6ff","#1e40af").pack(side="left",padx=(8,3))
            ac=kw.get("is_active",True)
            self._tag(inn,"启用" if ac else "停用","#ecfdf5" if ac else "#f3f4f6",
                     "#065f46" if ac else "#6b7280").pack(side="left",padx=3)
            bt=ctk.CTkFrame(rw,fg_color="transparent"); bt.pack(side="right",padx=16,pady=12)
            ctk.CTkButton(bt,text="切换",font=self.f["xs"],fg_color="#f1f3f6",text_color=SUB,
                         hover_color="#e2e5ee",width=44,height=26,corner_radius=6,
                         command=lambda i=i:self._stg(i)).pack(side="left",padx=2)
            ctk.CTkButton(bt,text="删除",font=self.f["xs"],fg_color=RED,hover_color="#dc2626",
                         width=44,height=26,corner_radius=6,
                         command=lambda i=i:self._sdel(i)).pack(side="left",padx=2)

    def _sadd(self):
        kw=self._sk.get().strip()
        if not kw: return
        d=load_json(SKIP_FILE,{"keywords":[]})
        mt="equal" if self._sm.get()=="完全匹配" else "contain"
        ac=self._ss.get()=="启用"
        d["keywords"].append({"keyword":kw,"match_type":mt,"is_active":ac})
        save_json(SKIP_FILE,d); self._sk.delete(0,"end"); self._sld()

    def _stg(self,i):
        d=load_json(SKIP_FILE,{"keywords":[]})
        d["keywords"][i]["is_active"]=not d["keywords"][i].get("is_active",True)
        save_json(SKIP_FILE,d); self._sld()

    def _sdel(self,i):
        d=load_json(SKIP_FILE,{"keywords":[]}); d["keywords"].pop(i)
        save_json(SKIP_FILE,d); self._sld()

    # ═══ Bot ═══
    def _start(self):
        global bot_thread,status
        if status["running"]: return
        self._ui(True); status["running"]=True; status["round"]=0; status["contacts"]=0
        self._log("启动..."); bot_thread=threading.Thread(target=self._run,daemon=True); bot_thread.start()

    def _stop(self):
        global status
        if not status["running"]: return
        if bot_instance: bot_instance.running=False
        status["running"]=False; self._log("停止..."); self._ui(False)

    def _ui(self,on):
        if on:
            self.dc.itemconfig(self.di,fill=GRN); self.sl.configure(text="运行中",text_color=GRN)
            self.ss.configure(text="监听中..."); self.bs.configure(state="disabled"); self.bp.configure(state="normal")
        else:
            self.dc.itemconfig(self.di,fill="#d1d5db"); self.sl.configure(text="已停止",text_color="#9ca3af")
            self.ss.configure(text="准备就绪"); self.bs.configure(state="normal"); self.bp.configure(state="disabled")

    def _run(self):
        global bot_instance,status
        try:
            import comtypes; comtypes.CoInitialize()
            bot_instance=wechat_bot.WechatBotV6()
            import builtins; op=builtins.print
            def hp(*a,**kw):
                op(*a,**kw); m=" ".join(str(x) for x in a)
                if m.strip(): bot_queue.put({"text":m.strip(),"level":"info"})
            builtins.print=hp
            import logging
            class QH(logging.Handler):
                def emit(self,r): bot_queue.put({"text":self.format(r),"level":r.levelname.lower()})
            qh=QH(); qh.setFormatter(logging.Formatter("%(message)s")); logging.getLogger().addHandler(qh)
            bot_instance.run()
            builtins.print=op; logging.getLogger().removeHandler(qh)
        except Exception as e:
            import traceback
            bot_queue.put({"text":f"异常:{e}","level":"error"})
            bot_queue.put({"text":traceback.format_exc(),"level":"error"})
        finally:
            builtins.print=op
            try: logging.getLogger().removeHandler(qh)
            except: pass
            status["running"]=False
            self.after(0,lambda:self._ui(False))
            self.after(0,lambda:self._log("已停止"))
            try: import comtypes; comtypes.CoUninitialize()
            except: pass

    def _log(self,txt):
        self.log_cache.append(txt)
        if len(self.log_cache)>500: self.log_cache.pop(0)
        self.lx.configure(state="normal")
        self.lx.insert("end",f"[{time.strftime('%H:%M:%S')}] {txt}\n")
        self.lx.see("end"); self.lx.configure(state="disabled")
        self.lc.configure(text=f"{len(self.log_cache)} 条")

    def _clog(self):
        self.log_cache.clear(); self.lx.configure(state="normal")
        self.lx.delete("1.0","end"); self.lx.insert("end","  已清屏\n"); self.lx.configure(state="disabled")
        self.lc.configure(text="0 条")

    def _poll(self):
        while not bot_queue.empty():
            try: self._log(bot_queue.get_nowait()["text"])
            except queue.Empty: break
        if status["running"]: self.lt.configure(text=time.strftime("%H:%M:%S"))
        self.after(600,self._poll)

    def _close(self):
        if status["running"]: self._stop(); time.sleep(0.5)
        self.destroy()

if __name__=="__main__":
    App().mainloop()
