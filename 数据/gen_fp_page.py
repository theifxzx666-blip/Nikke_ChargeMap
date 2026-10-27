# -*- coding: utf-8 -*-
"""生成《第 35 章 沼泽丛林 · 玩家视角充能点》汇总页：5 张实机机位图，每张 5 个点。

v7 口径（对应实战机制）
----------------------
1. 开局只有主控一人充能（小美人鱼带火力聚焦时才是 5 人），故主指标是「单人段数」。
2. 受击点耐久只有三档 soft 100 / medium 500 / hard 1000，软质一打就碎，碎了不再充能，
   故主排序用「稳态段数」= 软质碎掉后仍能穿透的段数（medium + hard）。
"""
import json, os, html

import audit_html

ROOT = os.path.dirname(os.path.abspath(__file__))
ARENAS = ["001", "002", "003", "004", "005"]


def load():
    """各战场的默认阵位（cover_3，游戏进图位置）—— 跨战场对照表统一用这一份。

    verify/audit/sim 只回写 px_<arena>_cover_3.json，所以这里优先读它；
    px_<arena>.json 是兼容旧脚本的副本。
    """
    out = {}
    for a in ARENAS:
        for name in ("px_%s_cover_3.json" % a, "px_%s.json" % a, "fp_%s.json" % a):
            p = os.path.join(ROOT, "导出", name)
            if os.path.exists(p):
                out[a] = json.load(open(p, encoding="utf-8"))
                break
    return out


VIEWS = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]


def load_views(arenas=None):
    """{arena: {view: px json}} —— 5 个阵位各一份选点结果。"""
    out = {}
    for a in (arenas or ARENAS):
        d = {}
        for v in VIEWS:
            p = os.path.join(ROOT, "导出", "px_%s_%s.json" % (a, v))
            if os.path.exists(p):
                d[v] = json.load(open(p, encoding="utf-8"))
        if d:
            out[a] = d
    return out


def load_audit_views(arenas=None):
    """{arena: {view: {no: row}}}"""
    out = {}
    for a in (arenas or ARENAS):
        d = {}
        for v in VIEWS:
            p = os.path.join(ROOT, "导出", "audit_%s_%s.json" % (a, v))
            if os.path.exists(p):
                d[v] = {r["no"]: r for r in json.load(open(p, encoding="utf-8"))["rows"]}
        if d:
            out[a] = d
    return out


def load_bands():
    """各战场按 15° 水平区间统计：区间内可破坏物件数 + 该区间能达到的最高稳态段数。"""
    path = os.path.join(ROOT, "导出", "yaw_bands.json")
    if not os.path.exists(path):
        return {}
    return json.load(open(path, encoding="utf-8"))


def load_audit():
    """v12 独立审计结果：容错锥（横/纵）、阵位可用性、等级（默认 3 号位）。"""
    out = {}
    for a in ARENAS:
        for name in ("audit_%s_cover_3.json" % a, "audit_%s.json" % a):
            p = os.path.join(ROOT, "导出", name)
            if os.path.exists(p):
                out[a] = {r["no"]: r for r in json.load(open(p, encoding="utf-8"))["rows"]}
                break
    return out


def boss_marks(a, v):
    """boss 战场的点位叠加层：读该阵位的 px json，没有就返回空（只显示场景）。"""
    p = os.path.join(ROOT, "导出", "px_%s_%s.json" % (a, v))
    if not os.path.exists(p):
        return ""
    try:
        d = json.load(open(p, encoding="utf-8"))
        m = mark_html(d)
    except Exception:
        return ""
    return ('<div class="dmk">%s</div>' % m) if m else ""


def cover_imgs(a, alt):
    """boss 小图：同一战场 5 个阵位各一张，跟着顶部「机位」条切换。

    图是纯场景（出图时 dots=0），点位由 .dmk 叠加层实时画 —— 和 001~005 同一套机制。
    """
    out = []
    for v in VIEWS:
        p = os.path.join(ROOT, "render", "fp_%s_%s.webp" % (a, v))
        if not os.path.exists(p):
            continue
        cls = "cvwrap cv-on" if v == "cover_3" else "cvwrap"
        out.append('<div class="%s" data-cv="%s"><div class="simg">'
                   '<img src="数据/render/fp_%s_%s.webp" alt="%s · %s">%s</div></div>'
                   % (cls, v, a, v, alt, v, boss_marks(a, v)))
    if not out:                       # 还没重拍：退回旧的单张 png
        png = os.path.join(ROOT, "render", "fp_%s.png" % a)
        if os.path.exists(png):
            out.append('<div class="cvwrap cv-on" data-cv="cover_3">'
                       '<img src="数据/render/fp_%s.png" alt="%s"></div>' % (a, alt))
    return "".join(out)


def band_table(bands):
    if not bands:
        return ""
    heads = "".join("<th>%+.0f~%+.0f°</th>" % (b["lo"], b["hi"])
                    for b in bands[ARENAS[0]])
    rows = []
    for a in ARENAS:
        cells = []
        for b in bands[a]:
            st = b["steady"]
            cls = "s%d" % min(st, 4)
            cells.append('<td class="%s">%d<i>%d件</i></td>' % (cls, st, b["nobj"]))
        rows.append('<tr><td class="no"><b>%s</b></td>%s</tr>' % (a, "".join(cells)))
    return ('<table class="hm"><thead><tr><th>战场</th>%s</tr></thead><tbody>%s</tbody></table>'
            % (heads, "".join(rows)))


# 特性标签 -> 颜色类
FT = {"不掉段": "keep", "高稳态": "hi", "近景": "near", "远景": "far", "全阵位": "all"}


def esc(s):
    return html.escape(str(s))


def short(name):
    return name.replace("sbg_swamplandjungle_", "")


def conf_cell(p):
    """可信度单元格：等级 + 分数 + 达标率。"""
    g = p.get("grade")
    if not g:
        return "—"
    f = p["sim"]["follow"]
    return ('<i class="gr %s">%s</i><b>%.0f</b><s>%d%% · 均 %.1f 段</s>'
            % (g, g, p["conf"], round(f["hit_rate"] * 100), f["mean"]))


def rot_line(d):
    """战场级轮换信息（sim_charge.py 产出）。"""
    fs = (d.get("verify") or {}).get("field_sim")
    if not fs:
        return ""
    A, B = fs["A"], fs["B"]
    warn = ' <b class="warn">该战场可破坏物不够充满，其余需靠打敌人</b>' if A["short"] else ""
    g = fs.get("greedy_A") or {}
    order = (A.get("order_greedy") or [])[:9]
    save = A["shots"] - g.get("shots", A["shots"])
    seq = ('<br><b>推荐顺序</b> ' + " → ".join(str(x) for x in order)
           + (" 等 %d 个点" % g.get("pts", 0))
           + ('（<b>%d 发</b>，按编号顺序要 %d 发，省 %d 发）' % (g["shots"], A["shots"], save)
              if save > 0 else '（%d 发，与编号顺序相同）' % g.get("shots", A["shots"]))) if order else ""
    return ('<p class="rot"><b>轮换</b>：可破坏物池 <b>%d</b> 件 = <b>%.0f%%</b> 爆裂条%s<br>'
            '一枪碎（A）需 <b>%d</b> 发 / 走过 <b>%d</b> 个点 · 每次上限 30（B）%d 发 / %d 个点%s'
            % (fs["pool"], fs["pool_pct"], warn,
               A["shots"], A["pts"], B["shots"], B["pts"], seq))


def mark_html(d):
    """该阵位的点位 -> 图片上的 HTML 叠加层。

    坐标取 px json 里的 px（相机投影后的屏幕像素，基准 fp.w × fp.h），换算成百分比。
    图片按 width:100% 显示，百分比定位自动跟随缩放，不用 JS 重算。
    颜色按稳态段数分级：5+ 金 / 4 薄荷 / 3 蓝 / 2 灰 / <2 暗。
    """
    w = d.get("w") or 1600
    h = d.get("h") or 900
    out = []
    for p in d["points"]:
        px = p.get("px")
        if not px:
            continue
        s_ = p["n_steady"]
        g = ("g5" if s_ >= 5 else "g4" if s_ >= 4 else "g3" if s_ >= 3
             else "g2" if s_ >= 2 else "g1")
        ps = p.get("per_slot_steady") or p["per_slot"]
        ss = ",".join(str(ps.get("cover_%d" % i, 0)) for i in range(1, 6))
        out.append(
            '<i class="dm %s" data-no="%d" data-ss="%s" style="left:%.2f%%;top:%.2f%%" '
            'title="%d 号 · 稳态 %d 段 / 首轮 %d 段 · 首击 %.0fm · c1~c5 = %s"></i>'
            % (g, p["no"], ss, px[0] * 100.0 / w, px[1] * 100.0 / h,
               p["no"], s_, p["n"], p["first"], ss))
    return "".join(out)


def cover_body(a, d, au=None):
    """单个阵位（机位）的内容：该阵位的出图 + 点位表 + 说明。

    不同阵位的相机位置差最多 10.8m，像素坐标、可达角度、点位集合都不同 ——
    所以图和表必须成套出现，不能拿 3 号位的点位去标注 5 号位的画面。
    """
    pts = d["points"]
    au = au or {}
    top = pts[0]
    # 出图：优先按阵位的 webp；没有就退回旧的单张 png（还没重拍的战场）
    v = d["view"]
    webp = os.path.join(ROOT, "render", "fp_%s_%s.webp" % (a, v))
    png = os.path.join(ROOT, "render", "fp_%s.png" % a)
    if os.path.exists(webp):
        imgsrc = "数据/render/fp_%s_%s.webp" % (a, v)
    elif os.path.exists(png):
        imgsrc = "数据/render/fp_%s.png" % a
    else:
        imgsrc = ""
    rows = []
    for p in pts:
        m = p["mix"]
        ps = p.get("per_slot_steady") or p["per_slot"]   # v12：用稳态段数，与表头口径一致
        # v12：c1~c5 已扣除「被自家/相邻掩体挡住」——0 不是没数据，是那个阵位打不出去
        per = "".join(
            ('<td class="c zero" title="该阵位被掩体挡住，打不出去">0</td>'
             if ps.get("cover_%d" % i, 0) == 0 else
             '<td class="c%s">%d</td>'
             % (" hot" if ps.get("cover_%d" % i, 0) >= 5 else "",
                ps.get("cover_%d" % i, 0)))
            for i in range(1, 6))
        tags = "".join('<i class="ft %s">%s</i>' % (FT.get(t, ""), esc(t))
                       for t in p.get("tags", [])) or '<i class="ft">—</i>'
        rc = au.get(p["no"]) or {}
        cy, cp_ = rc.get("cone_yaw_px"), rc.get("cone_pitch_px")
        if cy is None:
            cone_td = ('<td class="d">±%dpx</td>' % p["rad"]) if p.get("rad") is not None \
                else '<td class="d">—</td>'
        else:
            cone_td = ('<td class="cone %s"><b>%.1f</b><s>%.1f</s></td>'
                       % ("narrow" if min(cy, cp_) < 2.5 else "", cy, cp_))
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
               cone_td, conf_cell(p), p["total"], tags, per))

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
  <div class="cvtop">
    <div class="badge">机位 <b>{view}</b>{dflt} · 最强点 稳态 <b>{st}</b> 段 · 首轮 <b>{n}</b> 段</div>
    <div class="cvdim">达标点 <b>{np_}</b> 个</div>
  </div>
  <figure class="stage">
    <div class="simg">
      <a href="{imgsrc}" target="_blank"><img src="{imgsrc}" alt="战场 {a} 机位 {view}"></a>
      <div class="dmk">{marks}</div>
    </div>
    <figcaption>图上的圆点由页面实时绘制（不是烧在图里的）—— 切换「显示几个」与
      「跨阵位对照」时，圆点会跟着增减/变灰。<br>
      机位 <code>{view}</code> · 相机 <code>camera_position</code> = ({cx}, 0.00, {cz}) ·
      角色站位 = ({chx}, {chy}, {chz}) · 视高 2.34m（地面 y = −2.34）· 沿 +z · 竖直 FOV 60°</figcaption>
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
  <p class="cn"><b>本节的图和点位表只属于机位 {view}</b> —— 换阵位请点页面顶部的「机位」切换条，
    图和表会一起换。<b>c1~c5</b> 列是「同一个瞄准点在其它阵位还能打几段」，与机位切换不是一回事：
    后者才是站在该阵位时看到的画面。<br>
    <b>稳态</b> = 软质目标碎掉后仍能穿透的段数（中 + 硬），决定持续充能；
    <b>首轮</b> = 全目标完好时的段数；<b>聚焦</b> = 小美人鱼火力聚焦下 5 人同时开火的合计段数。<br>
    <b>容错 横/纵</b>（v12 实测，绕开相机）：准星偏离这颗像素多少还能保住标称段数 ——
    横向大、纵向小是常态，因为横向移一移还是打同一件东西，纵向一抖就换目标了。
    <b>纵向 &lt;2.5px 的会标红</b>，那基本是「能打中但稳不住」。<br>
    <b>红色的 0 = 那个阵位被自家或相邻的高掩体挡住，打不出去</b>。<br>
    <b>①~⑤ 首选</b>（金/薄荷绿），<b>⑥ 起为补充</b>（左侧竖线标记）：段数偏低，但换了站位、
    被掩体挡住、或需要描远处目标时可以顶上去 —— 用页面顶部的切换条决定显示几个。<br>
    <b>不掉段</b> = 命中里没有软质，碎裂不影响；
    <b>全阵位</b> = 「5 个阵位都能打到 ≥2 段」；
    <b>近景/远景</b> = 首击距离 ≤18m / ≥40m。</p>
  <details><summary>展开 {np_} 个点的逐件命中明细（含耐久档）</summary>{detail}</details>
""".format(
        a=a, v=d["view"], view=d["view"], imgsrc=imgsrc,
        marks=mark_html(d) if imgsrc else "",
        st=top["n_steady"], n=top["n"], np_=len(pts),
        dflt='（游戏进图默认）' if d["view"] == "cover_3" else "",
        cx=("%.1f" % d["cam"][0]), cz=("%.1f" % d["cam"][2]),
        chx=("%.1f" % d["char"][0]), chy=("%.1f" % d["char"][1]),
        chz=("%.1f" % d["char"][2]),
        rows="".join(rows), detail="".join(detail), rot=rot_line(d))


def arena_block(a, pack):
    """一个战场 = 5 个阵位容器，页面上由顶部「机位」切换条控制显示哪一个。"""
    blocks = []
    keys = sorted(pack)
    first = "cover_3" if "cover_3" in keys else (keys[0] if keys else "")
    for v in keys:
        d, au = pack[v]
        cls = "cvwrap cv-on" if v == first else "cvwrap"   # 无 JS 时也能看到默认机位
        blocks.append('<div class="%s" data-cv="%s">%s</div>'
                      % (cls, v, cover_body(a, d, au)))
    return """
<section class="ar" id="a{a}">
  <div class="ah">
    <h3>战场 <span>{a}</span></h3>
    <a class="live" title="需先运行 启动战场查看器.bat（本地服务 8899）" href="http://127.0.0.1:8899/viewer/fp.html?arena={a}" target="_blank">打开可交互视图 ↗</a>
  </div>
{blocks}
</section>""".format(a=a, blocks="".join(blocks))


CFSEC = """__ROT__\n\n<h2>v10.5：每个点给一个可信度</h2>
<p class="body">前面的 4 段 / 3 段是<b>一组假设下的确定解</b>：相机在 <code>camera_position</code>、
    朝向沿 +z 且俯角 0、角色正好站在阵位中心、枪口高 1.45m、准星能压到那一颗像素。
    这些里有一半是<b>推断</b>而非实测。所以「4 段」可不可靠，取决于这些假设被抖动时它还站不站得住。</p>
<p class="body">做法是<b>把同一颗目标反复重打 300 次</b>：每次随机抖一遍站位、枪口高度、手抖、后坐、
    几何误差，再走完整链路（准星 → 相机射线 → 命中点 → 枪口瞄准 → 穿透计数 → 遮挡截断），
    看还剩几段。得到的是<b>段数分布</b>，不是一个数。</p>
<div class="note">
  <b>五个随机扰动（影响可信度）</b>
  <ul>
    <li><b>站位 ±0.30m</b>：掩体后左右走位，不会正好站在阵位中心。</li>
    <li><b>枪口高度 ±0.15m</b>：不同角色模型的枪口位置差别不小。</li>
    <li><b>手抖 ±2~4px</b>：支撑半径越小的点，要求越精。</li>
    <li><b>后坐 0.12°</b>：连射时枪口上跳，纵向偏 ≈1.8px。</li>
    <li><b>几何 1.5px</b>：渲染网格与碰撞体的简化差。</li>
  </ul>
</div>
<p class="body"><b>另外三项不进评分</b>：相机俯仰、机位朝向、FOV。它们错了会让<b>整张图一起偏</b>
    （属于工具级失效，玩家第一眼就会发现画面与实机对不上），不该摊到单个点头上，
    所以只在文档里单列为「相机标定风险」。但实测这三项是本项目当前的<b>最大瓶颈</b> —— 见下。</p>
<p class="body"><b>可信度 = 100 × (0.60·达标率 + 0.25·可用率 + 0.15·P10/标称)</b>：
    达标率 = 300 次里仍拿到标称段数的比例；可用率 = 仍 ≥2 段（不退化成单判）的比例；
    P10/标称 = 最差 10% 情况还剩几成。分级 <span class="gr A">A</span> ≥80、
    <span class="gr B">B</span> ≥68、<span class="gr C">C</span> ≥52、
    <span class="gr D">D</span> &lt;52。</p>
__TABLE__
<div class="note">
  <b>三条结论</b>
  <ul>
    <li><b>段数和可信度是两个维度</b>：004 的 2 段点达标率 88%、005 的 4 段点只有 14%。
      前者虽然少，但「说 2 段就给 2 段」；后者峰值漂亮，抖一抖就塌。</li>
    <li><b>8 张图 130 个点里只有 8 个 A 级（6%）</b>，一半以上落在 C/D。达标率中位 62%，
      也就是说「照着打」平均有近四成的概率少 1 段；期望段数比标称平均低 <b>0.58 段</b>。</li>
    <li><b>相机俯仰是全局瓶颈</b>：俯角推到 ±2°，图上标注位置纵向漂 <b>≈30px</b>（2° × 15px/°），
      足够让准星落到隔壁那根栏杆上；机位朝向 ±0.8° 漂 13px，FOV ±0.8° 漂 5px。
      「相机到底有没有俯角」这一条不解决，红点位置就只是相对参考。</li>
  </ul>
</div>

"""

ROTSEC = """<h2>V11：单点段数不是目标，「能凑够一条」才是</h2>
<p class="body">V10.5 把每个点拆开评估。可是爆裂条是一条 100% 的共享进度条 —— 单点再强也只贡献一次。
    一旦承认「受击物碎掉就从场景消失」，就必须把点位当成一条<b>轮换路径</b>来算：
    A 打碎的件，B 就打不到了。这条耦合在之前的「单点段数」里完全没体现。</p>
<div class="note">
  <b>这里只有一件不确定的事，但它决定一切</b>
  <p class="body" style="margin:6px 0">耐久是 HP（soft 100 / medium 500 / hard 1000），而每次命中实际扣多少血，
    取决于 <code>hpdamage_limit=30</code> 的语义 —— 表里没写，两种都合法：</p>
  <ul>
    <li><b>A · 无上限</b>：单发伤害（数千~数万）远超 1000 → 一枪打穿的全部碎 → <b>每个点只能用 1 发</b></li>
    <li><b>B · 上限 30</b>：每发最多扣 30 → soft 4 发、medium 17 发、hard 34 发才碎 → <b>单点能撑 34 发</b></li>
  </ul>
</div>
<p class="body">两种假设下玩法完全相反：<b>A 必须走位轮换 10~17 个点，B 一个点打到底就够</b>。
    所以下表两个数字都给，并且额外给出<b>可破坏物池</b> —— 池子 × 280 就是这张图靠打地形能拿到的上限。</p>
__TABLE__
<div class="note">
  <b>三条结论</b>
  <ul>
    <li><b>打地形最多只能充满 0.36~1.51 条</b>。004 的池子只有 13 件 = 36%，光靠打地形连四成都拿不到；
      001 有 14 个点、池子 38 件 = 106%，刚好够一条。<b>所以「打一轮就没充能了」不是找错点，是目标总量不够。</b></li>
    <li><b>池子的覆盖率只有 11%~47%</b>（001 是 27%：场景 143 件可破坏物，点位只碰到 38 件）。
      原因是这些点全都挤在中线同一条射线上、互相打同一批物件 —— 这正是「点位为什么显得挤在中线」的另一面。
      想提高总充能，该<b>扩大覆盖</b>（打两侧、打近景），而不是继续找更强的单点。</li>
    <li><b>按「单点段数」排序不是最优</b>：002 用同样的点、只换顺序（贪心按边际覆盖选下一点），
      充满发数从 13 降到 9（省 31%）。因为重叠的点排在前面会浪费。<b>顺序优化的收益在 0~31% 之间。</b></li>
  </ul>
</div>

"""

def main():
    data = load()
    AUDIT = load_audit()
    VDATA = load_views()
    VAUDIT = load_audit_views()
    # 每个战场一份 {view: (点位数据, 审计行)}；缺阵位就少一个容器，不报错
    PACK = {a: {v: (VDATA[a][v], (VAUDIT.get(a) or {}).get(v))
                for v in sorted(VDATA.get(a) or {})} for a in ARENAS}
    # 还没跑多阵位的战场：退回 3 号位单机位，页面不至于空掉
    for a in ARENAS:
        if not PACK[a] and a in data:
            PACK[a] = {"cover_3": (data[a], AUDIT.get(a))}
    best = max(ARENAS, key=lambda a: (data[a]["points"][0]["n_steady"],
                                      data[a]["points"][0]["n"]))

    cmp_rows = []
    for a in ARENAS:
        p = data[a]["points"][0]
        m = p["mix"]
        cmp_rows.append(
            '<tr><td class="no"><b>%s</b></td><td class="seg">%d</td><td class="seg2">%d</td>'
            '<td class="pct">%.1f%%</td><td class="pct2">%.1f%%</td>'
            '<td class="mix"><i class="s">%d</i><i class="m">%d</i><i class="h">%d</i></td>'
            '<td class="d">%.0fm</td><td class="d">%d</td><td class="nm">%s</td></tr>'
            % (a, p["n_steady"], p["n"], p["steady_pct"], p["pct"],
               m["soft"], m["medium"], m["hard"], p["first"], p["total"],
               esc(short(p["detail"][0]["name"]))))

    body = "\n".join(arena_block(a, PACK[a]) for a in ARENAS)
    t = data[best]["points"][0]

    # ---- 可信度分布表 ----
    # ---- 战场轮换表 ----
    S2 = 'display:block;font-size:10px;color:var(--tx3);margin-top:2px'
    rt = []
    for a in ARENAS:
        d = data[a]
        fs = (d.get("verify") or {}).get("field_sim")
        if not fs:
            continue
        tot_obj = d.get("n_hitbox_obj") or 1
        cov = 100.0 * fs["pool"] / tot_obj
        A, B = fs["A"], fs["B"]
        gA = fs.get("gain_A", 0)
        rt.append(
            '<tr><td class="no"><b>%s</b></td><td class="d">%d</td>'
            '<td class="hl">%d</td>'
            '<td class="hl">%.0f%%<s style="%s">%d / %d 件</s></td>'
            '<td class="hl %s">%.0f%%</td>'
            '<td class="d">%d 发</td>'
            '<td class="d">%d 发 <s style="font-size:10px;color:var(--tx3)">/ %d 点</s></td>'
            '<td class="hl %s">%s</td></tr>'
            % (a, fs["n_points"], fs["pool"], cov, S2, fs["pool"], tot_obj,
               "warn" if fs["pool_pct"] < 100 else "",
               fs["pool_pct"],
               A["shots"], B["shots"], B["pts"],
               "warn" if gA > 0 else "",
               ("-%d 发" % gA) if gA > 0 else "—"))
    rot_table = ('<table class="tb rt"><thead><tr>'
                 '<th>战场</th><th>点位</th><th>池子<br>件数</th><th>覆盖率</th>'
                 '<th>池子<br>=充能</th><th>A 一枪碎</th><th>B 上限 30</th>'
                 '<th>贪心<br>省</th></tr></thead><tbody>%s</tbody></table>'
                 '<p class="cn" style="text-align:center;font-size:11px">A 模式每个点只用 1 发，所以「发数 = 点数」；B 模式才需要看点位数。贪心省 = 只换顺序能少打几发。</p>' % "".join(rt))
    cf_rows, tot = [], {"A": 0, "B": 0, "C": 0, "D": 0}
    for a in ARENAS:
        d = data[a]
        sm = d.get("verify", {}).get("summary", {})
        for g in tot:
            tot[g] += sm.get(g, 0)
        n_all = max(1, sum(sm.values()))
        seg = "".join('<i class="g%s" style="width:%.1f%%"></i>' % (g, 100.0 * sm.get(g, 0) / n_all)
                      for g in ("A", "B", "C", "D"))
        top = max(d["points"], key=lambda x: x.get("conf", 0))
        p0 = d["points"][0]
        vf = d.get("verify", {})
        cf_rows.append(
            '<tr><td class="no"><b>%s</b></td>'
            '<td class="cf">%s</td>'
            '<td class="cf"><b>%d%%</b></td>'
            '<td class="cf" style="min-width:96px"><div class="cfbar">%s</div>'
            '<s style="font-size:10px;color:var(--tx3)">A%d B%d C%d D%d</s></td>'
            '<td class="cf">%d 号 <b>%.0f</b><s>%s</s></td>'
            '<td class="d" style="font-size:11px;color:var(--tx3)">%d 次 · %.0fs</td></tr>'
            % (a, conf_cell(p0),
               round((p0.get("sim") or {}).get("follow", {}).get("hit_rate", 0) * 100), seg,
               sm.get("A", 0), sm.get("B", 0), sm.get("C", 0), sm.get("D", 0),
               top["no"], top.get("conf", 0), top.get("grade", "-"),
               vf.get("n_sim", 0), vf.get("secs", 0)))
    n_all = max(1, sum(tot.values()))
    cf_sum = ('<tr style="border-top:2px solid var(--bd2)"><td class="no"><b>合计</b></td>'
              '<td class="cf">—</td><td class="cf">—</td>'
              '<td class="cf"><div class="cfbar">%s</div><s style="font-size:10px;color:var(--tx3)">A%d B%d C%d D%d</s></td>'
              '<td class="cf">—</td><td class="d">—</td></tr>'
              % ("".join('<i class="g%s" style="width:%.1f%%"></i>' % (g, 100.0 * tot[g] / n_all)
                         for g in ("A", "B", "C", "D")),
                 tot["A"], tot["B"], tot["C"], tot["D"]))
    cf_table = ('<table class="tb"><thead><tr><th>战场</th><th>① 可信度</th><th>① 达标率</th>'
                '<th>等级分布</th><th>本图最稳的点</th><th>模拟量</th></tr></thead><tbody>%s%s</tbody></table>'
                % ("".join(cf_rows), cf_sum))

    page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>第 35 章 沼泽丛林 · 玩家视角充能点</title>
<style>
  :root{
    --bg:#080e0c; --pan:#0e1714; --bd:#1e3a30; --bd2:#2b4d40;
    --tx:#dcece4; --tx2:#9dbdb0; --tx3:#6f9484; --gold:#ffcf6b; --mint:#7fe3b4;
    --red:#ff9d8a; --yel:#e8c96a;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:var(--bg);color:var(--tx);
    font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.65;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:1180px;margin:0 auto;padding:44px 26px 80px}
  header.top{border-bottom:1px solid var(--bd);padding-bottom:26px;margin-bottom:8px}
  .kicker{color:var(--tx3);font-size:11.5px;letter-spacing:2.2px;text-transform:uppercase}
  h1{font-size:31px;font-weight:600;letter-spacing:.6px;margin:9px 0 12px}
  h1 span{color:var(--gold)}
  .lead{color:var(--tx2);font-size:14px;max-width:840px}
  .lead b{color:var(--gold);font-weight:600}
  .kv{display:flex;gap:26px;flex-wrap:wrap;margin-top:20px}
  .kv div{font-size:12px;color:var(--tx3)}
  .kv b{display:block;color:var(--tx);font-size:19px;font-weight:600;letter-spacing:.3px;margin-top:2px}
  .kv b i{font-size:12px;font-style:normal;color:var(--tx2);margin-left:2px}
  h2{font-size:15px;font-weight:600;letter-spacing:.6px;margin:44px 0 14px;
    padding-left:11px;border-left:3px solid var(--gold);color:#eafaf1}
  p.body{color:var(--tx2);font-size:13.5px;margin:10px 0}
  p.body b{color:var(--tx)}
  .note{background:var(--pan);border:1px solid var(--bd);border-radius:10px;padding:14px 17px;
    font-size:12.5px;color:var(--tx2);margin:14px 0}
  .note b{color:var(--gold)}
  .note ul{margin:6px 0 0 18px}
  .note li{margin:4px 0}
  table{width:100%;border-collapse:collapse;font-size:12.5px;margin:14px 0 6px}
  th{color:var(--tx3);font-weight:500;text-align:left;padding:8px 7px;border-bottom:1px solid var(--bd);
    font-size:11.5px;line-height:1.35;white-space:nowrap}
  td{padding:7px;border-bottom:1px solid #14231d;color:var(--tx2)}
  td.no{width:34px}td.no b{color:var(--gold);font-size:14px}
  td.seg,td.sq{color:#eafaf1;font-weight:600;font-size:14px}
  td.seg2{color:var(--tx);font-weight:600}
  td.pct{color:var(--mint)}
  td.pct2{color:var(--tx3)}
  td.d{color:var(--tx3)}td.r{color:var(--tx3)}
  td.mix i{font-style:normal;display:inline-block;min-width:17px;text-align:center;
    border-radius:3px;font-size:10px;margin-right:3px;padding:0 3px}
  td.mix i.s{background:#2a3b33;color:#9fc0b1}
  td.mix i.m{background:#3d3620;color:var(--yel)}
  td.mix i.h{background:#42231f;color:var(--red)}
  td.c{text-align:center;color:var(--tx3);width:34px}
  td.c.hot{color:var(--gold);font-weight:600}
  td.c.zero{color:#ff5a45;font-weight:700;background:#2a1512}
  td.cone{white-space:nowrap;font-size:12.5px}
  td.cone b{font-weight:600;color:var(--mint)}
  td.cone s{text-decoration:none;color:var(--tx3);font-size:11px;margin-left:3px}
  td.cone.narrow b,td.cone.narrow s{color:#ff9d8a}
  td.nm{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--tx3)}
  td.tags{white-space:nowrap}
  .gr{display:inline-block;font-style:normal;font-weight:700;font-size:10px;line-height:1.5;
    padding:0 4px;border:1px solid;border-radius:4px;margin-right:4px;vertical-align:1px}
  .gr.A{color:#7fd6a0;border-color:#38614a;background:#102a20}
  .gr.B{color:#8fc0d8;border-color:#375463;background:#0e2028}
  .gr.C{color:#d9b56a;border-color:#665029;background:#221c0e}
  .gr.D{color:#c07a7a;border-color:#5f3838;background:#201313}
  td.cf{white-space:nowrap}
  td.cf b{font-weight:600;margin-left:1px}
  td.cf s{text-decoration:none;color:var(--tx2);font-size:10px;margin-left:6px;opacity:.8}
  .cfbar{display:flex;gap:1px;height:8px;border-radius:3px;overflow:hidden;margin:5px 0 2px}
  .cfbar i{display:block;height:100%}
  .cfbar .gA{background:#4f9e76}
  .cfbar .gB{background:#4f83a0}
  .cfbar .gC{background:#a08a4b}
  .cfbar .gD{background:#8a5252}
  .ft{font-style:normal;display:inline-block;font-size:10px;line-height:1.5;border-radius:3px;
    padding:0 4px;margin-right:3px;background:#16241e;color:var(--tx3)}
  .ft.keep{background:#16352a;color:#8ce0b6}
  .ft.hi{background:#332c15;color:var(--gold)}
  .ft.near{background:#1b2d33;color:#88c4d4}
  .ft.far{background:#241f33;color:#b0a4dd}
  .ft.all{background:#2a2418;color:#d8c48a}
  tr.minor td{border-left:none}
  tr.minor td.no b{color:var(--tx3);font-weight:500}
  tr.minor td.seg{color:#cfe3d8;font-weight:500}
  tr.minor td.no{border-left:3px solid #1e3a30}
  table.hm{font-size:12px;margin:16px 0 4px}
  table.hm th{text-align:center;padding:7px 4px}
  table.hm td{text-align:center;padding:9px 4px;font-weight:600;font-size:13.5px;
    border:1px solid var(--bg);border-radius:0}
  table.hm td.no{text-align:left;font-family:ui-monospace,Consolas,monospace;
    font-size:12.5px;color:var(--tx);background:none}
  table.hm td i{display:block;font-style:normal;font-weight:400;font-size:10px;opacity:.72;margin-top:1px}
  table.hm td.s1{background:#12352a;color:#8ce0b6}
  table.hm td.s2{background:#1c5a45;color:#d8f7ea}
  table.hm td.s3{background:#2a8563;color:#f0fff8}
  table.hm td.s4{background:#5fcf9e;color:#06301f}
  table.hm td.s0{background:#1a2420;color:#5f7a6e}
  .ar{margin-top:52px;background:var(--pan);border:1px solid var(--bd);border-radius:14px;
    padding:22px 22px 26px}
  .ah{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:14px}
  .ah h3{font-size:16px;font-weight:600;color:#eafaf1}
  .ah h3 span{color:var(--gold);font-family:ui-monospace,Consolas,monospace}
  .badge{font-size:12px;color:var(--tx2);background:#0a1410;border:1px solid var(--bd2);
    border-radius:20px;padding:4px 13px}
  .badge b{color:var(--gold)}
  .live{margin-left:auto;font-size:11.5px;color:var(--mint);text-decoration:none;
    border:1px solid #2b4d40;border-radius:6px;padding:4px 10px}
  .live:hover{background:#14251e}
  figure{margin:0 0 6px}
  figure img{width:100%;display:block;border-radius:9px;border:1px solid #16261f}
  figcaption{font-size:11px;color:var(--tx3);margin-top:7px}
  .cn{font-size:11.5px;color:var(--tx3);margin-top:4px}
  .cn b{color:var(--tx2);font-weight:600}
  details{margin-top:12px;border-top:1px solid #14231d;padding-top:10px}
  summary{cursor:pointer;font-size:12px;color:var(--mint);outline:none}
  .dt{margin-top:12px;font-size:12px}
  .dth{color:var(--tx3);font-size:11px;margin-bottom:5px}
  .dt ol{margin-left:20px;color:var(--tx2)}
  .dt li{margin:2px 0;font-family:ui-monospace,Consolas,monospace;font-size:11px}
  .dt li i{font-style:normal;color:var(--tx3);margin-left:7px}
  .tag{display:inline-block;min-width:16px;text-align:center;border-radius:3px;font-size:9px;
    padding:0 4px;margin-right:7px;font-family:-apple-system,"Microsoft YaHei",sans-serif}
  .tag.soft{background:#1d4033;color:#8ce0b6}
  .tag.medium{background:#3d3620;color:var(--yel)}
  .tag.hard{background:#42231f;color:var(--red)}
  footer{margin-top:56px;border-top:1px solid var(--bd);padding-top:18px;
    font-size:11px;color:var(--tx3);line-height:1.9}
  table.tb.rt{width:auto;margin:14px auto 6px;font-size:12px}
  table.tb.rt th{white-space:normal;text-align:center;padding:8px 14px}
  table.tb.rt th:first-child{white-space:nowrap;min-width:58px}
  table.tb.rt td.hl{color:#7fe3b4;font-weight:600;font-size:13px;text-align:center;white-space:nowrap}
  table.tb.rt td.hl.warn{color:#d9b56a}
  table.tb.rt td.d{text-align:center;white-space:nowrap}
  table.tb.rt td{padding:7px 13px}
  table.tb.rt s{text-decoration:none;font-style:normal}
  table.tb.rt td.hl s{display:block;margin-top:1px;font-weight:400;line-height:1.3}
  table.tb.rt td.no{border-left:none}
  p.rot{margin:10px 0 2px;padding:9px 12px;background:#0c1613;border-left:2px solid #38614a;
    border-radius:0 6px 6px 0;font-size:12px;color:var(--tx2);line-height:1.65}
  p.rot b{color:#bfe6d2;font-weight:600}
  p.rot b.warn{color:#d9b56a}
  .nbar{position:sticky;top:0;z-index:9;display:flex;gap:9px;align-items:center;flex-wrap:wrap;
    background:rgba(8,14,12,.94);backdrop-filter:blur(8px);border-bottom:1px solid var(--bd);
    padding:11px 0;margin:0;font-size:12px;color:var(--tx3)}
  .nbar em{font-style:normal;color:var(--tx2)}
  .nbar button{font:inherit;font-size:12px;font-weight:600;color:#9ec4b3;cursor:pointer;
    background:#101b17;border:1px solid var(--bd2);border-radius:7px;padding:3px 11px}
  .nbar button:hover{background:#16241e;color:#eafaf1}
  .nbar button.on{background:var(--mint);border-color:var(--mint);color:#06110c}
  .nbar span.hint{margin-left:auto;font-size:11px;color:#587566}
  .nbar .sep{width:1px;height:16px;background:var(--bd2);margin:0 3px}
  .nbar button.slot{min-width:30px;padding:3px 8px}
  /* ---- 图上点位叠加层（图里不再烧标注）---- */
  .stage .simg{position:relative;display:block;line-height:0;border-radius:8px;
    overflow:hidden;background:#0a1210}
  .stage .simg img{width:100%;height:auto;display:block}
  .dmk{position:absolute;inset:0;pointer-events:none}
  .dmk .dm{position:absolute;width:22px;height:22px;border-radius:50%;
    transform:translate(-50%,-50%);pointer-events:auto;cursor:help;
    display:flex;align-items:center;justify-content:center;
    border:2px solid var(--c);background:rgba(5,13,10,.74);
    box-shadow:0 0 0 1px rgba(0,0,0,.6),0 2px 9px rgba(0,0,0,.55);
    transition:opacity .14s;font-style:normal;line-height:1}
  .dmk .dm::after{content:attr(data-no);font-size:10.5px;font-weight:700;
    color:var(--c);font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .dmk .dm.g5{--c:#f2c14e} .dmk .dm.g4{--c:#7fd6a0} .dmk .dm.g3{--c:#8fc0d8}
  .dmk .dm.g2{--c:#b9c6bd} .dmk .dm.g1{--c:#88968c}
  .dmk .dm.faint{opacity:.55}                 /* 该阵位只够 1 段 */
  .dmk .dm.off{opacity:.26;filter:grayscale(1)} /* 该阵位被掩体挡住 */
  .dmk .dm.off::after{text-decoration:line-through}
  /* 机位切换条：常驻在「显示个数」条上方，z-index 更高 */
  .nbar.cbar{top:0;z-index:10;border-bottom:1px solid var(--bd);padding-top:14px}
  .nbar.cbar + .nbar{top:44px}
  .nbar button.cv{padding:4px 13px}
  .nbar button.cv i{font-style:normal;font-size:10px;opacity:.62;margin-left:5px}
  .cvwrap{display:none}
  .cvwrap.cv-on{display:block}
  .cvtop{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:0 0 10px}
  .cvtop .cvdim{font-size:12px;color:var(--tx3)}
  .cvtop .cvdim b{color:#cfe9dd}
  /* 按掩体筛选：不达标行降权，不隐藏（信息不能凭空消失） */
  tr.dim{opacity:.42}
  tr.dim td.seg{color:#7a4a42}
  tr.dim td.no b{color:#8a6259}
  td.c.sel{background:#12281f;box-shadow:inset 0 0 0 1px #2f6b52;color:#bfe6d2}
  td.c.sel.hot{color:var(--gold)}
  tr.dead td{text-decoration:line-through;text-decoration-color:#5a3128}
  code{background:#101b17;border:1px solid #1b2f27;border-radius:4px;padding:1px 5px;
    font-size:11px;color:var(--mint)}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="kicker">NIKKE · 第 35 章 swamplandjungle（chapter_id 36 / d_main_35_*）· 拆包实测</div>
  <h1>玩家视角 · 每个战场 <span>最合适的充能点</span></h1>
  <p class="lead">机位取自 <code>cover_3.camera_position</code>：站在角色身后 4.5m、视高 2.34m、
    沿 +z、FOV 60°，图里 ①~⑤ 是首选、其后是补充，都是屏幕上能直接压的位置（默认 5 个，可切到全部）。
    排序按<b>稳态段数</b> —— 开局只有主控一人充能，且软质目标一打就碎，碎了不再充能。</p>
  <div class="kv">
    <div>全场最强<b>__BEST__<i>号战场</i></b></div>
    <div>稳态充能<b>__STPCT__<i>% / 轮</i></b></div>
    <div>首轮充能<b>__NPTCT__<i>% / 轮</i></b></div>
    <div>单发穿透<b>__ST__<i>段稳态 · __N__ 段首轮</i></b></div>
    <div>点位<b>__NP__<i>个 / 图（默认显示 5）</i></b></div>
  </div>
</header>

<div class="nbar cbar">
  <em>机位 · 我站的掩体</em>
  <button class="cv" data-cv="cover_1">1 号位</button>
  <button class="cv" data-cv="cover_2">2 号位</button>
  <button class="cv on" data-cv="cover_3">3 号位<i>进图默认</i></button>
  <button class="cv" data-cv="cover_4">4 号位</button>
  <button class="cv" data-cv="cover_5">5 号位</button>
  <span class="hint">换号位 = 换相机位置，<b>图和点位表一起换</b> · 快捷键 Q / W / E / R / T</span>
</div>

<div class="nbar">
  <em>每个战场显示</em>
  <button data-n="5" class="on">5 个</button>
  <button data-n="8">8 个</button>
  <button data-n="12">12 个</button>
  <button data-n="24">全部</button>
  <span class="sep"></span>
  <em>跨阵位对照</em>
  <button class="slot on" data-s="0">不限</button>
  <button class="slot" data-s="1">1</button>
  <button class="slot" data-s="2">2</button>
  <button class="slot" data-s="3">3</button>
  <button class="slot" data-s="4">4</button>
  <button class="slot" data-s="5">5</button>
  <span class="hint">同一个瞄准点在其它阵位还能打几段（不是换视角）· 快捷键 1 / 2 / 3 / 4</span>
</div>

<p class="lead">下面这节独立审计同样是 <b>3 号位（进图默认阵位）</b> 的口径：
容错锥要绑定一个相机位置才有定义，换阵位后锥宽会变。各阵位的锥宽请看每张战场表里的
「容错 px 横/纵」列（随「机位」条一起换）。</p>

__AUDIT__
__CF__

<h2>v10：判定点从「角度」搬到「像素」</h2>
<p class="body">上一版（v9）在<b>枪口角度</b>上选点，隐含假设「准星指哪、枪口就打哪」。实际链路是
    <code>准星像素 → 相机射线 → 命中点 Pc → 枪口瞄准 Pc</code>，而相机在角色身后 4.5m、右偏 1.2m、高 0.89m，
    与枪口不是同一点：<b>15m 处横移 1.2m 就是 4.6°</b>。本轮实测 8 张图，相机方向与枪口方向的夹角
    <b>中位 3.3~6.5°、最大 15.2°</b> —— v9 报的角度照搬到屏幕上会偏出一段。</p>
<div class="note">
  <b>v10 四条改动</b>
  <ul>
    <li><b>逐像素</b>：先给相机做一张 1600×900 的深度图（Z-buffer 光栅化），每个像素反推出枪口角度，
      再查角度域段数 —— 选点在像素上做，角度只是导出量。</li>
    <li><b>稳定性量化到像素</b>：对逐像素段数图做方框腐蚀，得到<b>稳定半径 ±Rpx</b>（准星偏 R 像素仍不掉段）。
      方框包含半径 R 的圆，所以这个数是<b>保守</b>的：说稳就真稳。</li>
    <li><b>淘汰单判</b>：稳态段数 &lt; 2 的点直接不进候选（打一枪只算一段，不值得占一个编号）。</li>
    <li><b>我方掩体不作判定点</b>：<code>cover_object</code> 单独渲一张深度图，凡是被自家掩体挡住的像素一律不参与
      —— 准星压在自己的掩体上本来也打不出去（5 张图里掩体占掉 33~42% 的像素）。</li>
  </ul>
</div>
<p class="body">遮挡也算进去了：<code>static_object</code>（不可破坏的机械/岩石）与地形会截断射线，
    命中清单只保留遮挡物之前的那些。去重则换成<b>屏幕像素间距</b>（NMS）：中心距 &lt;50px 必冲突、&gt;72px 直接共存，
    中间档才看纵深差 —— 换分辨率、换 FOV 都不用重调参数。</p>

<h2>口径：单人充能 + 碎裂</h2>
<p class="body">上一版把 5 个人的段数直接相加当作「每轮充能」，这在开局不成立，也没考虑受击点被打碎。
    现在按实战机制分成三个数：</p>
<div class="note">
  <b>① 充能主体：开局只有主控一人</b>
  <ul>
    <li>除小美人鱼技能组自带<b>火力聚焦</b>外，开局阶段基本只有主控角色在充能，其余 4 人的输出不进爆裂条。</li>
    <li>所以主指标用<b>单发（单人）段数</b>，不是 5 人相加。表里的 c1~c5 是各阵位的单发值，主控站哪个位置就看哪一列。</li>
    <li>5 人相加的数保留为「<b>聚焦</b>」列，只在火力聚焦窗口内成立。</li>
  </ul>
</div>
<div class="note">
  <b>② 受击点会被打碎：分「首轮」和「稳态」</b>
  <ul>
    <li>可充能物按 <code>ConfigBattleTable</code> 的 hitbox 分组只有三档耐久：<b>soft 100 / medium 500 / hard 1000</b>。</li>
    <li>软质目标耐久很低，一两轮就碎，<b>碎了就不再产生充能命中</b>；中/硬质能撑住。</li>
    <li><b>首轮</b> = 全目标完好时的段数（开局限定）；<b>稳态</b> = 软质碎掉后仍能穿透的段数（中+硬），这是打满一场真正靠得住的数。</li>
    <li>排序用稳态优先、首轮次之 —— 一个「首轮 6 段但 4 件是软的」点，实际只值 2 段。</li>
  </ul>
</div>
<p class="body">两个数都不依赖主观权重：段数来自 Möller–Trumbore 射线求交，档位来自配置表。
    <b>缺的是武器伤害值</b>（未拆出），所以「软质具体几轮碎」换算不出来，只能按耐久档位区分「撑得住 / 撑不住」。</p>

<h2>为什么①~⑤之外还要给补充点</h2>
<p class="body">同一个战场里，能「一串穿透 ≥3 件中/硬目标」的角度是稀缺资源 —— 001 全画面只有 2 个角度做到稳态 4 段，
    003 有 2 个，其余战场稳态上限就是 3 段。这是几何决定的：远景那排物体是竖直面板，要凑出长串必须让射线和这排面板
    共线，可用的俯角窗口只有 1° 左右。</p>
<div class="note">
  <b>所以补充点不是「更差的首选」，而是另一种用途：</b>
  <ul>
    <li><b>换站位还能打</b> —— 主控被强制换掩体（c1~c5 差异见每一列的段数），①~⑤ 里有的点在某阵位只有 1~2 段，补充点里常能找到该阵位 ≥3 段的替代。</li>
    <li><b>挡住时有备份</b> —— 敌人或队友遮住首选方向时，不用重新找点，直接切到旁边编号。</li>
    <li><b>近景稳住节奏</b> —— 标「近景」的点首击 12~18m，爆裂条见底时不用瞄远处小目标。</li>
    <li><b>不掉段的点最省心</b> —— 命中里没有软质，打一整场段数不掉，不用换点。</li>
  </ul>
</div>
<p class="body">补充点的共同代价是<b>段数更低</b>（多为稳态 2 段，约 5.6%/轮）。它们的价值在于「可用性」而不是「上限」：
    真打起来首选被挡、或者站位被换，能立刻顶一个上去，比现场找点强。</p>

<h2>一处筛选修正：同方位、不同纵深的两层点</h2>
<p class="body">有人反馈「①旁边那条管线上也能充能，速率还可以」。按屏幕像素反查，
    那个位置是 <b>yaw −34.5° / pitch +6.0°、3 段（8.4%/发）、48.5m</b> —— 确实能打，但当时没标。
    查下来是筛选规则在误杀，不是点不合格，三处都要改：</p>
<div class="note">
  <ul>
    <li><b>候选池 2° 粗去重是先到先得</b>：旁边的格子先入池，目标格在 1.19° 内被跳过 → 降到 <b>0.75°</b>（只防同格重复）。</li>
    <li><b>候选池只按「窗口稳健值」取前 320 格</b>：只在 1° 窗口内成立的窄峰点排不进来 → 改为按<b>稳态段数</b>全量枚举（上限 4000）。</li>
    <li><b>角距阈值 6° 太宽</b>：4° 在画面上已有 70px，46/34px 靶心不会重叠 → 阈值降到 <b>4°</b>，只有 3°~4° 才要求纵深差 ≥15m。</li>
  </ul>
</div>
<p class="body">改完后每张图从 10 个点扩到 <b>12</b> 个。沼泽丛林这边也救回了几个点，典型是 <b>001 的 ⑫</b>：
    它与 ④ 相距 5.0°、首击都在 15.5m，以前被判成重复，其实一个打左侧树丛、一个打正前灌木，命中集不同。</p>

<h2>点位为什么显得“挤在中线”</h2>
<p class="body">这是看图最容易产生的误会。把画面按水平视角切成 6 段，逐段求「这段里最强能打几段」，
    得到的结果是：<b>左右两侧都有点位，只是强度只有中央的一半</b>。表里数字是该区间内的最高稳态段数，
    小字是该区间内的可破坏物件数。</p>
__BANDS__
<p class="cn">上表覆盖 ±45°，即整块屏幕；画面水平半角 = atan(tan(30°) × 16/9) = 45.7°，扫描范围已贴到画面边缘。</p>

<p class="body"><b>三个事实凑成了“中线密集”的观感：</b></p>
<div class="note">
  <ul>
    <li><b>水平方向其实铺开了。</b>001 的 12 个点从 yaw −35.3° 到 +37.0°，占画面宽度 79%；⑧⑨⑩⑪ 这四个本来就落在两侧。
      只是它们排在编号后面（稳态 2 段），第一眼看过去注意到的都是中央的 ①②。</li>
    <li><b>垂直方向确实集中。</b>可破坏物都立在地面上，而能被穿成长串的那批在 z≈35m 的远景带上，
      仰角固定在 +6~+9°。画面下半（近景泥土、角色脚下）<b>没有可破坏物</b>——
      143 件里俯角低于 −3° 的只有 14 件，所以下半屏自然一个点都没有。</li>
    <li><b>中央强是因为射线可以和远景带共线。</b>那排物体是竖直面板，横向排开；
      从中央看过去正好一穿一排（首轮 6~7 件）。两侧看过去是斜切这排面板，只蹭到边缘 2 件。</li>
  </ul>
</div>

<p class="body"><b>还有一个画面外的发现：</b>可破坏物里只有 55~60% 落在画面内
    （001 是 80/143、002 是 116/220、003 是 58/75、004 是 96/119、005 是 83/127），
    其余分布在 yaw 45~66°，<b>初始视角看不到</b>。其中 002 的 yaw +45~+60 那一段有 47 件物体、
    最高稳态 4 段（首轮 6），比画面内多数区间都强 —— 如果实战里能左右拖动镜头，那块值得单独看一眼；
    如果镜头固定，那部分就是无效区域。</p>

<h2>机位与参数（全部拆包，非估计）</h2>
<table>
  <thead><tr><th>项</th><th>取值</th><th>来源</th></tr></thead>
  <tbody>
    <tr><td>机位</td><td>cover_N 的 <code>camera_position</code></td><td>阵位预制体，5 个阵位各一份</td></tr>
    <tr><td>朝向 / 俯仰</td><td>rotation = identity（沿 +z，俯仰 0°）</td><td>实测全部四元数为 (0,0,0,1)</td></tr>
    <tr><td>视高 / 后撤</td><td>y=0（地面 −2.34）→ 2.34m；角色在 z+4.5、右偏 1.2m</td><td>camera_position vs character_position</td></tr>
    <tr><td>竖直视场</td><td>60°（near 0.1 / far 300）</td><td><code>spotpresentationbase_assets_spotcameracontrol</code></td></tr>
    <tr><td>每段充能</td><td>2.8%（= 280 能量 / 10000，小红帽 SR 单发）</td><td><code>ulti_gauge_shot_hit=4</code> × burst_energy_max</td></tr>
    <tr><td>耐久档位</td><td>soft 100 / medium 500 / hard 1000</td><td><code>ConfigBattleTable</code> hitbox 分组</td></tr>
  </tbody>
</table>

<h2>五个战场的最强点横向对比</h2>
<p class="lead">下面这张表和后面的轮换模拟<b>都按 3 号位（游戏进图默认阵位）统计</b> ——
跨战场横向对照要固定一个机位才有意义。单个阵位的完整数据在每张战场上方用「机位」条切换。</p>
<table>
  <thead><tr><th>战场</th><th>稳态<br>段数</th><th>首轮<br>段数</th><th>稳态<br>%/轮</th><th>首轮<br>%/轮</th>
    <th>软/中/硬</th><th>首击</th><th>聚焦<br>段数</th><th>最近命中物</th></tr></thead>
  <tbody>__CMP__</tbody>
</table>
<p class="cn">均为各战场 ① 号点；单发口径（主控一人），聚焦列为火力聚焦时的 5 人合计。</p>

__BODY__

<footer>
  数据链路：拆包 <code>core_catalog.sqlite → chunk_file_map → store.cdb.idx → adb dd → zstd → UnityFS</code>
  （UnityPy）→ 原生装配 JSON → glTF → three.js 按实机相机渲染。<br>
  未计入：敌人本体（只算场景可破坏物）、静态物遮挡、武器射程与单发伤害、击杀奖励能量（kill_m/e/c/b 另计）。<br>
  排序脚本 <code>数据/scan_px.py</code>（v10 像素级：相机深度图 → 逐像素枪口角 → 角度域段数 → 方框腐蚀求稳定半径
  → 屏幕像素 NMS &lt;50px / &gt;72px + 命中集 Jaccard &lt; 0.5），
  出图 <code>数据/viewer/fp.html</code> + <code>shoot_fp.sh</code>。<br>
  004 入选点最少：该战场全画面稳态上限就是 2 段（可破坏物 119 件、软质占多数），
  满足「稳态 ≥2 段 + 屏幕间距」的像素只有个位数 —— 不是脚本截断，是候选真的用完。
</footer>

<style>
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:10px 0 14px}
  .grid2 figure.blk{margin:0;background:#0f1a17;border:1px solid #1e332c;border-radius:10px;overflow:hidden}
  .grid2 figure.blk img{width:100%;display:block}
  .grid2 figcaption{padding:10px 12px;font-size:13px;line-height:1.65;color:#b9cdc4}
  .grid2 figcaption b{color:#e6f5ee}
  .grid2 .live{display:inline-block;margin-top:6px;color:#5fd2a4;text-decoration:none}
  @media (max-width:900px){.grid2{grid-template-columns:1fr}}
</style>
<h2>Boss 战场：35 章的 boss 关用的是哪一张</h2>
<p class="lead">第 35 章只有一条 Boss 关 —— <code>6035044</code>（Hard 镜像 <code>7035044</code>，剧本 <code>d_main_35_09_s</code>，
monster_id <code>13100101</code>）。沼泽区域有两个 boss 背景包，客户端里<b>没有 stage → 背景的映射表</b>
（<code>CampaignStageTable</code> 只给服务端下发的 <code>spot_id</code>，<code>campaignlevelmapgroup</code> 里只有 <code>_stageId</code>），
所以两张都还原了，按你实机看到的形状对一下。</p>

<div class="grid2">
  <figure class="blk">
    __IMG_B8__
    <figcaption><b>sbg_swamplandjunglebbg008</b> —— 开阔水面 + 中央植被小岛，远处城市天际线。
      219 物件 / 16,792 三角面 / 受击体 28 件。
      <b>全画面没有 ≥2 段的共线</b>：28 件受击体散布在岛与水面上，没有任何一条射线能连穿两件 ——
      这张图基本只能靠打敌人本体充能。
      <a class="live" href="http://127.0.0.1:8899/viewer/index.html?arena=bbg008" target="_blank">三维查看 ↗</a></figcaption>
  </figure>
  <figure class="blk">
    __IMG_B9__
    <figcaption><b>sbg_swamplandjunglebbg009</b> —— 两侧山脊、枯树、浅水沼泽。
      291 物件 / 32,700 三角面 / 受击体 73 件，<b>有 6 个达标点</b>，最高稳态 4 段
      （<code>px(242,350)</code>，50.2m，五阵位全可用，锥宽 5px 以内）。
      审计 S0 / A1 / B4 / C0 / D1。
      <a class="live" href="http://127.0.0.1:8899/viewer/index.html?arena=bbg009" target="_blank">三维查看 ↗</a></figcaption>
  </figure>
</div>

<p class="lead">两张都以 <code>../导出/assembly_bbg00X.json</code> 原生装配、五阵位与 001~005 完全同一套布局
（root ±5.40 / ±2.70 / 0.00），点位用的是同一套像素级算法。</p>

</div>

<script>
// 点位数量切换：所有表格行 / 明细块都带 data-no，超过 N 的直接隐藏
(function () {
  var cur = 5;
  var btns = [].slice.call(document.querySelectorAll('.nbar button[data-n]'));
  function apply(n) {
    cur = n;
    [].forEach.call(document.querySelectorAll('[data-no]'), function (el) {
      el.style.display = (+el.dataset.no <= n) ? '' : 'none';
    });
    btns.forEach(function (b) { b.classList.toggle('on', +b.dataset.n === n); });
  }
  btns.forEach(function (b) { b.addEventListener('click', function () { apply(+b.dataset.n); }); });

  // ---- 机位切换：换的是相机位置，图和点位表成套换 ----
  var cvbtns = [].slice.call(document.querySelectorAll('.nbar button.cv'));
  function setCover(v) {
    [].forEach.call(document.querySelectorAll('.cvwrap'), function (el) {
      el.classList.toggle('cv-on', el.dataset.cv === v);
    });
    cvbtns.forEach(function (b) { b.classList.toggle('on', b.dataset.cv === v); });
  }
  cvbtns.forEach(function (b) {
    b.addEventListener('click', function () { setCover(b.dataset.cv); });
  });
  var CVKEY = { q: 'cover_1', w: 'cover_2', e: 'cover_3', r: 'cover_4', t: 'cover_5' };
  window.addEventListener('keydown', function (e) {
    var v = CVKEY[(e.key || '').toLowerCase()];
    if (v) setCover(v);
  });
  setCover('cover_3');                 // 游戏进图默认站在 3 号位
  window.addEventListener('keydown', function (e) {
    var i = {'1': 0, '2': 1, '3': 2, '4': 3}[e.key];
    if (i !== undefined && btns[i]) btns[i].click();
  });
  apply(cur);

  // ---- 按掩体筛选：选中后重排 + 标出这一列 + 打不到的行降权 ----
  var sbtns = [].slice.call(document.querySelectorAll('.nbar button.slot'));
  function segOf(tr, k) {
    var cs = tr.querySelectorAll('td.c');
    if (!cs.length) return -1;
    var t = (cs[k - 1] || {}).textContent || '';
    return t.trim() === '' ? -1 : (+t || 0);
  }
  function pick(k) {
    sbtns.forEach(function (b) { b.classList.toggle('on', +b.dataset.s === k); });
    // 图上的圆点也跟着变：该阵位打不出去的点标灰划掉，只够 1 段的半透明
    [].forEach.call(document.querySelectorAll('.dmk .dm'), function (m) {
      var ss = (m.dataset.ss || '').split(',');
      var v = k > 0 ? (+ss[k - 1] || 0) : -1;
      m.classList.remove('off', 'faint');
      if (k > 0) {
        if (v === 0) m.classList.add('off');
        else if (v < 2) m.classList.add('faint');
      }
    });
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
          return a._oi - b._oi;          // 同段数保持原顺序
        });
      } else {
        rows.sort(function (a, b) { return a._oi - b._oi; });   // 复原
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

    page = (page.replace("__BEST__", best)
            .replace("__STPCT__", "%.1f" % t["steady_pct"])
            .replace("__NPTCT__", "%.1f" % t["pct"])
            .replace("__ST__", str(t["n_steady"])).replace("__N__", str(t["n"]))
            .replace("__NP__", "%d~%d" % (min(len(data[a]["points"]) for a in ARENAS),
                                          max(len(data[a]["points"]) for a in ARENAS)))
            .replace("__CMP__", "\n".join(cmp_rows)).replace("__BODY__", body)
            .replace("__BANDS__", band_table(load_bands()))
            .replace("__IMG_B8__", cover_imgs("bbg008", "bbg008 boss 战场"))
            .replace("__IMG_B9__", cover_imgs("bbg009", "bbg009 boss 战场"))
            .replace("__CF__", CFSEC.replace("__TABLE__", cf_table))
            .replace("__ROT__", ROTSEC.replace("__TABLE__", rot_table)))

    # v12 独立审计节
    ABODY, ACSS, _st = audit_html.build(
        [(a, "沼泽丛林 %s" % a) for a in ARENAS])
    if ABODY:
        page = page.replace("</style>", ACSS.replace("<style>", "") + "\n</style>")
        page = page.replace("__AUDIT__", ABODY)
    else:
        page = page.replace("__AUDIT__", "")

    out = os.path.join(ROOT, "..", "H35沼泽丛林玩家视角充能点.html")
    open(out, "w", encoding="utf-8").write(page)
    print("->", out, len(page))


if __name__ == "__main__":
    main()
