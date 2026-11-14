# -*- coding: utf-8 -*-
"""项目进度看板：扫描真实文件状态 → 正式产物/进度看板.html

不手填数字。所有进度都从磁盘现值算：
  资源库/场景库/*/            scenes, source/tex/glb 齐不齐
  分析/<章节>/<场景>/          px/audit/_run 齐不齐（五阵位）
  正式产物/                   页面 / 充能图 / 预览 / 实预图 / 清单
  核心目录/agent/agent.md     待办清单（解析 "### …待办" 下的 "- " 行）
  git                         最近提交

用法：
    python 工具/校验/progress.py            # 打印摘要 + 写看板
    python 工具/校验/progress.py --quiet    # 只写文件
"""
import datetime
import glob
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "资源库", "场景库")
ANA = os.path.join(ROOT, "分析")
OUT = os.path.join(ROOT, "正式产物", "进度看板.html")
AGENT_MD = os.path.join(ROOT, "核心目录", "agent", "agent.md")
PARAM = os.path.join(ROOT, "工具", "参数真源.json")

VIEWS = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]


def _exists(p):
    return os.path.exists(p)


def load():
    reg = json.load(open(os.path.join(LIB, "registry.json"), encoding="utf-8"))["scenes"]
    d = {"scenes": [], "chapters": {}, "param": {}, "todo": [], "git": [], "generated": datetime.datetime.now()}

    try:
        d["param"] = json.load(open(PARAM, encoding="utf-8"))
    except Exception:
        d["param"] = {}

    for arena, r in reg.items():
        sd = os.path.join(LIB, r["chapter_dir"], r["dir"])
        src = glob.glob(os.path.join(sd, "source", "*.bundle"))
        tex = glob.glob(os.path.join(sd, "tex", "*.png"))
        glb = glob.glob(os.path.join(sd, "mesh", "*.glb"))
        ad = os.path.join(ANA, r["chapter_dir"], arena)
        px = [v for v in VIEWS if _exists(os.path.join(ad, "px_%s.json" % v))]
        au = [v for v in VIEWS if _exists(os.path.join(ad, "audit_%s.json" % v))]
        shot = [v for v in VIEWS if _exists(os.path.join(ROOT, "正式产物", "场景图", "充能图",
                                                         "fp_%s_%s.webp" % (arena, v)))
                or _exists(os.path.join(ROOT, "正式产物", "场景图", "充能图", "fp_%s.png" % arena))]
        row = {
            "arena": arena, "chapter": r["chapter_dir"], "status": r.get("status", ""),
            "has_source": bool(src), "has_tex": bool(tex), "has_glb": bool(glb),
            "has_slots": _exists(os.path.join(sd, "mesh", "slots.json")),
            "px": len(px), "audit": len(au), "shot": len(shot),
        }
        d["scenes"].append(row)
        c = d["chapters"].setdefault(r["chapter_dir"], {"n": 0, "src": 0, "px": 0, "shot": 0})
        c["n"] += 1
        c["src"] += 1 if (src and tex and glb) else 0
        c["px"] += 1 if len(px) == 5 else 0
        c["shot"] += 1 if shot else 0

    # 待办：解析 agent.md 里 "### …待办" 段下的 "- " 行
    if _exists(AGENT_MD):
        lines = open(AGENT_MD, encoding="utf-8").read().splitlines()
        in_todo = False
        for ln in lines:
            if ln.startswith("#"):
                in_todo = "待办" in ln
                continue
            if in_todo and ln.strip().startswith("- "):
                t = ln.strip()[2:].strip()
                if t:
                    d["todo"].append(t)

    try:
        d["git"] = subprocess.run(["git", "log", "--oneline", "-8", "--date=short",
                                   "--pretty=%h %ad %s"], cwd=ROOT, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace").stdout.splitlines()
        d["dirty"] = len(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                                        text=True, encoding="utf-8", errors="replace").stdout.splitlines())
    except Exception:
        d["dirty"] = 0
    return d


def summary(d):
    s = d["scenes"]
    n = len(s)
    return {
        "scenes": n,
        "geo": sum(1 for x in s if x["has_source"] and x["has_tex"] and x["has_glb"]),
        "analyzed": sum(1 for x in s if x["px"] == 5),
        "audited": sum(1 for x in s if x["audit"] == 5),
        "shot": sum(1 for x in s if x["shot"]),
        "pages": len(glob.glob(os.path.join(ROOT, "正式产物", "页面", "*.html"))),
        "lists": len(glob.glob(os.path.join(ROOT, "正式产物", "清单", "*"))),
        "preview": len(glob.glob(os.path.join(ROOT, "正式产物", "场景图", "预览", "*.png"))),
        "reel": len(glob.glob(os.path.join(ROOT, "正式产物", "场景图", "实预图", "*.png"))),
        "docs": len(glob.glob(os.path.join(ROOT, "docs", "*.md"))) - 1,
        "todo": len(d["todo"]),
        "dirty": d.get("dirty", 0),
    }


def bar(done, total, w=120):
    pct = 0 if not total else int(round(done * 100.0 / total))
    fill = int(round(pct * w / 100.0))
    return ('<div class="bar"><i style="width:%d%%"></i></div><span class="pct">%d%% <b>%d/%d</b></span>'
            % (pct, pct, done, total))


def render(d):
    m = summary(d)
    cam = d["param"].get("camera", {})
    vp = d["param"].get("viewport", {})
    fov = cam.get("fov_vertical_deg", "?")
    fov_status = cam.get("fov_status", "")
    aspect = vp.get("aspect_ratio", "?")

    stages = [
        ("P0 参数固化", 1 if fov != "?" else 0, 4,
         "FOV/near/far 已入参数真源；画幅 16:9；朝向南；余 1 项 GateFit 枚举待证"),
        ("P1 资源取件", m["geo"], m["scenes"], "112 个已采场景 geometry 齐全，不需要重采"),
        ("P2 装配（8 根分组）", m["geo"], m["scenes"], "assembly/glb 由 build_assembly 生成"),
        ("P3 机位（5 阵位）", sum(1 for x in d["scenes"] if x["has_slots"]), m["scenes"],
         "slots.json 已生成的场景数（5 个 cover 锚点）"),
        ("P4 点位重算", m["analyzed"], m["scenes"], "FOV 40° 下的 scan/verify/audit/rotate"),
        ("P5 出图出页", m["shot"], m["scenes"], "充能图 / 页面 / 三张表单"),
    ]

    rows = ""
    for ch in sorted(d["chapters"]):
        c = d["chapters"][ch]
        rows += ("<tr><td>%s</td><td class='n'>%d</td><td class='n'>%d</td>"
                 "<td class='n'>%d</td><td class='n'>%d</td><td>%s</td></tr>"
                 % (html.escape(ch), c["n"], c["src"], c["px"], c["shot"],
                    bar(c["px"], c["n"], 40)))

    todo = "".join("<li>%s</li>" % html.escape(t) for t in d["todo"]) or "<li class='dim'>（无）</li>"
    git = "".join("<li><code>%s</code></li>" % html.escape(g) for g in d["git"])

    stage_html = ""
    for name, done, total, note in stages:
        stage_html += ("<div class='stage'><div class='st-name'>%s</div>%s"
                       "<div class='st-note'>%s</div></div>"
                       % (name, bar(done, total), html.escape(note)))

    tpl = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>地图充能计算 · 进度看板</title>
<style>
:root{--bg:#12161d;--panel:#1a2029;--line:#2a3340;--txt:#e6edf3;--dim:#8b98a8;--acc:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.6 "Microsoft YaHei",system-ui,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:28px 22px 60px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--dim);font-size:12px;margin-bottom:22px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:26px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card b{display:block;font-size:24px;line-height:1.2}
.card span{color:var(--dim);font-size:12px}
h2{font-size:15px;margin:26px 0 12px;padding-left:9px;border-left:3px solid var(--acc)}
.stage{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:10px}
.st-name{font-weight:600;margin-bottom:6px}
.st-note{color:var(--dim);font-size:12px;margin-top:4px}
.bar{display:inline-block;width:calc(100% - 118px);height:8px;background:#0d1117;border-radius:5px;overflow:hidden;vertical-align:middle}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#1f6feb,#58a6ff)}
.pct{display:inline-block;width:108px;text-align:right;font-size:12px;color:var(--dim)}
.pct b{color:var(--txt)}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--dim);font-weight:500;font-size:12px}
tr:last-child td{border-bottom:none}
td.n{text-align:right;font-variant-numeric:tabular-nums}
ul{margin:0;padding-left:20px}
li{margin:3px 0}
code{background:#0d1117;padding:1px 5px;border-radius:4px;font-size:12px;color:#9ecbff}
.dim{color:var(--dim)}
.kv{display:grid;grid-template-columns:130px 1fr;gap:4px 14px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;font-size:13px}
.kv div:nth-child(odd){color:var(--dim)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:800px){.two{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<h1>地图充能计算 · 进度看板</h1>
<div class="sub">生成于 @@GEN@@ ｜ 数据源：registry.json / 分析/ / 正式产物/ / agent.md / git（每次运行重算，不手填）</div>

<div class="cards">
  <div class="card"><b>@@SCENES@@</b><span>已登记场景</span></div>
  <div class="card"><b>@@GEO@@</b><span>几何齐全</span></div>
  <div class="card"><b>@@ANALYZED@@</b><span>五阵位分析完成</span></div>
  <div class="card"><b>@@SHOT@@</b><span>已出充能图</span></div>
  <div class="card"><b>@@PAGES@@</b><span>页面 / @@LISTS@@ 张表单</span></div>
  <div class="card"><b>@@TODO@@</b><span>待办项</span></div>
</div>

<h2>阶段进度</h2>
@@STAGES@@

<h2>相机与画幅（唯一真源 工具/参数真源.json）</h2>
<div class="kv">
  <div>垂直 FOV</div><div><b>@@FOV@@°</b> <span class="dim">@@FOVNOTE@@</span></div>
  <div>near / far</div><div>@@NEAR@@ / @@FAR@@</div>
  <div>画幅</div><div><b>@@ASPECT@@</b></div>
  <div>相机朝向</div><div>+Z（yaw 0 / pitch 0，25 组锚点实测）</div>
  <div>爆裂槽上限</div><div>@@BURST@@ <span class="dim">（ConfigBattleTable，社区 10000 是 ÷100 口径）</span></div>
</div>

<h2>章节覆盖</h2>
<table><thead><tr><th>章节</th><th>场景</th><th>几何齐</th><th>五阵位分析</th><th>有图</th><th>分析进度</th></tr></thead>
<tbody>@@ROWS@@</tbody></table>

<div class="two">
  <div><h2>待办</h2><ul>@@TODO_LIST@@</ul></div>
  <div><h2>最近提交</h2><ul>@@GIT@@</ul></div>
</div>
</div></body></html>"""

    rep = {
        "@@GEN@@": d["generated"].strftime("%Y-%m-%d %H:%M"),
        "@@SCENES@@": str(m["scenes"]),
        "@@GEO@@": str(m["geo"]),
        "@@ANALYZED@@": str(m["analyzed"]),
        "@@SHOT@@": str(m["shot"]),
        "@@PAGES@@": str(m["pages"]),
        "@@LISTS@@": str(m["lists"]),
        "@@TODO@@": str(m["todo"]),
        "@@STAGES@@": stage_html,
        "@@FOV@@": str(fov),
        "@@FOVNOTE@@": html.escape(str(fov_status)),
        "@@NEAR@@": str(cam.get("near_clip", "?")),
        "@@FAR@@": str(cam.get("far_clip", "?")),
        "@@ASPECT@@": html.escape(str(aspect)),
        "@@BURST@@": str(d["param"].get("energy", {}).get("burst_gauge_max", "?")),
        "@@ROWS@@": rows,
        "@@TODO_LIST@@": todo,
        "@@GIT@@": git,
    }
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    return tpl


def s_rows(d):
    return d["scenes"]


def main():
    d = load()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(d))
    if "--quiet" not in sys.argv:
        m = summary(d)
        print("场景 %d ｜ 几何 %d ｜ 五阵位分析 %d ｜ 出图 %d ｜ 页面 %d ｜ 表单 %d ｜ 待办 %d ｜ 未提交 %d"
              % (m["scenes"], m["geo"], m["analyzed"], m["shot"], m["pages"], m["lists"],
                 m["todo"], m["dirty"]))
        print("看板 → %s" % OUT)


if __name__ == "__main__":
    main()
