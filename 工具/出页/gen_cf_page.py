# -*- coding: utf-8 -*-
"""生成《第 34 章 · 玩家视角充能点》汇总页。

与 35 章沼泽丛林页的区别
------------------------
34 章这批场景（sbg_cityforestundercrystal_001~005）出现一个明显反常：
「段数最高的点」和「真能打中的点」几乎不重合 —— 8 段点的容错锥只有 0.7~1.2px。
所以本页把两套排序并列：段数榜（几何最优）与实战榜（锥宽 × 可信度），
并在每个战场头部分别报出两个冠军。

复用：conf_cell / rot_line 来自 gen_fp_page；审计节来自 audit_html；
样式表直接从已生成的沼泽丛林页面里读，保证两个页面同源、不漂移。
"""
import json, os, re, sys, html

import gen_fp_page as G
import audit_html

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(ROOT)) + "/工具")
from paths import PATH                                     # noqa: E402
ARENAS = ["c001", "c002", "c003", "c004", "c005"]
LABEL = {a: a[1:] for a in ARENAS}          # c001 -> 001
REGION = "cityforestundercrystal"
SWAMP_PAGE = PATH.page("H35沼泽丛林玩家视角充能点.html")


def esc(s):
    return html.escape(str(s))


def short(name):
    return (name or "").replace("sbg_" + REGION + "_", "").replace("sbg_", "")


def load():
    out = {}
    for a in ARENAS:
        p = PATH.px(a)
        if os.path.exists(p):
            out[a] = json.load(open(p, encoding="utf-8"))
    return out


def load_audit():
    out = {}
    for a in ARENAS:
        p = PATH.audit(a)
        if os.path.exists(p):
            out[a] = {r["no"]: r for r in json.load(open(p, encoding="utf-8"))["rows"]}
    return out


def css():
    """直接复用沼泽丛林页的样式表 —— 两个页面同源。"""
    if not os.path.exists(SWAMP_PAGE):
        raise SystemExit("先运行 gen_fp_page.py 生成沼泽丛林页（本页复用它的样式表）")
    s = open(SWAMP_PAGE, encoding="utf-8").read()
    m = re.search(r"<style>(.*?)</style>", s, re.S)
    if not m:
        raise SystemExit("沼泽丛林页里没找到 <style>")
    return m.group(1)


def swamp_min_pool():
    """第 35 章沼泽丛林五图里最低的池子占比（%），现算，不写死。"""
    vals = []
    for a in ("001", "002", "003", "004", "005"):
        p = PATH.px(a)
        if not os.path.exists(p):
            continue
        fs = ((json.load(open(p, encoding="utf-8")).get("verify") or {})
              .get("field_sim") or {})
        if fs.get("pool_pct"):
            vals.append(fs["pool_pct"])
    return min(vals) if vals else 0.0


def _swamp_px():
    out = []
    for a in ("001", "002", "003", "004", "005"):
        p = PATH.px(a)
        if os.path.exists(p):
            out.append(json.load(open(p, encoding="utf-8")))
    return out


def swamp_d_pct():
    """第 35 章沼泽丛林五图的 D 级占比（%），可信度口径。"""
    d = n = 0
    for j in _swamp_px():
        s = (j.get("verify") or {}).get("summary") or {}
        d += s.get("D", 0)
        n += sum(s.get(k, 0) for k in "ABCD")
    return 100.0 * d / n if n else 0.0


def swamp_cover_range():
    """第 35 章沼泽丛林五图的掩体占画面比例（%），返回 (min, max)。"""
    vals = []
    for j in _swamp_px():
        cs = j.get("cover_stat") or {}
        if cs.get("cover_px"):
            vals.append(100.0 * cs["cover_px"] / (1600 * 900))
    return (min(vals), max(vals)) if vals else (0.0, 0.0)


def cone(r):
    return r.get("cone_px") or 0.0


def swamp_median_cone():
    """第 35 章沼泽丛林的锥宽中位数（现算，避免把旧几何的数字写死在文案里）。"""
    vals = []
    for a in ("001", "002", "003", "004", "005"):
        p = PATH.audit(a)
        if not os.path.exists(p):
            continue
        rows = json.load(open(p, encoding="utf-8")).get("rows") or []
        vals += [r["cone_px"] for r in rows if r.get("cone_px")]
    if not vals:
        return 0.0
    vals.sort()
    return vals[len(vals) // 2]


def best_stable(px, au):
    """段数冠军：稳态段数优先，同段数看锥宽。"""
    return max(px["points"], key=lambda p: (p["n_steady"], cone(au.get(p["no"]) or {})))


def best_usable(px, au):
    """实战冠军：段数 ≥3 且锥宽最大；没有 3 段就退到 2 段里最宽的。"""
    for thr in (3, 2):
        cand = [p for p in px["points"] if p["n_steady"] >= thr]
        if cand:
            return max(cand, key=lambda p: (cone(au.get(p["no"]) or {}), p.get("conf", 0)))
    return px["points"][0]


def block(a, d, au):
    """单个战场：机位图 + 点位表 + 逐件明细 + 轮换行。"""
    pts = d["points"]
    au = au or {}
    st = best_stable(d, au)
    us = best_usable(d, au)
    lab = LABEL[a]

    rows = []
    for p in pts:
        m = p["mix"]
        ps = p.get("per_slot_steady") or p["per_slot"]
        per = "".join(
            ('<td class="c zero" title="该阵位被掩体挡住，打不出去">0</td>'
             if ps.get("cover_%d" % i, 0) == 0 else
             '<td class="c%s">%d</td>'
             % (" hot" if ps.get("cover_%d" % i, 0) >= 5 else "", ps.get("cover_%d" % i, 0)))
            for i in range(1, 6))
        tags = "".join('<i class="ft %s">%s</i>' % (G.FT.get(t, ""), esc(t))
                       for t in p.get("tags", [])) or '<i class="ft">—</i>'
        r = au.get(p["no"]) or {}
        cy, cp = r.get("cone_yaw_px"), r.get("cone_pitch_px")
        if cy is None:
            cone_td = '<td class="d">—</td>'
        else:
            cone_td = ('<td class="cone %s"><b>%.1f</b><s>%.1f</s></td>'
                       % ("narrow" if min(cy, cp) < 2.5 else "", cy, cp))
        rows.append(
            '<tr class="%s" data-no="%d"><td class="no"><b>%d</b></td>'
            '<td class="seg">%d</td><td class="seg2">%d</td>'
            '<td class="pct">%.1f%%</td><td class="pct2">%.1f%%</td>'
            '<td class="mix"><i class="s">%d</i><i class="m">%d</i><i class="h">%d</i></td>'
            '<td class="d">%.0fm</td>%s<td class="cf">%s</td>'
            '<td class="d">%d</td><td class="tags">%s</td>%s</tr>'
            % ("minor" if p["no"] > 5 else "", p["no"], p["no"], p["n_steady"], p["n"],
               p["steady_pct"], p["pct"],
               m["soft"], m["medium"], m["hard"], p["first"],
               cone_td, G.conf_cell(p), p["total"], tags, per))

    detail = []
    for p in pts:
        lis = "".join(
            '<li><span class="tag %s">%s</span>%s<i>%dm</i></li>'
            % (h["grp"], h["grp"][0].upper(), esc(short(h["name"])), h["d"])
            for h in p["detail"])
        detail.append('<div class="dt" data-no="%d"><div class="dth">%d 号 · 首轮 %d 段 / 稳态 %d 段 · '
                      '共 %d 件（软 %d / 中 %d / 硬 %d）</div><ol>%s</ol></div>'
                      % (p["no"], p["no"], p["n"], p["n_steady"], len(p["detail"]),
                         p["mix"]["soft"], p["mix"]["medium"], p["mix"]["hard"], lis))

    return """
<section class="ar" id="s{a}">
  <div class="ah">
    <h3>战场 <span>{lab}</span> <code>sbg_{reg}_{lab}</code></h3>
    <div class="badge">段数冠军 <b>{stn}</b> 段 · 锥 <b>{stc}</b>px ｜ 实战冠军 <b>{usn}</b> 段 · 锥 <b>{usc}</b>px</div>
    <a class="live" title="需先运行启动战场查看器（本地服务 8899）" href="http://127.0.0.1:8899/viewer/fp.html?arena={a}" target="_blank">玩家视角三维视图 ↗</a>
    <a class="live" title="自由拖动视角，看整张战场的原生装配" href="http://127.0.0.1:8899/viewer/index.html?arena={a}" target="_blank">自由查看 ↗</a>
  </div>
  <figure>
    <a href="../场景图/fp_{a}.png" target="_blank"><img src="../场景图/fp_{a}.png" alt="战场 {lab} 玩家视角"></a>
    <figcaption>机位 cover_3 的 <code>camera_position</code> = ({cx}, 0.00, {cz}) ·
      视高 2.34m（地面 y = −2.34）· 沿 +z · 竖直 FOV 60° ·
      相机与枪口视差 中位 {pxm}° / 最大 {pxx}°（近景必须按像素反推，不能直接扫枪口角度）</figcaption>
  </figure>
  <table class="tg">
    <thead><tr>
      <th>号</th><th>稳态<br>段数</th><th>首轮<br>段数</th><th>稳态<br>%/轮</th><th>首轮<br>%/轮</th>
      <th>软/中/硬</th><th>首击</th><th>容错 px<br>横/纵</th><th>可信度</th><th>聚焦<br>段数</th><th>特性</th>
      <th>c1</th><th>c2</th><th>c3</th><th>c4</th><th>c5</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {rot}
  <p class="cn"><b>稳态</b> = 软质目标碎掉后仍能穿透的段数（中 + 硬），决定持续充能；
    <b>首轮</b> = 全目标完好时的段数。<b>容错 横/纵</b> = 准星偏离这颗像素多少还能保住标称段数
    （四方向取最小，绕开相机独立测；<b>红色表示纵向 &lt;2.5px，基本稳不住</b>）。<br>
    <b>可信度</b> = 300 次随机扰动下的达标率/可用率/P10 合成分（A≥80 B≥68 C≥52 D&lt;52）。
    <b>c1~c5</b> = 五个阵位各自的单发段数，<b>红色的 0 = 该阵位被自家或相邻高掩体挡住</b>。<br>
    <b>①~⑤ 首选</b>，<b>⑥ 起为补充</b>：换了站位、被挡住、或要描远处目标时顶上；
    页面顶部切换条决定显示几个。</p>
  <details><summary>展开 {np} 个点的逐件命中明细（含耐久档）</summary>{detail}</details>
</section>""".format(
        a=a, lab=lab, reg=REGION,
        stn=st["n_steady"], stc=("%.1f" % cone(au.get(st["no"]) or {})),
        usn=us["n_steady"], usc=("%.1f" % cone(au.get(us["no"]) or {})),
        cx=("%.1f" % d["cam"][0]), cz=("%.1f" % d["cam"][2]),
        pxm=("%.1f" % d["parallax"]["median"]), pxx=("%.1f" % d["parallax"]["max"]),
        rows="".join(rows), detail="".join(detail), rot=G.rot_line(d), np=len(pts))


def duel_table(data, AUDIT):
    """段数榜 vs 实战榜：五张战场横向对比。"""
    rows = []
    for a in ARENAS:
        d, au = data[a], AUDIT.get(a) or {}
        st, us = best_stable(d, au), best_usable(d, au)
        sr, ur = au.get(st["no"]) or {}, au.get(us["no"]) or {}
        gap = st["n_steady"] - us["n_steady"]
        rows.append(
            '<tr><td class="no"><b>%s</b></td>'
            '<td class="hl">%d 号 <s>%d 段 · 锥 %.1fpx · %s</s></td>'
            '<td class="hl %s">%d 号 <s>%d 段 · 锥 %.1fpx · %s · conf %.0f</s></td>'
            '<td class="d">%s</td></tr>'
            % (LABEL[a],
               st["no"], st["n_steady"], cone(sr), sr.get("grade", "-"),
               "warn" if gap >= 2 else "",
               us["no"], us["n_steady"], cone(ur), ur.get("grade", "-"), us.get("conf", 0),
               ("差 %d 段" % gap) if gap > 0 else "一致"))
    return ('<table class="tb rt"><thead><tr><th>战场</th>'
            '<th>段数冠军<br><i>审计等级</i></th>'
            '<th>实战冠军（≥3 段里锥最宽）<br><i>审计等级 / 可信度</i></th>'
            '<th>两者差</th></tr></thead>'
            '<tbody>%s</tbody></table>'
            '<p class="cn">两套等级别混：这里的<b>审计等级</b>（S/A/B/C/D）只看几何容错与阵位可用；'
            '下面点位表里的<b>可信度</b>（A/B/C/D + 分数）来自 300 次随机扰动，看的是「抖一抖还活不活」。'
            '两者经常不一致 —— 锥窄但抖动小的点会「审计 D、可信度 A」。</p>' % "".join(rows))


def restore_table(data, AUDIT):
    """场景还原体检：每张图的几何规模与遮挡情况。"""
    rows = []
    for a in ARENAS:
        d = data[a]
        cs = d["cover_stat"]
        au = AUDIT.get(a) or {}
        blocked = sum(1 for r in au.values()
                      if any(str(x).startswith("挡:") for x in (r.get("warn") or [])))
        covpct = 100.0 * cs["cover_px"] / (1600 * 900)
        pspan = d["scan"]["pitch"][1] - d["scan"]["pitch"][0]
        rows.append(
            '<tr><td class="no"><b>%s</b></td><td class="d">%d</td><td class="hl">%d</td>'
            '<td class="d">%d</td><td class="d">%d 件 / %.0f%%</td>'
            '<td class="d">%.0f</td><td class="d">%.1f</td><td class="d">%.1f</td>'
            '<td class="d">%d</td></tr>'
            % (LABEL[a], d["n_tri"], d["n_hitbox_obj"], d["n_block_tri"],
               cs["n"], covpct, pspan, d["parallax"]["median"], d["parallax"]["max"],
               blocked))
    return ('<table class="tb rt"><thead><tr><th>战场</th><th>三角面</th><th>受击体</th>'
            '<th>遮挡三角</th><th>掩体 件/占画面</th><th>纵向扫描 °</th>'
            '<th>视差 中位°</th><th>视差 最大°</th><th>被挡点数</th></tr></thead>'
            '<tbody>%s</tbody></table>' % "".join(rows))


def main():
    data = load()
    AUDIT = load_audit()
    if len(data) != len(ARENAS):
        raise SystemExit("缺 px_*.json：%s" % [a for a in ARENAS if a not in data])

    # ---------- 统计 ----------
    allp = []
    for a in ARENAS:
        au = AUDIT.get(a) or {}
        for p in data[a]["points"]:
            allp.append((a, p, au.get(p["no"]) or {}))
    n_pt = len(allp)
    cone_list = sorted(cone(r) for _, _, r in allp)
    med_cone = cone_list[len(cone_list) // 2]
    narrow = sum(1 for c in cone_list if c < 2)
    swamp_cone = swamp_median_cone()
    hi = [x for x in allp if x[1]["n_steady"] >= 5]
    hi_narrow = sum(1 for x in hi if cone(x[2]) < 3)
    wide = [x for x in allp if cone(x[2]) >= 8]
    wide_seg = [x[1]["n_steady"] for x in wide]
    gcnt = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
    for _, _, r in allp:
        gcnt[r.get("grade", "D")] = gcnt.get(r.get("grade", "D"), 0) + 1
    ccnt = {"A": 0, "B": 0, "C": 0, "D": 0}
    for a in ARENAS:
        for g, v in (data[a]["verify"]["summary"] or {}).items():
            ccnt[g] = ccnt.get(g, 0) + v
    pool = [data[a]["verify"]["field_sim"]["pool_pct"] for a in ARENAS]
    shots = [data[a]["verify"]["field_sim"]["A"]["shots"] for a in ARENAS]
    pitch_bad = sum(1 for _, _, r in allp if (r.get("pitch_keep") or 0) < 0.6)
    blk = {"cover_2": 0, "cover_4": 0, "both": 0}
    for _, _, r in allp:
        w = [str(x) for x in (r.get("warn") or []) if str(x).startswith("挡:")]
        for s in w:
            if "cover_2,cover_4" in s or "cover_4,cover_2" in s:
                blk["both"] += 1
            elif "cover_2" in s:
                blk["cover_2"] += 1
            elif "cover_4" in s:
                blk["cover_4"] += 1

    st_top = max(allp, key=lambda x: x[1]["n_steady"])
    us_top = max((x for x in allp if x[1]["n_steady"] >= 3),
                 key=lambda x: (cone(x[2]), x[1].get("conf", 0)))

    # ---------- 对比表 ----------
    duel = duel_table(data, AUDIT)
    restore = restore_table(data, AUDIT)
    body = "\n".join(block(a, data[a], AUDIT.get(a)) for a in ARENAS)

    # ---------- 可信度表 ----------
    cf_rows, tot = [], {"A": 0, "B": 0, "C": 0, "D": 0}
    for a in ARENAS:
        d = data[a]
        sm = d["verify"]["summary"]
        for g in tot:
            tot[g] += sm.get(g, 0)
        n_all = max(1, sum(sm.values()))
        seg = "".join('<i class="g%s" style="width:%.1f%%"></i>'
                      % (g, 100.0 * sm.get(g, 0) / n_all) for g in ("A", "B", "C", "D"))
        top = max(d["points"], key=lambda x: x.get("conf", 0))
        cf_rows.append(
            '<tr><td class="no"><b>%s</b></td><td class="cf">%s</td>'
            '<td class="cf"><b>%d%%</b></td>'
            '<td class="cf" style="min-width:96px"><div class="cfbar">%s</div>'
            '<s>A%d B%d C%d D%d</s></td>'
            '<td class="cf">%d 号 <b>%.0f</b><s>%s</s></td></tr>'
            % (LABEL[a], G.conf_cell(d["points"][0]),
               round(d["points"][0]["sim"]["follow"]["hit_rate"] * 100), seg,
               sm.get("A", 0), sm.get("B", 0), sm.get("C", 0), sm.get("D", 0),
               top["no"], top.get("conf", 0), top.get("grade", "-")))
    n_all = max(1, sum(tot.values()))
    cf_sum = ('<tr style="border-top:2px solid var(--bd2)"><td class="no"><b>合计</b></td>'
              '<td class="cf">—</td><td class="cf">—</td>'
              '<td class="cf"><div class="cfbar">%s</div><s>A%d B%d C%d D%d</s></td>'
              '<td class="cf">—</td></tr>'
              % ("".join('<i class="g%s" style="width:%.1f%%"></i>'
                         % (g, 100.0 * tot[g] / n_all) for g in ("A", "B", "C", "D")),
                 tot["A"], tot["B"], tot["C"], tot["D"]))
    cf_table = ('<table class="tb"><thead><tr><th>战场</th><th>① 可信度</th>'
                '<th>① 达标率</th><th>等级分布</th><th>本图最稳的点</th></tr></thead>'
                '<tbody>%s%s</tbody></table>' % ("".join(cf_rows), cf_sum))

    # ---------- 轮换表 ----------
    rt = []
    for a in ARENAS:
        d = data[a]
        fs = d["verify"]["field_sim"]
        tot_obj = d.get("n_hitbox_obj") or 1
        A, B = fs["A"], fs["B"]
        gA = fs.get("gain_A", 0)
        order = (A.get("order_greedy") or [])[:9]
        rt.append(
            '<tr><td class="no"><b>%s</b></td><td class="d">%d</td><td class="hl">%d</td>'
            '<td class="hl %s">%.0f%%<s>%d / %d 件</s></td>'
            '<td class="d">%d 发</td><td class="d">%d 发%s</td><td class="d">%s</td></tr>'
            % (LABEL[a], fs["n_points"], fs["pool"],
               "warn" if fs["pool_pct"] < 100 else "", fs["pool_pct"], fs["pool"], tot_obj,
               A["shots"], B["shots"],
               '<s style="font-size:10px;color:var(--tx3)"> / %d 点</s>' % B["pts"],
               ("-%d 发" % gA) if gA > 0 else "—"))
    rot_table = ('<table class="tb rt"><thead><tr><th>战场</th><th>点位</th><th>池子<br>件数</th>'
                 '<th>池子<br>=充能</th><th>A 一枪碎</th><th>B 上限 30</th>'
                 '<th>贪心<br>省</th></tr></thead><tbody>%s</tbody></table>'
                 '<p class="cn" style="text-align:center;font-size:11px">'
                 'A 模式每个点只能用 1 发（发数 = 点数）；B 模式单点能撑 34 发。贪心省 = 只换顺序能少打几发。</p>'
                 % "".join(rt))

    ABODY, ACSS, _st = audit_html.build([(a, "34 章 %s" % LABEL[a]) for a in ARENAS])

    page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>第 34 章 晶化城市森林 · 玩家视角充能点</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="kicker">NIKKE · 第 34 章 {REGION} · 拆包实测</div>
  <h1>关卡场景还原 · 每个战场 <span>最合适的充能点</span></h1>
  <p class="lead">五张战场全部从客户端 <code>sbg_cityforestundercrystal_001~005</code> 原生还原：
    顶点、三角索引、父链 TRS、掩体锚点都取自拆包数据，不是手绘示意。机位取 <code>cover_3.camera_position</code>
    （角色身后 4.5m、视高 2.34m、沿 +z、FOV 60°），图里 ①~⑤ 是屏幕上能直接压的位置。<br>
    <b>这一章有个反常</b>：段数最高的点（8 段）容错锥只有 0.7~1.2px，实战基本压不住；
    锥宽 ≥8px 的点段数全是 2~4。所以本页把「段数榜」和「实战榜」并列给出。</p>
  <div class="kv">
    <div>全场最强单点<b>{STN}<i>段稳态 · {STC}px 锥</i></b></div>
    <div>实战首选<b>{USN}<i>段 · {USC}px 锥 · {USL}</i></b></div>
    <div>点位总数<b>{NPT}<i>个 / 5 张图（默认显示 5）</i></b></div>
    <div>可破坏物池<b>{POOL0}~{POOL1}<i>% 爆裂条</i></b></div>
    <div>A 模式充满<b>{SH0}~{SH1}<i>发（走位轮换）</i></b></div>
  </div>
</header>

<div class="nbar">
  <em>每个战场显示</em>
  <button data-n="5" class="on">5 个</button>
  <button data-n="8">8 个</button>
  <button data-n="12">12 个</button>
  <button data-n="24">全部</button>
  <span class="sep"></span>
  <em>我的掩体</em>
  <button class="slot on" data-s="0">不限</button>
  <button class="slot" data-s="1">1</button>
  <button class="slot" data-s="2">2</button>
  <button class="slot" data-s="3">3</button>
  <button class="slot" data-s="4">4</button>
  <button class="slot" data-s="5">5</button>
  <span class="hint">编号 ①~⑤ 为首选，其后为补充点 · 快捷键 1 / 2 / 3 / 4</span>
</div>

<h2>先看这个：段数榜和实战榜不是一回事</h2>
<p class="body">同一张图上，「单发穿透最多」和「真能稳定打中」在这批场景里几乎互斥。
    原因在几何：34 章的受击体常常排成一条延伸到 45~55m 的细长队列，只要射线与这排物件共线，
    一发能穿 7~8 件；可这条「共线走廊」在屏幕上只有 1~2 像素宽，纵向更窄 ——
    <b>段数是纸面最优，锥宽才决定能不能落上去</b>。</p>
{DUEL}
<div class="note">
  <b>三条硬数据</b>
  <ul>
    <li><b>段数 ≥5 的 {NHI} 个点里，{NHIN} 个锥宽 &lt;3px</b>（占 {NHIP}%）。
      它们不是「算错了」，是「对准了能打到、但你压不准」。</li>
    <li><b>锥宽 ≥8px 的 {NWIDE} 个点，段数全在 {WMIN}~{WMAX} 段</b>。
      想要高段数就得牺牲容错，想要容错就只能接受 3~4 段。</li>
    <li><b>全场 {NPT} 个点的锥宽中位数只有 {MEDC}px</b>，其中 {NARROW} 个不到 2px。
      对比 35 章沼泽丛林的 {SWAMPCONE}px —— 34 章整体的「可操作性」低一档，这是场景几何决定的，不是算法差异。</li>
  </ul>
</div>

<h2>场景是怎么还原的</h2>
<p class="body">链路与 35 章（沼泽丛林）一致，数据源换成 <code>spotbackground(hd)_assets_sbg_cityforestundercrystal_00N</code>：</p>
<div class="note">
  <ul>
    <li><code>core_catalog.sqlite</code> 查 file_id → <code>store.cdb.idx</code> 取偏移 →
      adb <code>dd</code> 定点读 → zstd 解压 → 按 file_offset 拼 UnityFS bundle。</li>
    <li>UnityPy 解析：Mesh 顶点（ch0 float32x3）+ uint16 三角索引 + Transform 父链合成世界矩阵，
      <b>0.5 厚的双面平板只取正面</b>；Sprite 走 billboard 规则还原朝向。</li>
    <li>按 <code>SpotSingleMap</code> 的分组树归类：<code>soft/medium/hard</code> 是可充能受击体，
      <code>static_object/ground</code> 只挡弹，<code>cover_object</code> 是我方掩体（不作判定点）。</li>
    <li>五个阵位取 <code>cover_1~cover_5</code> 的世界变换，相机取各自的 <code>camera_position</code>。</li>
  </ul>
</div>
{restore}
<p class="cn">「被挡点数」= 那个点在五个阵位里至少有一个被自家/相邻掩体遮断（0.4~4m 处截断）的点数。
  这五张图的掩体占画面 {COVP0}~{COVP1}%，和 35 章的 {SWCOV0}~{SWCOV1}% 是同一量级，换阵位失效依旧是主要坑。</p>

{body}

<h2>可信度：300 次随机扰动</h2>
<p class="body">每个点重打 300 次：站位 ±0.30m、枪口高度 ±0.15m、手抖 ±2~4px、后坐 0.12°、几何 1.5px，
    每次走完整链路（准星 → 相机射线 → 命中点 → 枪口瞄准 → 穿透计数 → 遮挡截断），看还剩几段。
    评分 <code>100 × (0.60·达标率 + 0.25·可用率 + 0.15·P10/标称)</code>，
    A≥80 / B≥68 / C≥52 / D&lt;52。相机俯仰、朝向、FOV 不进评分（它们错会让整张图一起偏，属于工具级失效）。</p>
{CF}
<div class="note">
  <b>结论</b>
  <ul>
    <li><b>{NPT} 个点里 A {CA} 个 / B {CB} 个 / C {CC} 个 / D {CD} 个</b>，D 占 {CDP}%。
      35 章沼泽同口径 D 占 {SWDP}% —— 两章的差别主要来自阵位遮挡与俯角敏感，不能只看锥宽。</li>
    <li><b>俯角敏感 {PBAD} 个点</b>：相机俯角一偏就掉段。这批点多是打在 40m 外的细长物件上，
      俯角 ±2° 对应屏幕纵向 ≈30px，足够换一个目标。</li>
    <li><b>阵位遮挡</b>：被 cover_2 挡 {B2} 次、cover_4 挡 {B4} 次、两者都挡 {BB} 次。
      站到对侧掩体后，这些点在 0.4~4m 处就被自家掩体截断，段数直接归零（表里显示为红色 0）。</li>
  </ul>
</div>

<h2>轮换：池子够不够充满</h2>
<p class="body">受击物碎掉即从场景消失，且跨点位共享 —— 单点再强也只贡献一次。所以要看「可破坏物池」：
    池 × 2.8% 就是这张图靠打地形能拿到的上限。两种假设都给：
    <b>A 一枪碎</b>（<code>hpdamage_limit</code> 不生效，每点 1 发）、
    <b>B 上限 30</b>（soft 4 / medium 17 / hard 34 发才碎）。</p>
{ROT}
<div class="note">
  <b>这一章和 35 章（沼泽丛林）最大的不同</b>
  <ul>
    <li><b>池子全部够用</b>：{POOL0}%~{POOL1}%，五张图都能靠自己充满一条爆裂条。
      35 章沼泽丛林有一张只有 {SWAMPMINPOOL}%，只能靠打敌人补 —— 34 章没有这个问题。</li>
    <li><b>A 模式下需要走 {SH0}~{SH1} 个点</b>，点位给到 24 个，够轮换；
      B 模式下 1 个点打到底就够（单点上限 34 发 ≈ 95% 爆裂条）。</li>
    <li><b>所以 34 章的瓶颈不是「充能不够」，是「按住不放也打不中」</b> ——
      回到第一节：优先挑锥宽大的点，别追 8 段。</li>
  </ul>
</div>

{AUDIT}

<h2>怎么用</h2>
<p class="body">1) 先确认自己在哪个战场：五个场景外观差别很大（001 废墟立交、002 湖面残骸、003 晶体密林、
    004 断桥、005 开阔滩地），进关卡看一眼背景即可对上 —— <b>关卡 → 场景的对应关系不在客户端</b>，
    <code>spot_id</code> 由服务端下发，客户端资源里没有这张表，所以按战场给而不是按 35-x 给。<br>
    2) 选定战场后，先看<b>实战冠军</b>那一个点：锥宽最大、可信度最高。<br>
    3) 站位和被挡：用顶部「我的掩体」筛 —— 选 1~5 会按该阵位的段数重排，打不到的行整行划掉。<br>
    4) 需要更高段数再往表里挑，但注意容错列：纵向红色的基本只能当参考。</p>

<footer>
  数据：安卓国际服 <code>com.shiftup.patch/core/chunk/store.cdb</code> 定点提取 ·
  第 34 章 <code>sbg_cityforestundercrystal_001~005</code>（<code>fcbg_cityforestcrystal_007</code>）<br>
  脚本：<code>scan_px.py</code>（像素级选点）· <code>verify_px.py</code>（300 次可信度）·
  <code>audit_px.py</code>（六项独立审计）· <code>sim_charge.py</code>（轮换）·
  <code>gen_cf_page.py</code>（本页）<br>
  三维视图需先双击「启动战场查看器」起本地服务（8899）。
</footer>
</div>

<script>
(function () {
  var btns = [].slice.call(document.querySelectorAll('.nbar button[data-n]'));
  var cur = 5;
  function apply(n) {
    cur = n;
    [].forEach.call(document.querySelectorAll('[data-no]'), function (el) {
      el.style.display = (+el.dataset.no <= n) ? '' : 'none';
    });
    btns.forEach(function (b) { b.classList.toggle('on', +b.dataset.n === n); });
  }
  btns.forEach(function (b) { b.addEventListener('click', function () { apply(+b.dataset.n); }); });
  window.addEventListener('keydown', function (e) {
    var i = { '1': 0, '2': 1, '3': 2, '4': 3 }[e.key];
    if (i !== undefined && btns[i]) btns[i].click();
  });
  apply(cur);

  var sbtns = [].slice.call(document.querySelectorAll('.nbar button.slot'));
  function segOf(tr, k) {
    var cs = tr.querySelectorAll('td.c');
    if (!cs.length) return -1;
    var t = (cs[k - 1] || {}).textContent || '';
    return t.trim() === '' ? -1 : (+t || 0);
  }
  function pick(k) {
    sbtns.forEach(function (b) { b.classList.toggle('on', +b.dataset.s === k); });
    [].forEach.call(document.querySelectorAll('tbody'), function (tb) {
      var rows = [].slice.call(tb.children).filter(function (r) {
        return r.querySelector('td.c');
      });
      if (!rows.length) return;
      rows.forEach(function (r, i) { if (r._oi === undefined) r._oi = i; });
      rows.forEach(function (tr) {
        [].forEach.call(tr.querySelectorAll('td.c'), function (c, i) {
          c.classList.toggle('sel', k > 0 && i === k - 1);
        });
        tr.classList.remove('dim', 'dead');
        if (k > 0) {
          var v = segOf(tr, k);
          if (v === 0) tr.classList.add('dim', 'dead');
          else if (v > 0 && v < 2) tr.classList.add('dim');
        }
      });
      if (k > 0) {
        rows.sort(function (a, b) {
          var va = segOf(a, k), vb = segOf(b, k);
          if (va !== vb) return vb - va;
          return a._oi - b._oi;
        });
      } else {
        rows.sort(function (a, b) { return a._oi - b._oi; });
      }
      rows.forEach(function (r) { tb.appendChild(r); });
    });
  }
  sbtns.forEach(function (b) {
    b.addEventListener('click', function () { pick(+b.dataset.s); });
  });
})();
</script>
</body>
</html>"""

    page = (page.replace("__CSS__", css())
            .replace("{REGION}", REGION)
            .replace("{STN}", str(st_top[1]["n_steady"]))
            .replace("{STC}", "%.1f" % cone(st_top[2]))
            .replace("{USN}", str(us_top[1]["n_steady"]))
            .replace("{USC}", "%.1f" % cone(us_top[2]))
            .replace("{USL}", "%s-%s" % (LABEL[us_top[0]], us_top[1]["no"]))
            .replace("{NPT}", str(n_pt))
            .replace("{POOL0}", "%.0f" % min(pool)).replace("{POOL1}", "%.0f" % max(pool))
            .replace("{SH0}", str(min(shots))).replace("{SH1}", str(max(shots)))
            .replace("{DUEL}", duel)
            .replace("{NHI}", str(len(hi))).replace("{NHIN}", str(hi_narrow))
            .replace("{NHIP}", "%.0f" % (100.0 * hi_narrow / max(1, len(hi))))
            .replace("{NWIDE}", str(len(wide)))
            .replace("{WMIN}", str(min(wide_seg) if wide_seg else 0))
            .replace("{WMAX}", str(max(wide_seg) if wide_seg else 0))
            .replace("{MEDC}", "%.1f" % med_cone).replace("{NARROW}", str(narrow))
            .replace("{SWAMPCONE}", "%.1f" % swamp_cone)
            .replace("{SWAMPMINPOOL}", "%.0f" % swamp_min_pool())
            .replace("{SWDP}", "%.0f" % swamp_d_pct())
            .replace("{SWCOV0}", "%.0f" % swamp_cover_range()[0])
            .replace("{SWCOV1}", "%.0f" % swamp_cover_range()[1])
            .replace("{restore}", restore)
            .replace("{COVP0}", "%.0f" % min(100.0 * data[a]["cover_stat"]["cover_px"] / (1600 * 900)
                                             for a in ARENAS))
            .replace("{COVP1}", "%.0f" % max(100.0 * data[a]["cover_stat"]["cover_px"] / (1600 * 900)
                                             for a in ARENAS))
            .replace("{body}", body)
            .replace("{CF}", cf_table)
            .replace("{CA}", str(ccnt["A"])).replace("{CB}", str(ccnt["B"]))
            .replace("{CC}", str(ccnt["C"])).replace("{CD}", str(ccnt["D"]))
            .replace("{CDP}", "%.0f" % (100.0 * ccnt["D"] / max(1, n_pt)))
            .replace("{PBAD}", str(pitch_bad))
            .replace("{B2}", str(blk["cover_2"])).replace("{B4}", str(blk["cover_4"]))
            .replace("{BB}", str(blk["both"]))
            .replace("{ROT}", rot_table)
            .replace("{AUDIT}", ABODY or ""))

    if ABODY and ACSS:
        page = page.replace("</style>", ACSS.replace("<style>", "") + "\n</style>", 1)

    out = PATH.page("H34晶化城市森林玩家视角充能点.html")
    open(out, "w", encoding="utf-8").write(page)
    print("->", out, len(page))
    print("   分级 S%d A%d B%d C%d D%d · 锥宽中位 %.1fpx · 池子 %.0f~%.0f%%"
          % (gcnt["S"], gcnt["A"], gcnt["B"], gcnt["C"], gcnt["D"],
             med_cone, min(pool), max(pool)))


if __name__ == "__main__":
    main()
