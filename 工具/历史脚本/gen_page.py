# -*- coding: utf-8 -*-
"""生成 H36-35 充能点位平面标注的汇总页（原生画面 + 数据表）。"""
import json, os, html

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
EX = os.path.join(BASE, "导出")
OUT_HTML = os.path.join(ROOT, "H36-35平面标注.html")

ARENAS = ["001", "002", "003", "004", "005"]
TITLE = {"001": "沼泽丛林 · 废墟水道", "002": "沼泽丛林 · 车辆残骸",
         "003": "沼泽丛林 · 蒸汽湿地", "004": "沼泽丛林 · 密林裂谷",
         "005": "沼泽丛林 · 沉船滩涂"}

GRADE_CLS = {"硬": "g-hard", "中": "g-mid", "软": "g-soft"}


def load():
    return json.load(open(os.path.join(EX, "h36-35_scan.json"), encoding="utf-8"))


def rows(tops):
    out = []
    for i, t in enumerate(tops[:5]):
        g = t["grade"]
        gtxt = " ".join("<i class='%s'>%s×%d</i>" % (GRADE_CLS.get(k, "g-soft"), k, v)
                        for k, v in g.items())
        out.append(
            "<tr><td class='idx'>%d</td><td>x=%+.2f<br><span class='sub'>偏角 %+.1f°</span></td>"
            "<td class='num'>%d</td><td class='num'>%d</td><td class='num'>%d</td>"
            "<td class='num e0'>%d</td><td class='num e1'>%d</td><td>%s</td></tr>"
            % (i + 1, t["px"], t["yaw"], t["nHit"], t["nPt"], t["nHit"] + t["nPt"],
               t["e0"], t["e1"], gtxt))
    return "\n".join(out)


def main():
    scan = load()
    cards = []
    for a in ARENAS:
        d = scan[a]
        img = "数据/render/h36_%s_top1.png" % a
        cards.append(f"""
<section class="arena">
  <div class="ahead">
    <h2>战场 #{a} <span class="tag">{TITLE[a]}</span></h2>
    <span class="meta">物体 {len(d['props'])} 个 · 敌点位 {len(d['points'])} 个</span>
  </div>
  <a class="shot" href="{img}" target="_blank"><img src="{img}" alt="战场 {a}"></a>
  <table>
    <thead><tr>
      <th>#</th><th>建议站位</th><th>段数</th><th>敌点</th><th>合计段</th>
      <th>保底能量</th><th>理想能量</th><th>可破坏物分布</th>
    </tr></thead>
    <tbody>{rows(d['top'])}</tbody>
  </table>
</section>""")

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>H36-35 穿透充能点位 · 原生画面平面标注</title>
<style>
:root{{--bg:#0b0f0d;--panel:#121815;--line:#25322a;--tx:#dfe8e0;--dim:#8fa094;
--hard:#ff5c54;--mid:#ffb03e;--soft:#80e294;--acc:#5fd0ff}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#17201a,#0b0f0d 60%);
color:var(--tx);font:15px/1.7 "Microsoft YaHei",system-ui,sans-serif}}
header{{padding:56px 40px 28px;max-width:1360px;margin:0 auto}}
h1{{margin:0 0 10px;font-size:32px;letter-spacing:.5px}}
h1 em{{font-style:normal;color:var(--acc)}}
.lead{{color:var(--dim);max-width:900px}}
.facts{{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0 8px}}
.fact{{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:12px 16px;min-width:190px}}
.fact b{{display:block;font-size:20px;color:#fff;font-weight:700}}
.fact span{{font-size:12.5px;color:var(--dim)}}
main{{max-width:1360px;margin:0 auto;padding:16px 40px 80px}}
.arena{{background:var(--panel);border:1px solid var(--line);border-radius:14px;
padding:20px;margin-bottom:28px}}
.ahead{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:14px}}
h2{{margin:0;font-size:19px}}
.tag{{font-size:13px;font-weight:400;color:var(--dim);margin-left:6px}}
.meta{{margin-left:auto;font-size:12.5px;color:var(--dim)}}
.shot{{display:block;border-radius:10px;overflow:hidden;border:1px solid #1d2823}}
.shot img{{display:block;width:100%;height:auto}}
table{{width:100%;border-collapse:collapse;margin-top:14px;font-size:13.5px}}
th{{text-align:left;font-weight:500;color:var(--dim);border-bottom:1px solid var(--line);
padding:8px 10px;white-space:nowrap}}
td{{padding:9px 10px;border-bottom:1px solid #1a241f;vertical-align:top}}
tr:last-child td{{border-bottom:0}}
.idx{{color:var(--acc);font-weight:700}}
.sub{{color:var(--dim);font-size:12px}}
.num{{font-variant-numeric:tabular-nums}}
.e0{{color:#c9d8cc}}.e1{{color:#ffd274;font-weight:600}}
i{{font-style:normal;margin-right:6px;font-size:12.5px}}
.g-hard{{color:var(--hard)}}.g-mid{{color:var(--mid)}}.g-soft{{color:var(--soft)}}
.legend{{display:flex;gap:22px;flex-wrap:wrap;color:var(--dim);font-size:13px;margin-top:18px}}
.legend em{{font-style:normal;display:inline-block;width:10px;height:10px;border-radius:2px;
margin-right:6px;vertical-align:middle}}
footer{{max-width:1360px;margin:0 auto;padding:0 40px 60px;color:#617064;font-size:12.5px}}
code{{background:#0e1411;border:1px solid var(--line);border-radius:4px;padding:1px 6px;
font-family:Consolas,monospace;font-size:12px;color:#a9c0b0}}
</style></head>
<body>
<header>
  <h1>H36-35 <em>穿透充能点位</em> · 原生画面平面标注</h1>
  <p class="lead">底图不是示意图：每一个物体都取自游戏客户端拆包出的原始贴片
  （<code>sbg_swamplandjungle_001~005</code>），按各自的世界坐标在游戏战斗视角下重新投影合成，
  因此每个红/绿/黄括号框落在画面上的位置，就是它在你屏幕里的真实位置。
  打叉标注的是「小红帽一发穿透会依次打到的可破坏体」。</p>
  <div class="facts">
    <div class="fact"><b>10000</b><span>爆裂条总能量</span></div>
    <div class="fact"><b>280</b><span>单段能量（每命中 1 个可破坏体）</span></div>
    <div class="fact"><b>36</b><span>一发打满 10000 的段数上限</span></div>
    <div class="fact"><b>2 / 3 / 4</b><span>常见段数 → 所需发数</span></div>
    <div class="fact"><b>1.0 + 2.0s</b><span>蓄力 + 换弹（SR，弹匣 6）</span></div>
  </div>
  <div class="legend">
    <span><em style="background:#ff5c54"></em>硬 · 大幅可破坏</span>
    <span><em style="background:#ffb03e"></em>中 · 中幅</span>
    <span><em style="background:#80e294"></em>软 · 小幅（草丛/灌木）</span>
    <span><em style="background:#5fd0ff"></em>建议站位与朝向</span>
  </div>
</header>
<main>
{''.join(cards)}
</main>
<footer>
  数据链：<code>core_catalog.sqlite</code> → <code>store.cdb</code> → <code>zstd</code> → <code>UnityFS</code>
  → 贴片（Texture2D）+ 场景 AABB（MeshCollider）→ 透视投影合成。
  段数按「射线与可破坏体 AABB 求交」统计，站位扫描步长 0.25m / 朝向 0.5°。
  每段 280 能量取自社区实测口径，若与实测有偏差可用「涨幅 ÷ 2.80%」反推校准。
</footer>
</body></html>"""
    open(OUT_HTML, "w", encoding="utf-8").write(doc)
    print("->", OUT_HTML)


if __name__ == "__main__":
    main()
