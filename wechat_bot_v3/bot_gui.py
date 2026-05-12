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

# ── palette ──
PRI   = "#5b6cf0"
PRI_H = "#4a5cd8"
ACC   = "#8b5cf6"
BG    = "#f3f4f8"
SURF  = "#ffffff"
TXT   = "#181b24"
SUB   = "#5f6478"
LIGHT = "#949aad"
BDR   = "#e6e9f0"
GRN   = "#22b369"
RED   = "#e5484d"
LOG_BG="#0d0f14"
LOG_TX="#9da8cc"
INP_BG="#f7f8fc"

P = os.path.join
PF=P(BASE_DIR,"reply_policy.json")
SF=P(BASE_DIR,"skip_keywords.json")
RF=P(BASE_DIR,"auto_reply_rules.json")

def ld(p,d):
    try:
        if os.path.exists(p):
            with open(p,"r",encoding="utf-8") as f: return json.load(f)
    except: pass
    return d
def sv(p,d):
    with open(p,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)

bot_i=None; bot_t=None; bot_q=queue.Queue()
st={"running":False,"round":0,"contacts":0}

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._init_fonts()
        self.title("识流 AI")
        self.geometry("900x680")
        self.minsize(760,540)
        self.configure(fg_color=BG)
        self._header()
        self._tabs()
        self._console(); self._policy(); self._rules(); self._skip()
        self.log_buf=[]
        self._poll()
        self.protocol("WM_DELETE_WINDOW",self._close)

    def _init_fonts(self):
        self.ff={
            "h1":ctk.CTkFont("Microsoft YaHei UI",26,"bold"),
            "h2":ctk.CTkFont("Microsoft YaHei UI",17,"bold"),
            "h3":ctk.CTkFont("Microsoft YaHei UI",14,"bold"),
            "body":ctk.CTkFont("Microsoft YaHei UI",14),
            "sm":ctk.CTkFont("Microsoft YaHei UI",12),
            "xs":ctk.CTkFont("Microsoft YaHei UI",11),
            "mono":ctk.CTkFont("Cascadia Code",11),
        }
    def _card(self,parent,**kw):
        return ctk.CTkFrame(parent,fg_color=SURF,corner_radius=12,
                           border_width=1,border_color=BDR,**kw)
    def _lab(self,parent,text,sub=""):
        r=ctk.CTkFrame(parent,fg_color="transparent")
        r.pack(fill="x",padx=24,pady=(18,8))
        ctk.CTkLabel(r,text=text,font=self.ff["h2"],text_color=TXT).pack(side="left")
        if sub: ctk.CTkLabel(r,text=sub,font=self.ff["sm"],text_color=LIGHT).pack(side="right")
    def _tag(self,parent,text,bg,fg):
        t=ctk.CTkFrame(parent,fg_color=bg,corner_radius=7)
        ctk.CTkLabel(t,text=text,font=self.ff["xs"],text_color=fg,padx=8,pady=2).pack()
        return t
    def _sep(self,parent):
        ctk.CTkFrame(parent,fg_color=BDR,height=1).pack(fill="x",padx=24)

    def _header(self):
        f=tk.Frame(self,bg=PRI,height=64,bd=0,highlightthickness=0)
        f.pack(fill="x"); f.pack_propagate(False)
        c=tk.Canvas(f,bg=PRI,height=64,bd=0,highlightthickness=0); c.pack(fill="both",expand=True)
        for i in range(64):
            r=int(0x5b+(0x8b-0x5b)*i/64); g=int(0x6c+(0x5c-0x6c)*i/64)
            b_=int(0xf0+(0xf6-0xf0)*i/64)
            c.create_line(0,i,900,i,fill=f"#{r:02x}{g:02x}{b_:02x}")
        c.create_text(28,26,anchor="w",text="识流 AI · 桌面控制台",fill="#fff",
                      font=("Microsoft YaHei UI",20,"bold"))
        c.create_text(28,46,anchor="w",text="微信自动回复机器人  ·  全部功能本地管理",
                      fill="#bcc6f0",font=("Microsoft YaHei UI",11))

    def _tabs(self):
        self.tv=ctk.CTkTabview(self,fg_color="transparent",corner_radius=0)
        self.tv.pack(fill="both",expand=True)
        for n in ["控制台","回复策略","回复规则","不回复关键词"]: self.tv.add(n)
        sb=self.tv._segmented_button
        sb.configure(fg_color=BG,selected_color=PRI,unselected_color="#e2e5ee",
                     selected_hover_color=ACC,text_color=TXT,
                     font=ctk.CTkFont("Microsoft YaHei UI",14,"bold"))

    # ── console ──
    def _console(self):
        t=self.tv.tab("控制台"); t.configure(fg_color=BG)
        c=self._card(t); c.pack(fill="x",padx=24,pady=(14,12))
        row=ctk.CTkFrame(c,fg_color="transparent"); row.pack(fill="x",padx=24,pady=(18,14))
        self.dot_cv=tk.Canvas(row,width=20,height=20,bg=SURF,highlightthickness=0)
        self.dot_cv.pack(side="left",padx=(0,14))
        self.dot_id=self.dot_cv.create_oval(4,4,16,16,fill="#d1d5db",outline="")
        inf=ctk.CTkFrame(row,fg_color="transparent"); inf.pack(side="left")
        self.st_lb=ctk.CTkLabel(inf,text="已停止",font=self.ff["h1"],text_color="#9ca3af"); self.st_lb.pack(anchor="w")
        self.st_sb=ctk.CTkLabel(inf,text="准备就绪，点击启动",font=self.ff["sm"],text_color=LIGHT); self.st_sb.pack(anchor="w")
        sr=ctk.CTkFrame(row,fg_color="transparent"); sr.pack(side="right")
        for lb,k in [("轮次","round"),("处理","contacts")]:
            bx=ctk.CTkFrame(sr,fg_color=INP_BG,corner_radius=12); bx.pack(side="left",padx=5)
            nl=ctk.CTkLabel(bx,text="0",font=ctk.CTkFont("Microsoft YaHei UI",28,"bold"),text_color=PRI)
            nl.pack(padx=22,pady=(10,0))
            ctk.CTkLabel(bx,text=lb,font=self.ff["xs"],text_color=LIGHT).pack(padx=22,pady=(0,10))
            setattr(self,f"st_{k}",nl)
        br=ctk.CTkFrame(c,fg_color="transparent"); br.pack(fill="x",padx=24,pady=(2,16))
        self.bs=ctk.CTkButton(br,text="▶  启动",font=self.ff["h3"],fg_color=GRN,hover_color="#1da05a",
                               width=130,height=42,corner_radius=10,command=self._start)
        self.bs.pack(side="left",padx=(0,12))
        self.bp=ctk.CTkButton(br,text="⏹  停止",font=self.ff["h3"],fg_color=RED,hover_color="#d63e42",
                               width=100,height=42,corner_radius=10,command=self._stop,state="disabled")
        self.bp.pack(side="left")
        self.lt=ctk.CTkLabel(br,text="",font=self.ff["sm"],text_color=LIGHT); self.lt.pack(side="right")

        c2=self._card(t); c2.pack(fill="both",expand=True,padx=24,pady=(0,12))
        lb2=ctk.CTkFrame(c2,fg_color="transparent"); lb2.pack(fill="x",padx=24,pady=(16,10))
        ctk.CTkLabel(lb2,text="实时日志",font=self.ff["h2"],text_color=TXT).pack(side="left")
        self.lc=ctk.CTkLabel(lb2,text="0 条",font=self.ff["sm"],text_color=LIGHT); self.lc.pack(side="right",padx=(0,10))
        ctk.CTkButton(lb2,text="清屏",font=self.ff["xs"],fg_color="#f1f3f6",text_color=LIGHT,
                     hover_color="#e2e5ee",width=52,height=28,corner_radius=7,
                     command=self._clog).pack(side="right")
        self.lx=ctk.CTkTextbox(c2,fg_color=LOG_BG,text_color=LOG_TX,font=self.ff["mono"],
                               corner_radius=10,wrap="word")
        self.lx.pack(fill="both",expand=True,padx=24,pady=(0,16))
        self.lx.insert("end","  就绪。\n"); self.lx.configure(state="disabled")

        c3=self._card(t); c3.pack(fill="x",padx=24,pady=(0,12))
        bar=ctk.CTkFrame(c3,fg_color="transparent"); bar.pack(fill="x",padx=24,pady=16)
        ctk.CTkLabel(bar,text="快捷入口",font=self.ff["h2"],text_color=TXT).pack(side="left")
        for lb,cb in [("🌐  网页后台",lambda:webbrowser.open("http://127.0.0.1/shiliu_ai/admin.html")),
                       ("📁  项目目录",lambda:os.startfile(BASE_DIR))]:
            ctk.CTkButton(bar,text=lb,font=self.ff["sm"],fg_color="#f1f3f6",text_color=SUB,
                         hover_color="#e2e5ee",width=110,height=32,corner_radius=8,command=cb).pack(side="right",padx=(8,0))

    # ── policy ──
    def _policy(self):
        t=self.tv.tab("回复策略"); t.configure(fg_color=BG)
        c=self._card(t); c.pack(fill="x",padx=24,pady=(14,12))
        self._lab(c,"默认回复模式")
        self._mv=ctk.StringVar(value="reply")
        mr=ctk.CTkFrame(c,fg_color="transparent"); mr.pack(fill="x",padx=24,pady=(4,16))
        modes=[("reply","全部回复","黑名单除外"),("skip","仅白名单","只回复白名单联系人"),("ask","无限制","回复所有人")]
        self._mc={}
        for m,lb,sub in modes:
            card=ctk.CTkFrame(mr,fg_color=INP_BG,corner_radius=10,border_width=2,border_color=BDR)
            card.pack(side="left",fill="x",expand=True,padx=(0,10))
            card.bind("<Button-1>",lambda e,m=m:self._pm(m))
            tx=ctk.CTkFrame(card,fg_color="transparent"); tx.pack(padx=16,pady=12)
            ctk.CTkRadioButton(tx,text=lb,variable=self._mv,value=m,font=self.ff["h3"],
                              fg_color=PRI,hover_color=ACC,
                              command=lambda m=m:self._pm(m)).pack(anchor="w")
            ctk.CTkLabel(tx,text=sub,font=self.ff["xs"],text_color=LIGHT).pack(anchor="w",padx=(28,0))
            self._mc[m]=card

        for title,key,bg,fg in [("白名单  ·  始终回复","always_reply","#eefaf3","#18794e"),
                                 ("黑名单  ·  永不回复","never_reply","#fef3f2","#c5221f")]:
            c2=self._card(t); c2.pack(fill="x",padx=24,pady=(0,12))
            self._lab(c2,title)
            tf=ctk.CTkFrame(c2,fg_color="transparent"); tf.pack(fill="x",padx=24,pady=(4,8))
            setattr(self,f"_pt_{key}",tf)
            ir=ctk.CTkFrame(c2,fg_color="transparent"); ir.pack(fill="x",padx=24,pady=(0,16))
            inp=ctk.CTkEntry(ir,placeholder_text="输入名字，回车添加",font=self.ff["body"],
                            height=38,fg_color=INP_BG,border_color=BDR,corner_radius=9)
            inp.pack(side="left",fill="x",expand=True,padx=(0,10))
            inp.bind("<Return>",lambda e,k=key:self._pa(k))
            setattr(self,f"_pi_{key}",inp)
            ctk.CTkButton(ir,text="添加",font=self.ff["body"],fg_color=PRI,hover_color=PRI_H,
                         width=70,height=38,corner_radius=9,command=lambda k=key:self._pa(k)).pack(side="left")
        self._pl()

    def _pl(self):
        self._po=ld(PF,{"default":"reply","always_reply":[],"never_reply":[],"contact_overrides":{}})
        self._mv.set(self._po.get("default","reply")); self._pr()
    def _ps(self): sv(PF,self._po); self._pr()
    def _pm(self,m):
        self._po["default"]=m; self._ps()
        for k,card in self._mc.items():
            card.configure(border_color=PRI if k==m else BDR)
    def _pa(self,key):
        inp=getattr(self,f"_pi_{key}"); n=inp.get().strip()
        if not n: return
        if n not in self._po[key]: self._po[key].append(n)
        inp.delete(0,"end"); self._ps()
    def _prm(self,key,name):
        self._po[key]=[x for x in self._po[key] if x!=name]; self._ps()
    def _pr(self):
        # 更新模式卡片边框
        dm=self._po.get("default","reply")
        for k,card in self._mc.items():
            card.configure(border_color=PRI if k==dm else BDR)
        for key,bg,fg in [("always_reply","#eefaf3","#18794e"),("never_reply","#fef3f2","#c5221f")]:
            frame=getattr(self,f"_pt_{key}")
            for w in frame.winfo_children(): w.destroy()
            items=self._po.get(key,[])
            if not items:
                ctk.CTkLabel(frame,text="暂无",font=self.ff["sm"],text_color=LIGHT).pack(side="left",pady=4); continue
            for name in items:
                tg=ctk.CTkFrame(frame,fg_color=bg,corner_radius=16)
                tg.pack(side="left",padx=4,pady=4)
                ctk.CTkLabel(tg,text=name,font=self.ff["sm"],text_color=fg).pack(side="left",padx=(16,4),pady=6)
                ctk.CTkButton(tg,text="✕",font=self.ff["xs"],fg_color=bg,hover_color=bg,
                             text_color=fg,width=24,height=24,
                             command=lambda n=name,k=key:self._prm(k,n)).pack(side="left",padx=(0,12))

    # ── rules ──
    def _rules(self):
        t=self.tv.tab("回复规则"); t.configure(fg_color=BG)
        c=self._card(t); c.pack(fill="x",padx=24,pady=(14,12))
        self._lab(c,"添加规则","先命中规则 → 再走 AI"); self._sep(c)
        fr=ctk.CTkFrame(c,fg_color="transparent"); fr.pack(fill="x",padx=24,pady=(12,8))
        self._rk=ctk.CTkEntry(fr,placeholder_text="关键词",font=self.ff["body"],
                              height=38,fg_color=INP_BG,border_color=BDR,corner_radius=9)
        self._rk.pack(side="left",fill="x",expand=True,padx=(0,8))
        self._rm=ctk.CTkComboBox(fr,values=["包含匹配","完全匹配"],font=self.ff["body"],width=114,height=38,
                                  corner_radius=9,fg_color=INP_BG,border_color=BDR,
                                  dropdown_fg_color=SURF,button_color=PRI)
        self._rm.set("包含匹配"); self._rm.pack(side="left",padx=4)
        self._rs=ctk.CTkComboBox(fr,values=["启用","停用"],font=self.ff["body"],width=84,height=38,
                                  corner_radius=9,fg_color=INP_BG,border_color=BDR,
                                  dropdown_fg_color=SURF,button_color=PRI)
        self._rs.set("启用"); self._rs.pack(side="left",padx=4)
        fr2=ctk.CTkFrame(c,fg_color="transparent"); fr2.pack(fill="x",padx=24,pady=(2,16))
        self._rt=ctk.CTkEntry(fr2,placeholder_text="回复内容",font=self.ff["body"],
                              height=38,fg_color=INP_BG,border_color=BDR,corner_radius=9)
        self._rt.pack(side="left",fill="x",expand=True,padx=(0,10))
        ctk.CTkButton(fr2,text="保存",font=self.ff["h3"],fg_color=PRI,hover_color=PRI_H,
                     width=74,height=38,corner_radius=9,command=self._ra).pack(side="left")
        c2=self._card(t); c2.pack(fill="both",expand=True,padx=24,pady=(0,12))
        lb2=ctk.CTkFrame(c2,fg_color="transparent"); lb2.pack(fill="x",padx=24,pady=(14,6))
        ctk.CTkLabel(lb2,text="规则列表",font=self.ff["h2"],text_color=TXT).pack(side="left")
        ctk.CTkButton(lb2,text="刷新",font=self.ff["xs"],fg_color="#f1f3f6",text_color=SUB,
                     hover_color="#e2e5ee",width=50,height=28,corner_radius=7,
                     command=self._rl).pack(side="right")
        self._rf=ctk.CTkScrollableFrame(c2,fg_color="transparent")
        self._rf.pack(fill="both",expand=True,padx=20,pady=(0,16)); self._rl()

    def _rl(self):
        d=ld(RF,{"rules":[]}); rs=d.get("rules",[]); f=self._rf
        for w in f.winfo_children(): w.destroy()
        if not rs: ctk.CTkLabel(f,text="暂无规则",font=self.ff["sm"],text_color=LIGHT).pack(pady=36); return
        for rule in rs:
            rw=ctk.CTkFrame(f,fg_color=SURF,corner_radius=8,border_width=1,border_color=BDR)
            rw.pack(fill="x",pady=1)
            inn=ctk.CTkFrame(rw,fg_color="transparent"); inn.pack(fill="x",padx=12,pady=7)
            ctk.CTkLabel(inn,text=f"#{rule['id']}",font=self.ff["xs"],text_color=LIGHT,
                        corner_radius=4,padx=6).pack(side="left")
            ctk.CTkLabel(inn,text=rule["keyword"],font=self.ff["h3"],text_color=TXT).pack(side="left",padx=(8,4))
            mt="完全" if rule.get("match_type")=="equal" else "包含"
            self._tag(inn,mt,"#eff3ff","#2946d8").pack(side="left",padx=3)
            ac=rule.get("is_active",1)==1
            self._tag(inn,"启用" if ac else "停用","#eefaf3" if ac else "#f3f4f6",
                     "#18794e" if ac else "#6b7280").pack(side="left",padx=3)
            ctk.CTkLabel(inn,text=rule.get("reply_text","")[:28],font=self.ff["sm"],text_color=SUB).pack(side="left",padx=(10,0))
            bt=ctk.CTkFrame(rw,fg_color="transparent"); bt.pack(side="right",padx=10,pady=7)
            ctk.CTkButton(bt,text="切换",font=self.ff["xs"],fg_color="#f1f3f6",text_color=SUB,
                         hover_color="#e2e5ee",width=42,height=24,corner_radius=6,
                         command=lambda r=rule:self._rtg(r)).pack(side="left",padx=2)
            ctk.CTkButton(bt,text="删除",font=self.ff["xs"],fg_color=RED,hover_color="#d63e42",
                         width=42,height=24,corner_radius=6,
                         command=lambda r=rule:self._rdl(r)).pack(side="left",padx=2)

    def _ra(self):
        kw=self._rk.get().strip(); txt=self._rt.get().strip()
        if not kw or not txt: return
        d=ld(RF,{"rules":[]})
        rid=max((r.get("id",0) for r in d["rules"]),default=0)+1
        d["rules"].append({"id":rid,"keyword":kw,"match_type":"equal" if self._rm.get()=="完全匹配" else "contain",
                           "reply_text":txt,"is_active":1 if self._rs.get()=="启用" else 0})
        sv(RF,d); self._rk.delete(0,"end"); self._rt.delete(0,"end"); self._rl()

    def _rtg(self,rule):
        d=ld(RF,{"rules":[]})
        for r in d["rules"]:
            if r["id"]==rule["id"]: r["is_active"]=0 if r.get("is_active",1)==1 else 1
        sv(RF,d); self._rl()

    def _rdl(self,rule):
        d=ld(RF,{"rules":[]}); d["rules"]=[r for r in d["rules"] if r["id"]!=rule["id"]]
        sv(RF,d); self._rl()

    # ── skip ──
    def _skip(self):
        t=self.tv.tab("不回复关键词"); t.configure(fg_color=BG)
        c=self._card(t); c.pack(fill="x",padx=24,pady=(14,12))
        self._lab(c,"添加关键词","命中则不回复，按顺序匹配"); self._sep(c)
        fr=ctk.CTkFrame(c,fg_color="transparent"); fr.pack(fill="x",padx=24,pady=(12,16))
        self._sk=ctk.CTkEntry(fr,placeholder_text="关键词",font=self.ff["body"],
                              height=38,fg_color=INP_BG,border_color=BDR,corner_radius=9)
        self._sk.pack(side="left",fill="x",expand=True,padx=(0,8))
        self._sm=ctk.CTkComboBox(fr,values=["包含匹配","完全匹配"],font=self.ff["body"],width=114,height=38,
                                  corner_radius=9,fg_color=INP_BG,border_color=BDR,
                                  dropdown_fg_color=SURF,button_color=PRI)
        self._sm.set("包含匹配"); self._sm.pack(side="left",padx=4)
        self._ss=ctk.CTkComboBox(fr,values=["启用","停用"],font=self.ff["body"],width=84,height=38,
                                  corner_radius=9,fg_color=INP_BG,border_color=BDR,
                                  dropdown_fg_color=SURF,button_color=PRI)
        self._ss.set("启用"); self._ss.pack(side="left",padx=4)
        ctk.CTkButton(fr,text="添加",font=self.ff["h3"],fg_color=PRI,hover_color=PRI_H,
                     width=70,height=38,corner_radius=9,command=self._sadd).pack(side="left",padx=(8,0))
        c2=self._card(t); c2.pack(fill="both",expand=True,padx=24,pady=(0,12))
        lb2=ctk.CTkFrame(c2,fg_color="transparent"); lb2.pack(fill="x",padx=24,pady=(18,10))
        ctk.CTkLabel(lb2,text="关键词列表",font=self.ff["h2"],text_color=TXT).pack(side="left")
        ctk.CTkButton(lb2,text="刷新",font=self.ff["xs"],fg_color="#f1f3f6",text_color=SUB,
                     hover_color="#e2e5ee",width=50,height=28,corner_radius=7,
                     command=self._sld).pack(side="right")
        self._sf=ctk.CTkScrollableFrame(c2,fg_color="transparent")
        self._sf.pack(fill="both",expand=True,padx=20,pady=(0,16)); self._sld()

    def _sld(self):
        d=ld(SF,{"keywords":[]}); ks=d.get("keywords",[]); f=self._sf
        for w in f.winfo_children(): w.destroy()
        if not ks: ctk.CTkLabel(f,text="暂无关键词",font=self.ff["sm"],text_color=LIGHT).pack(pady=36); return
        for i,kw in enumerate(ks):
            rw=ctk.CTkFrame(f,fg_color=SURF,corner_radius=8,border_width=1,border_color=BDR)
            rw.pack(fill="x",pady=1)
            inn=ctk.CTkFrame(rw,fg_color="transparent"); inn.pack(fill="x",padx=12,pady=7)
            ctk.CTkLabel(inn,text=kw["keyword"],font=self.ff["h3"],text_color=TXT).pack(side="left")
            mt="完全" if kw.get("match_type")=="equal" else "包含"
            self._tag(inn,mt,"#eff3ff","#2946d8").pack(side="left",padx=(8,3))
            ac=kw.get("is_active",True)
            self._tag(inn,"启用" if ac else "停用","#eefaf3" if ac else "#f3f4f6",
                     "#18794e" if ac else "#6b7280").pack(side="left",padx=3)
            bt=ctk.CTkFrame(rw,fg_color="transparent"); bt.pack(side="right",padx=10,pady=7)
            ctk.CTkButton(bt,text="切换",font=self.ff["xs"],fg_color="#f1f3f6",text_color=SUB,
                         hover_color="#e2e5ee",width=42,height=24,corner_radius=6,
                         command=lambda i=i:self._stg(i)).pack(side="left",padx=2)
            ctk.CTkButton(bt,text="删除",font=self.ff["xs"],fg_color=RED,hover_color="#d63e42",
                         width=42,height=24,corner_radius=6,
                         command=lambda i=i:self._sdel(i)).pack(side="left",padx=2)

    def _sadd(self):
        kw=self._sk.get().strip();
        if not kw: return
        d=ld(SF,{"keywords":[]})
        d["keywords"].append({"keyword":kw,"match_type":"equal" if self._sm.get()=="完全匹配" else "contain",
                              "is_active":self._ss.get()=="启用"})
        sv(SF,d); self._sk.delete(0,"end"); self._sld()

    def _stg(self,i):
        d=ld(SF,{"keywords":[]}); d["keywords"][i]["is_active"]=not d["keywords"][i].get("is_active",True)
        sv(SF,d); self._sld()

    def _sdel(self,i):
        d=ld(SF,{"keywords":[]}); d["keywords"].pop(i); sv(SF,d); self._sld()

    # ── bot ──
    def _start(self):
        global bot_t,st
        if st["running"]: return
        self._ui(True); st["running"]=True; st["round"]=0; st["contacts"]=0
        self._log("启动机器人..."); bot_t=threading.Thread(target=self._run,daemon=True); bot_t.start()

    def _stop(self):
        global st
        if not st["running"]: return
        if bot_i: bot_i.running=False
        st["running"]=False; self._log("停止机器人..."); self._ui(False)

    def _ui(self,on):
        if on:
            self.dot_cv.itemconfig(self.dot_id,fill=GRN)
            self.st_lb.configure(text="运行中",text_color=GRN); self.st_sb.configure(text="监听中...")
            self.bs.configure(state="disabled"); self.bp.configure(state="normal")
        else:
            self.dot_cv.itemconfig(self.dot_id,fill="#d1d5db")
            self.st_lb.configure(text="已停止",text_color="#9ca3af"); self.st_sb.configure(text="准备就绪，点击启动")
            self.bs.configure(state="normal"); self.bp.configure(state="disabled")

    def _run(self):
        global bot_i,st
        try:
            import comtypes; comtypes.CoInitialize()
            bot_i=wechat_bot.WechatBotV6()
            import builtins; op=builtins.print
            def hp(*a,**kw):
                op(*a,**kw); m=" ".join(str(x) for x in a)
                if m.strip(): bot_q.put({"text":m.strip(),"level":"info"})
            builtins.print=hp
            import logging
            class QH(logging.Handler):
                def emit(self,r): bot_q.put({"text":self.format(r),"level":r.levelname.lower()})
            qh=QH(); qh.setFormatter(logging.Formatter("%(message)s")); logging.getLogger().addHandler(qh)
            bot_i.run()
            builtins.print=op; logging.getLogger().removeHandler(qh)
        except Exception as e:
            import traceback
            bot_q.put({"text":f"异常:{e}","level":"error"})
            bot_q.put({"text":traceback.format_exc(),"level":"error"})
        finally:
            builtins.print=op
            try: logging.getLogger().removeHandler(qh)
            except: pass
            st["running"]=False
            self.after(0,lambda:self._ui(False))
            self.after(0,lambda:self._log("已停止"))
            try: import comtypes; comtypes.CoUninitialize()
            except: pass

    def _log(self,txt):
        self.log_buf.append(txt)
        if len(self.log_buf)>500: self.log_buf.pop(0)
        self.lx.configure(state="normal")
        self.lx.insert("end",f"[{time.strftime('%H:%M:%S')}] {txt}\n")
        self.lx.see("end"); self.lx.configure(state="disabled")
        self.lc.configure(text=f"{len(self.log_buf)} 条")

    def _clog(self):
        self.log_buf.clear(); self.lx.configure(state="normal")
        self.lx.delete("1.0","end"); self.lx.insert("end","  已清屏\n"); self.lx.configure(state="disabled")
        self.lc.configure(text="0 条")

    def _poll(self):
        while not bot_q.empty():
            try: self._log(bot_q.get_nowait()["text"])
            except queue.Empty: break
        if st["running"]: self.lt.configure(text=time.strftime("%H:%M:%S"))
        self.after(600,self._poll)

    def _close(self):
        if st["running"]: self._stop(); time.sleep(0.5)
        self.destroy()

if __name__=="__main__":
    App().mainloop()
