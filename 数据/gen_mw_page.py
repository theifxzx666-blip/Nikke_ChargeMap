# -*- coding: utf-8 -*-
"""生成《H39-40 母鲸领域 玩家视角充能点》汇总页。

与 H36-35（沼泽丛林）同一条渲染/扫描链路，差异只在数据：
  · 母鲸领域全域没有 soft 受击点（只有 medium 500 / hard 1000）→ 稳态 = 首轮
  · 单点段数上限 4（沼泽是 6），因为物体是分散的管线/机械，横向错位、难共线
  · 大量目标低于枪口，俯角要到 −18°，故扫描范围扩到 pitch ∈ [−22, +22]
"""
import json, os, html

import audit_html

ROOT = os.path.dirname(os.path.abspath(__file__))
ARENAS = ["mw001", "mw002", "mw003"]
CHAP = {"mw001": "39 章", "mw002": "40 章", "mw003": "备用"}

FT = {"不掉段": "keep", "高稳态": "hi", "近景": "near", "远景": "far", "全阵位": "all"}


def esc(s):
    return html.escape(str(s))


def short(name):
    return name.replace("sbg_motherwhalefield_", "")


def load():
    out = {}
    for a in ARENAS:
        for name in ("px_%s.json" % a, "fp_%s.json" % a):   # v10 像素级优先
            q = os.path.join(ROOT, "导出", name)
            if os.path.exists(q):
                out[a] = json.load(open(q, encoding="utf-8"))
                break
    return out


def load_audit():
    out = {}
    for a in ARENAS:
        p = os.path.join(ROOT, "导出", "audit_%s.json" % a)
        if os.path.exists(p):
            out[a] = {r["no"]: r for r in json.load(open(p, encoding="utf-8"))["rows"]}
    return out


def load_bands():
    p = os.path.join(ROOT, "导出", "yaw_bands_mw.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def band_table(bands, data):
    if not bands:
        return ""
    heads = "".join("<th>%+.0f~%+.0f°</th>" % (b["lo"], b["hi"]) for b in bands[ARENAS[0]])
    rows = []
    for a in ARENAS:
        cells = []
        for b in bands[a]:
            st = b["steady"]
            cells.append('<td class="s%d">%d<i>%d件</i></td>' % (min(st, 4), st, b["nobj"]))
        rows.append('<tr><td class="no"><b>%s</b><i>%s</i></td>%s</tr>'
                    % (a, CHAP.get(a, ""), "".join(cells)))
    return ('<table class="hm"><thead><tr><th>战场</th>%s</tr></thead><tbody>%s</tbody></table>'
            % (heads, "".join(rows)))


def conf_cell(p):
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


def arena_block(a, d, au=None):
    pts = d["points"]
    au = au or {}
    top = pts[0]
    rows = []
    for p in pts:
        m = p["mix"]
        ps = p.get("per_slot_steady") or p["per_slot"]   # v12：用稳态段数，与表头口径一致
        # v12：c1~c5 已扣除「被自家/相邻掩体挡住」
        per = "".join(
            ('<td class="c zero" title="该阵位被掩体挡住，打不出去">0</td>'
             if ps.get("cover_%d" % i, 0) == 0 else
             '<td class="c%s">%d</td>'
             % (" hot" if ps.get("cover_%d" % i, 0) >= 4 else "",
                ps.get("cover_%d" % i, 0)))
            for i in range(1, 6))
        tags = "".join('<i class="ft %s">%s</i>' % (FT.get(t, ""), esc(t))
                       for t in p.get("tags", [])) or '<i class="ft">—</i>'
        rc = au.get(p["no"]) or {}
        cy, cp_ = rc.get("cone_yaw"), rc.get("cone_pitch")
        if cy is None:
            cone_td = ('<td class="d">±%dpx</td>' % p["rad"]) if p.get("rad") is not None \
                else '<td class="d">—</td>'
        else:
            cone_td = ('<td class="cone %s"><b>%.1f</b><s>%.1f</s></td>'
                       % ("narrow" if min(cy, cp_) < 2.5 else "", cy, cp_))
        rows.append(
            '<tr class="%s" data-no="%d"><td class="no"><b>%d</b></td>'
            '<td class="seg">%d</td><td class="pct">%.1f%%</td>'
            '<td class="mix"><i class="s">%d</i><i class="m">%d</i><i class="h">%d</i></td>'
            '<td class="d">%.0fm</td>%s<td class="cf">%s</td>'
            '<td class="d">%d</td><td class="tags">%s</td>%s</tr>'
            % ("minor" if p["no"] > 5 else "", p["no"], p["no"], p["n"], p["pct"],
               m["soft"], m["medium"], m["hard"], p["first"],
               cone_td, conf_cell(p), p["total"], tags, per))

    detail = []
    for p in pts:
        lis = "".join('<li><span class="tag %s">%s</span>%s<i>%dm</i></li>'
                      % (h["grp"], h["grp"][0].upper(), esc(short(h["name"])), h["d"])
                      for h in p["detail"])
        detail.append('<div class="dt" data-no="%d"><div class="dth">%d 号 · %d 段 · %d 件（中 %d / 硬 %d）</div>'
                      '<ol>%s</ol></div>'
                      % (p["no"], p["no"], p["n"], len(p["detail"]), p["mix"]["medium"], p["mix"]["hard"], lis))

    return """
<section class="ar" id="a{a}">
  <div class="ah">
    <h3>战场 <span>{a}</span> <em>{chap}</em></h3>
    <div class="badge">最强点 <b>{st}</b> 段 · <b>{pct:.1f}%</b> / 轮 · {shots} 轮充满</div>
    <a class="live" title="需先运行 启动战场查看器.bat（本地服务 8899）"
       href="http://127.0.0.1:8899/viewer/fp.html?arena={a}" target="_blank">打开可交互视图 ↗</a>
  </div>
  <figure>
    <a href="数据/render/fp_{a}.png" target="_blank"><img src="数据/render/fp_{a}.png" alt="战场 {a} 玩家视角"></a>
    <figcaption>机位 cover_3 的 <code>camera_position</code> = ({cx}, 0.00, {cz}) ·
      视高 2.34m（地面 y = −2.34）· 沿 +z · 竖直 FOV 60° · 角色位于画面底部</figcaption>
  </figure>
  <table class="tg">
    <thead><tr>
      <th>号</th><th>段数</th><th>%/轮</th><th>软/中/硬</th>
      <th>首击</th><th>容错 px<br>横/纵</th><th>可信度</th><th>聚焦<br>段数</th><th>特性</th>
      <th>c1</th><th>c2</th><th>c3</th><th>c4</th><th>c5</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {rot}
  <p class="cn"><b>段数</b> = 单发穿透的可破坏物件数（主控一人，每段 2.8% 爆裂条）；此区域没有软质受击点，
    所以段数不会随碎裂下降。<b>聚焦</b> = 小美人鱼火力聚焦下 5 人合计。<br>
    <b>容错 横/纵</b>（v12 实测，绕开相机）：准星偏多少像素还能保住标称段数。
    横向大、纵向小是常态；<b>纵向 &lt;2.5px 的标红</b>，那是「能打中但稳不住」。<br>
    <b>c1~c5</b> = 各阵位单发段数，<b>红色的 0 = 那个阵位被自家或相邻高掩体挡住</b>（这一版修掉了原先漏算遮挡的问题）。<br>
    <b>①~⑤ 首选</b>，<b>⑥ 起为补充</b>（左侧竖线）：换了阵位、被挡住时可以顶上；
    页面顶部可切换「显示几个」。</p>
  <details><summary>展开 {np_} 个点的逐件命中明细</summary>{detail}</details>
</section>""".format(
        a=a, chap=CHAP.get(a, ""), st=top["n"], pct=top["pct"], shots=top["shots"],
        cx=("%.1f" % d["cam"][0]), cz=("%.1f" % d["cam"][2]),
        rows="".join(rows), detail="".join(detail), np_=len(pts), rot=rot_line(d))


ROTSEC = """<h2>V11：单点段数不是目标，「能凑够一条」才是</h2>
<p class="body">V10.5 把每个点拆开评估。但爆裂条是一条 100% 的共享进度条，单点再强也只贡献一次。
    受击物碎掉就从场景消失，而且<b>跨点位共享</b> —— A 打碎的件，B 就打不到。所以点位必须按一条
    <b>轮换路径</b>来算，而不是各自独立的分数。</p>
<div class="note">
  <b>这里只有一件不确定的事，但它决定一切</b>
  <p class="body" style="margin:6px 0">本区域没有 soft，只有 medium 500 / hard 1000。每次命中扣多少血取决于
    <code>hpdamage_limit=30</code>，表里没写，两种都合法：</p>
  <ul>
    <li><b>A · 无上限</b>：单发伤害远超 1000 → 一枪打穿的全部碎 → <b>每个点只能用 1 发</b></li>
    <li><b>B · 上限 30</b>：每发最多扣 30 → medium 17 发、hard 34 发才碎 → <b>单点能撑 17 发</b></li>
  </ul>
</div>
<p class="body">母鲸领域的目标几乎全在 12~30m 的管线串上，一条线串 3~4 件很常见 ——
    这让<b>单发收益高</b>，但也让<b>点位之间高度重叠</b>（都打同一批管线）。下表给出可破坏物池，
    池子 × 280 就是这张图靠打地形能拿到的上限。</p>
__TABLE__
<div class="note">
  <b>三条结论</b>
  <ul>
    <li><b>可破坏物池只有 0.64~1.01 条</b>。mw001 池子 23 件 = 64%，光靠打地形连一半都拿不到；
      mw003 刚好 36 件 = 101%。<b>所以「打完就没充能了」不是找错点，是这张图的目标总量本来就不够。</b></li>
    <li><b>覆盖率只有 35%~57%</b>：场景里 63~65 件可破坏物，点位只碰到了 23~36 件。
      因为 15~24 个点几乎全压在右侧或左侧同一片管线上。想提高总充能，该<b>换方向扩大覆盖</b>，
      而不是在同一个方向上继续找更强的单点。</li>
    <li><b>按「单点段数」排序不是最优</b>：同样的点只换顺序（贪心按边际覆盖选下一点），
      mw001 从 14 发降到 12 发、mw003 从 19 发降到 17 发。<b>重叠的点排在前面会浪费。</b></li>
  </ul>
</div>

"""

MWSEC = '''__ROT__\n\n<h2>v10.5：每个点给一个可信度</h2>
<p class="body">4 段 / 3 段是<b>一组假设下的确定解</b>：相机在 <code>camera_position</code>、俯角 0、
    角色正好站在阵位中心、枪口高 1.45m。这些里有一半是推断。做法是<b>把同一颗目标重打 300 次</b>，
    每次随机抖站位（±0.30m）、枪口高度（±0.15m）、手抖（±2~4px）、后坐（0.12°）、几何（1.5px），
    走完整链路后看还剩几段 —— 得到的是分布，不是一个数。</p>
<p class="body"><b>可信度 = 100 × (0.60·达标率 + 0.25·可用率 + 0.15·P10/标称)</b>；
    <span class="gr A">A</span> ≥80 可直接照打、<span class="gr B">B</span> ≥68 偶尔掉 1 段、
    <span class="gr C">C</span> ≥52 条件性可用、<span class="gr D">D</span> &lt;52 不建议依赖。
    表格里的「达标率」= 300 次里仍拿到标称段数的比例，「均 X 段」= 期望段数。</p>
__TABLE__
<div class="note">
  <b>母鲸领域的特点</b>：目标几乎全在 12~30m（<code>pipeline</code> 管线串），
  一条线上串 3~4 件很常见，<b>但串得越长越吃站位</b> —— 3 段的达标率明显高于 4 段。
  另外全区域软质为 0，所以「稳态 = 首轮」，打碎了不影响的优势在这里用不上。
</div>

'''

def main():
    data = load()
    AUDIT = load_audit()
    best = max(ARENAS, key=lambda a: (data[a]["points"][0]["n"], data[a]["points"][0]["total"]))
    t = data[best]["points"][0]

    cmp_rows = []
    for a in ARENAS:
        p = data[a]["points"][0]
        m = p["mix"]
        cmp_rows.append(
            '<tr><td class="no"><b>%s</b><i>%s</i></td><td class="seg">%d</td><td class="pct">%.1f%%</td>'
            '<td class="mix"><i class="s">%d</i><i class="m">%d</i><i class="h">%d</i></td>'
            '<td class="d">%.0fm</td><td class="d">%d</td><td class="nm">%s</td></tr>'
            % (a, CHAP.get(a, ""), p["n"], p["pct"], m["soft"], m["medium"], m["hard"],
               p["first"], p["total"], esc(short(p["detail"][0]["name"]))))

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
            '<td class="hl">%.0f%%<s>%d / %d 件</s></td>'
            '<td class="hl %s">%.0f%%</td>'
            '<td class="d">%d 发</td>'
            '<td class="d">%d 发 <s style="font-size:10px;color:var(--tx3)">/ %d 点</s></td>'
            '<td class="hl %s">%s</td></tr>'
            % (a, fs["n_points"], fs["pool"], cov, fs["pool"], tot_obj,
               "warn" if fs["pool_pct"] < 100 else "",
               fs["pool_pct"],
               A["shots"], B["shots"], B["pts"],
               "warn" if gA > 0 else "",
               ("-%d 发" % gA) if gA > 0 else "—"))
    rot_table = ('<table class="tb rt"><thead><tr>'
                 '<th>战场</th><th>点位</th><th>池子<br>件数</th><th>覆盖率</th>'
                 '<th>池子<br>=充能</th><th>A 一枪碎</th><th>B 上限 30</th>'
                 '<th>贪心<br>省</th></tr></thead><tbody>%s</tbody></table>'
                 '<p class="cn" style="text-align:center;font-size:11px">A 模式每个点只用 1 发，'
                 '所以「发数 = 点数」；B 模式才需要看点位数。</p>' % "".join(rt))
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
        p0 = d["points"][0]; vf = d.get("verify", {})
        cf_rows.append(
            '<tr><td class="no"><b>%s</b></td><td class="cf">%s</td><td class="cf"><b>%d%%</b></td>'
            '<td class="cf" style="min-width:96px"><div class="cfbar">%s</div>'
            '<s style="font-size:10px;color:var(--tx3)">A%d B%d C%d D%d</s></td>'
            '<td class="cf">%d 号 <b>%.0f</b><s>%s</s></td>'
            '<td class="d" style="font-size:11px;color:var(--tx3)">%d 次 · %.0fs</td></tr>'
            % (a, conf_cell(p0), round(p0["sim"]["follow"]["hit_rate"] * 100), seg,
               sm.get("A", 0), sm.get("B", 0), sm.get("C", 0), sm.get("D", 0),
               top["no"], top.get("conf", 0), top.get("grade", "-"),
               vf.get("n_sim", 0), vf.get("secs", 0)))
    n_all = max(1, sum(tot.values()))
    cf_sum = ('<tr style="border-top:2px solid var(--bd2)"><td class="no"><b>合计</b></td>'
              '<td class="cf">—</td><td class="cf">—</td>'
              '<td class="cf"><div class="cfbar">%s</div>'
              '<s style="font-size:10px;color:var(--tx3)">A%d B%d C%d D%d</s></td>'
              '<td class="cf">—</td><td class="d">—</td></tr>'
              % ("".join('<i class="g%s" style="width:%.1f%%"></i>' % (g, 100.0 * tot[g] / n_all)
                         for g in ("A", "B", "C", "D")),
                 tot["A"], tot["B"], tot["C"], tot["D"]))
    cf_table = ('<table class="tb"><thead><tr><th>战场</th><th>① 可信度</th><th>① 达标率</th>'
                '<th>等级分布</th><th>本图最稳的点</th><th>模拟量</th></tr></thead><tbody>%s%s</tbody></table>'
                % ("".join(cf_rows), cf_sum))
    body = "\n".join(arena_block(a, data[a], AUDIT.get(a)) for a in ARENAS)

    page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>H39-40 母鲸领域 · 玩家视角充能点</title>
<style>
  :root{
    --bg:#070d11; --pan:#0d161c; --bd:#1c3542; --bd2:#2a4b5c;
    --tx:#dbeaf1; --tx2:#9bb8c6; --tx3:#6d8d9c; --gold:#ffcf6b; --mint:#7fe3b4;
    --red:#ff9d8a; --yel:#e8c96a;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:var(--bg);color:var(--tx);
    font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.65;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:1180px;margin:0 auto;padding:44px 26px 80px}
  header.top{border-bottom:1px solid var(--bd);padding-bottom:26px}
  .kicker{color:var(--tx3);font-size:11.5px;letter-spacing:2.2px;text-transform:uppercase}
  h1{font-size:31px;font-weight:600;letter-spacing:.6px;margin:9px 0 12px}
  h1 span{color:var(--gold)}
  .lead{color:var(--tx2);font-size:14px;max-width:860px}
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
  td{padding:7px;border-bottom:1px solid #10202a;color:var(--tx2)}
  td.no{width:52px}td.no b{color:var(--gold);font-size:14px}
  td.no i{display:block;font-style:normal;font-size:9.5px;color:var(--tx3)}
  td.seg{color:#eafaf1;font-weight:600;font-size:14px}
  td.pct{color:var(--mint)}
  td.d{color:var(--tx3)}
  td.mix i{font-style:normal;display:inline-block;min-width:17px;text-align:center;
    border-radius:3px;font-size:10px;margin-right:3px;padding:0 3px}
  td.mix i.s{background:#26343b;color:#9fb6c0}
  td.mix i.m{background:#3d3620;color:var(--yel)}
  td.mix i.h{background:#42231f;color:var(--red)}
  td.c{text-align:center;color:var(--tx3);width:34px}
  td.c.hot{color:var(--gold);font-weight:600}
  td.c.zero{color:#ff5a45;font-weight:700;background:#2a1512}
  .nbar .sep{width:1px;height:16px;background:var(--bd2);margin:0 3px}
  .nbar button.slot{min-width:30px;padding:3px 8px}
  tr.dim{opacity:.42}
  tr.dim td.seg{color:#7a4a42}
  tr.dim td.no b{color:#8a6259}
  td.c.sel{background:#12281f;box-shadow:inset 0 0 0 1px #2f6b52;color:#bfe6d2}
  td.c.sel.hot{color:var(--gold)}
  tr.dead td{text-decoration:line-through;text-decoration-color:#5a3128}
  td.cone{white-space:nowrap;font-size:12.5px}
  td.cone b{font-weight:600;color:var(--mint)}
  td.cone s{text-decoration:none;color:var(--tx3);font-size:11px;margin-left:3px}
  td.cone.narrow b,td.cone.narrow s{color:#ff9d8a}
  td.nm{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--tx3)}
  td.tags{white-space:nowrap}
  .ft{font-style:normal;display:inline-block;font-size:10px;line-height:1.5;border-radius:3px;
    padding:0 4px;margin-right:3px;background:#152128;color:var(--tx3)}
  .ft.keep{background:#16352a;color:#8ce0b6}
  .ft.hi{background:#332c15;color:var(--gold)}
  .ft.near{background:#1b2d33;color:#88c4d4}
  .ft.far{background:#241f33;color:#b0a4dd}
  .ft.all{background:#2a2418;color:#d8c48a}
  tr.minor td.no b{color:var(--tx3);font-weight:500}
  tr.minor td.seg{color:#cfe3d8;font-weight:500}
  tr.minor td.no{border-left:3px solid #1a3040}
  table.hm{font-size:12px;margin:16px 0 4px}
  table.hm th{text-align:center;padding:7px 4px}
  table.hm td{text-align:center;padding:9px 4px;font-weight:600;font-size:13.5px;
    border:1px solid var(--bg);border-radius:0}
  table.hm td.no{text-align:left;font-family:ui-monospace,Consolas,monospace;
    font-size:12.5px;color:var(--tx);background:none}
  table.hm td i{display:block;font-style:normal;font-weight:400;font-size:10px;opacity:.72;margin-top:1px}
  table.hm td.s1{background:#122c34;color:#8cd4e0}
  table.hm td.s2{background:#1b4d5c;color:#d8f4fa}
  table.hm td.s3{background:#26738c;color:#eafbff}
  table.hm td.s4{background:#4fb6d4;color:#04232c}
  table.hm td.s0{background:#172229;color:#5f7a86}
  .ar{margin-top:52px;background:var(--pan);border:1px solid var(--bd);border-radius:14px;
    padding:22px 22px 26px}
  .ah{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:14px}
  .ah h3{font-size:16px;font-weight:600;color:#eafaf1}
  .ah h3 span{color:var(--gold);font-family:ui-monospace,Consolas,monospace}
  .ah h3 em{font-style:normal;font-size:11.5px;color:var(--tx3);margin-left:6px}
  .badge{font-size:12px;color:var(--tx2);background:#0a1218;border:1px solid var(--bd2);
    border-radius:20px;padding:4px 13px}
  .badge b{color:var(--gold)}
  .live{margin-left:auto;font-size:11.5px;color:var(--mint);text-decoration:none;
    border:1px solid #2b4d40;border-radius:6px;padding:4px 10px}
  .live:hover{background:#122430}
  figure{margin:0 0 6px}
  figure img{width:100%;display:block;border-radius:9px;border:1px solid #16262f}
  figcaption{font-size:11px;color:var(--tx3);margin-top:7px}
  .cn{font-size:11.5px;color:var(--tx3);margin-top:4px}
  .cn b{color:var(--tx2);font-weight:600}
  details{margin-top:12px;border-top:1px solid #10202a;padding-top:10px}
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
  p.rot{margin:10px 0 2px;padding:9px 12px;background:#0c1613;border-left:2px solid #38614a;
    border-radius:0 6px 6px 0;font-size:12px;color:var(--tx2);line-height:1.65}
  p.rot b{color:#bfe6d2;font-weight:600}
  p.rot b.warn{color:#d9b56a}
  table.tb.rt{width:auto;margin:14px auto 6px;font-size:12px}
  table.tb.rt th{white-space:normal;text-align:center;padding:8px 14px}
  table.tb.rt th:first-child{white-space:nowrap;min-width:58px}
  table.tb.rt td{padding:7px 13px}
  table.tb.rt s{text-decoration:none;font-style:normal}
  table.tb.rt td.hl{color:#7fe3b4;font-weight:600;font-size:13px;text-align:center;white-space:nowrap}
  table.tb.rt td.hl.warn{color:#d9b56a}
  table.tb.rt td.hl s{display:block;margin-top:1px;font-weight:400;line-height:1.3}
  table.tb.rt td.d{text-align:center;white-space:nowrap}
  table.tb.rt td.no{border-left:none}
  code{background:#101b21;border:1px solid #1b2f38;border-radius:4px;padding:1px 5px;
    font-size:11px;color:var(--mint)}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="kicker">NIKKE · H39-40 · motherwhalefield 母鲸领域 · 拆包实测</div>
  <h1>第 39 / 40 章 · <span>玩家视角充能点</span></h1>
  <p class="lead">机位取自 <code>cover_3.camera_position</code>（角色身后 4.5m、视高 2.34m、沿 +z、FOV 60°），
    图里 ①~⑤ 是首选、其后是补充（默认显示 5 个，可切到全部）。这个区域和沼泽丛林（H36-35）有三处实打实的区别，都改了口径。</p>
  <div class="kv">
    <div>最强战场<b>__BEST__<i>（__CHAP__）</i></b></div>
    <div>单发最深<b>__SEG__<i>段 · __PCT__% / 轮</i></b></div>
    <div>充满所需<b>__SHOTS__<i>轮（仅地形）</i></b></div>
    <div>可破坏物<b>__NOBJ__<i>件 / 图（中+硬）</i></b></div>
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

__AUDIT__

__CF__

<h2>v10：判定点从「角度」搬到「像素」</h2>
<p class="body">上一版在<b>枪口角度</b>上选点，隐含假设「准星指哪、枪口就打哪」。实际是
    <code>准星像素 → 相机射线 → 命中点 Pc → 枪口瞄准 Pc</code>，相机在身后 4.5m、右偏 1.2m、高 0.89m，
    与枪口不是同一点。母鲸领域目标更近（12~30m 居多），视差实测<b>中位 3.8~4.3°、最大 15.2°</b>，
    这个误差在 v9 里被整个忽略了。</p>
<div class="note">
  <b>v10 四条改动</b>
  <ul>
    <li><b>逐像素</b>：相机深度图（1600×900，Z-buffer）→ 每像素反推枪口角度 → 查角度域段数。选点在像素上做。</li>
    <li><b>稳定半径</b>：对逐像素段数图做方框腐蚀，得到 ±Rpx（准星偏 R 像素仍不掉段）。方框含半径 R 的圆 → 结论保守。</li>
    <li><b>淘汰单判</b>：稳态段数 &lt; 2 的点不进候选。</li>
    <li><b>我方掩体不作判定点</b>：掩体单独渲一张深度图，被自家掩体挡住的像素不参与（本区域掩体占掉 27~31% 像素）。</li>
  </ul>
</div>
<p class="body">遮挡也算进去了：<code>static_object</code>（不可破坏的机械/岩石）与地形会截断射线。
    这条改动的直接后果是 <b>mw002 原先那条「4 段」不成立</b> —— 它在 39.9m 打中管线后，
    40.6m 就有一台 <code>sn_machine01_01</code> 挡住，后面 3 件（54~64m）实际打不到，真实只有 1 段。</p>

<h2>和沼泽丛林不一样的三件事</h2>
<div class="note">
  <b>① 全域没有软质受击点</b>
  <ul>
    <li>三张战场的 hitbox 分组只有 <b>hard 1000 / medium 500</b>，<b>soft 一件都没有</b>（沼泽丛林有大量树丛是 soft 100）。</li>
    <li>后果：不会出现「首轮 6 段、碎完只剩 2 段」的落差，<b>段数从开局到结束不变</b>，不用中途换点。</li>
    <li>所以表里只报一个段数，不再拆首轮/稳态。</li>
  </ul>
</div>
<div class="note">
  <b>② 段数上限是 4，不是 6</b>
  <ul>
    <li>这里的目标是<b>管线、机械、集装箱</b>，散落在甲板上，横向前后错位；沼泽丛林远景那排是竖直面板墙，射线能和面板共线一穿一排。</li>
    <li>实测：001 最高 4 段、002 最高 4 段、003 最高 4 段。画面上「一串能穿 4 件」的角度已经是最优。</li>
    <li>4 段 × 2.8% = <b>11.2% / 发</b>，约 90 发充满；沼泽最强点是 6 段 16.8%。这不是图错了，是这张图的目标确实没排成串。</li>
  </ul>
</div>
<div class="note">
  <b>③ 很多目标低于枪口，俯角能到 −18°</b>
  <ul>
    <li>沼泽丛林的目标都立在远处抬升的地面上，扫描范围是 <code>pitch −3~+20</code> 就够。</li>
    <li>母鲸领域是<b>甲板 + 下层机械</b>，65 件里有 12~22 件的中心低于枪口线，最陡要俯到 −18°（001 的 ④ 号点）。</li>
    <li>扫描范围因此扩到 <code>pitch −22~+22</code>，否则下层机械整片扫不到。</li>
  </ul>
</div>

<h2>另一件事：boss 变体场景没有地形可打</h2>
<div class="note">
  <b>母鲸领域还有一个 <code>sbg_motherwhalefieldbmf002_001</code> 场景（bmf = boss mother field）。</b>
  <ul>
    <li>67 个物体里，<b>可破坏物 0 个</b>：47 个 <code>noncol_object</code>（装饰）、15 个 <code>cover_object</code>（自家掩体）、5 个 ground。</li>
    <li>也就是说这个场景<b>不存在「打地形充能」这回事</b>，充能只能来自命中敌人本体与击杀奖励（<code>kill_m/e/c/b</code>）。</li>
    <li>本页的三张图是普通作战场景，均有 63~65 件中/硬目标，可以打地形。</li>
  </ul>
</div>

<h2>一处筛选修正：①右边那条管线，本来该标出来</h2>
<p class="body">有用户反馈：①（yaw −40°）右边那条横向管线上也能充能，速率还可以。反查属实 ——
    该方向 <b>yaw −34.5° / pitch +6.0°</b>，单发 <b>3 段（8.4%）</b>、首击 48.5m，命中
    <code>dm_pipeline_106_06_h</code> + <code>dm_machine02_h</code> + <code>dm_pipeline_12_01_h</code> 三件硬质，
    五阵位齐射 12 段。v10 复算后它是本图的 <b>⑩</b>（<code>px(297, 388)</code>，±2px），
    因为点数默认只显示 5 个，要把顶部切到「12 个」才看得到它。</p>
<div class="note">
  <b>之前漏掉它，是三道筛选在误杀，不是这个点不合格：</b>
  <ul>
    <li><b>候选池 2° 粗去重（先到先得）</b> —— 旁边的 −33.5/+5.1 先入池，它在 1.19° 内被直接跳过。
      粗去重降到 <b>0.75°</b>，只防同一格重复计算。</li>
    <li><b>候选池只按「窗口稳健值」排序</b> —— 它的 3 段只在 1° 窗口内成立，1° 外掉到 1~2 段，
      按稳健值排不进前 320 格。改为按<b>稳态段数</b>全量枚举（上限 4000 格）。</li>
    <li><b>角距阈值 6°</b> —— 它与 ① 差 5.77°、纵深只差 3.2m，被判成重复。阈值降到 <b>4°</b>；
      3°~4° 这个区间才要求「纵深差 ≥15m」。</li>
  </ul>
</div>
<p class="body">修正后每张图从 10 个点增到 <b>12</b> 个，沼泽丛林（H36-35）的五张同样重跑。
本图新增的 ⑪（−34.5/+6.0，48.5m）与 ⑫（−30.75/+6.0，31.2m）正好是「同方位、不同纵深」的一对：
一个打远处管线串、一个打近处管件，命中集合只重叠 1 件 —— 以前被当成同一个点，其实两条都该标。</p>

<h2>点位分布（水平 15° 分带）</h2>
<p class="body">数字是该区间内能做到的最高段数，小字是区间内的可破坏物件数。这个区域的点位分布比沼泽丛林散得多 ——
    左右两侧都有 4 段的带，不像沼泽丛林集中在中央。</p>
__BANDS__
<p class="cn">覆盖 ±45°，即整块屏幕（水平半角 45.7°）。</p>

<h2>机位与参数（全部拆包，非估计）</h2>
<table>
  <thead><tr><th>项</th><th>取值</th><th>来源</th></tr></thead>
  <tbody>
    <tr><td>区域</td><td>motherwhalefield</td><td>CampaignChapterTable：39 章 → <code>fcbg_motherwhalefield_001</code>，40 章 → <code>_002</code></td></tr>
    <tr><td>战场场景</td><td><code>sbg_motherwhalefield_001 / 002 / 003</code></td><td><code>core/chunk/store.cdb</code> 定点提取</td></tr>
    <tr><td>机位 / 朝向</td><td>cover_N 的 <code>camera_position</code>；rotation = identity（沿 +z，俯仰 0°）</td><td>阵位预制体，5 阵位布局与沼泽丛林完全一致</td></tr>
    <tr><td>视高 / 后撤</td><td>y = 0（地面 −2.34）→ 2.34m；角色在 z + 4.5、右偏 1.2m</td><td>camera_position vs character_position</td></tr>
    <tr><td>竖直视场</td><td>60°（near 0.1 / far 300）</td><td><code>spotcameracontrol</code></td></tr>
    <tr><td>扫描范围</td><td>yaw ±46°，pitch −22~+22°，步长 0.25°</td><td>按本区域目标俯角分布扩展</td></tr>
    <tr><td>每段充能</td><td>2.8%（280 能量 / 10000）</td><td><code>ulti_gauge_shot_hit</code> × burst_energy_max</td></tr>
  </tbody>
</table>

<h2>三张战场最强点横向对比</h2>
<table>
  <thead><tr><th>战场</th><th>段数</th><th>%/轮</th><th>软/中/硬</th><th>首击</th><th>聚焦<br>段数</th><th>最近命中物</th></tr></thead>
  <tbody>__CMP__</tbody>
</table>
<p class="cn">均为各战场 ① 号点。001/002 按章节顺序对应 39/40 章 —— <b>客户端没有「关卡 → 战场」映射表</b>
  （<code>spot_id</code> 由服务端下发），这一对应是推定，不是拆包实证。</p>

__BODY__

<footer>
  数据链路：<code>core_catalog.sqlite → chunk_file_map → store.cdb.idx → adb dd → zstd → UnityFS</code>（UnityPy）
  → 原生装配 JSON → glTF → three.js 按实机相机渲染。<br>
  未计入：敌人本体（只算场景可破坏物）、静态物遮挡、武器射程与单发伤害、击杀奖励能量。<br>
  排序脚本 <code>数据/scan_px.py mw</code>（v10 像素级：相机深度图 → 逐像素枪口角 → 段数 → 方框腐蚀求稳定半径
  → 屏幕像素 NMS + 命中集 Jaccard &lt; 0.5，遮挡体 = static/ground/我方掩体），
  出图 <code>数据/viewer/fp.html</code> + <code>shoot_mw.sh</code>。<br>
  战场 003 在章节表里没有对应章节（39/40 章只用到 001/002），作为区域内的第三张场景一并给出。
</footer>
</div>

<script>
(function () {
  var btns = [].slice.call(document.querySelectorAll('.nbar button[data-n]'));
  function apply(n) {
    [].forEach.call(document.querySelectorAll('[data-no]'), function (el) {
      el.style.display = (+el.dataset.no <= n) ? '' : 'none';
    });
    btns.forEach(function (b) { b.classList.toggle('on', +b.dataset.n === n); });
  }
  btns.forEach(function (b) { b.addEventListener('click', function () { apply(+b.dataset.n); }); });
  window.addEventListener('keydown', function (e) {
    var i = {'1': 0, '2': 1, '3': 2, '4': 3}[e.key];
    if (i !== undefined && btns[i]) btns[i].click();
  });
  apply(5);

  // ---- 按掩体筛选 ----
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

    nobj = "%d~%d" % (min(data[a]["n_hitbox_obj"] for a in ARENAS),
                      max(data[a]["n_hitbox_obj"] for a in ARENAS))
    page = (page.replace("__BEST__", best)
            .replace("__CHAP__", CHAP.get(best, ""))
            .replace("__SEG__", str(t["n"]))
            .replace("__PCT__", "%.1f" % t["pct"])
            .replace("__SHOTS__", str(t["shots"]))
            .replace("__NOBJ__", nobj)
            .replace("__CMP__", "\n".join(cmp_rows))
            .replace("__BANDS__", band_table(load_bands(), data))
            .replace("__BODY__", body)
            .replace("__CF__", MWSEC.replace("__TABLE__", cf_table))
            .replace("__ROT__", ROTSEC.replace("__TABLE__", rot_table)))

    ABODY, ACSS, _st = audit_html.build(
        [(a, "母鲸领域 %s" % a) for a in ARENAS])
    if ABODY:
        page = page.replace("</style>", ACSS.replace("<style>", "") + "\n</style>")
        page = page.replace("__AUDIT__", ABODY)
    else:
        page = page.replace("__AUDIT__", "")

    out = os.path.join(ROOT, "..", "H39-40母鲸领域充能点.html")
    open(out, "w", encoding="utf-8").write(page)
    print("->", out, len(page))


if __name__ == "__main__":
    main()
