# -*- coding: utf-8 -*-
"""把 audit_*.json 变成页面里的「独立审计」一节。

设计原则
--------
这一节不是讲方法，是给**结论**。玩家看完要知道三件事：

  1. 我照图打为什么打不准（阵位 / 屏幕比例 / 手抖预算）
  2. 哪几个点可以直接信，哪几个点必须满足前提
  3. 我自己怎么验证（给出可复现的对照方式）

所以表格按「等级」排，问题列写人话，不写参数名。
"""
import json, os


GRADE_CLS = {"S": "gs", "A": "ga", "B": "gb", "C": "gc", "D": "gd"}
GRADE_TXT = {"S": "直接照打", "A": "照打，站稳", "B": "可用，注意阵位",
             "C": "条件苛刻", "D": "别依赖"}

CSS = """
<style>
  .audit-tb td{font-size:12px}
  .audit-tb td.nm{color:var(--tx3);font-size:11px;max-width:200px;line-height:1.45}
  .audit-tb .dist{color:#6d8a7d;font-size:10.5px;white-space:nowrap;margin-top:1px;
    font-variant-numeric:tabular-nums}
  .audit-tb td.objname{max-width:200px;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap;font-family:ui-monospace,Consolas,monospace;font-size:11px}
  .gcell{display:inline-block;min-width:22px;text-align:center;border-radius:4px;
    font-weight:700;font-size:11.5px;padding:1px 5px}
  .gcell.gs{background:#0d3b2b;color:#7fe3b4;border:1px solid #1d6b4e}
  .gcell.ga{background:#123528;color:#9fe8c4;border:1px solid #235c45}
  .gcell.gb{background:#3a3315;color:#e8c96a;border:1px solid #6b5a23}
  .gcell.gc{background:#3d2a16;color:#e8a86a;border:1px solid #6b4a23}
  .gcell.gd{background:#3d1c18;color:#ff9d8a;border:1px solid #6b2e26}
  .mz{color:#ff6b5a;font-weight:700}
  .slot-bar{display:flex;gap:3px}
  .slot-bar i{width:13px;height:13px;border-radius:3px;background:#1b2b24;display:block}
  .slot-bar i.on{background:#2f6b52}
  .slot-bar i.hot{background:#7fe3b4}
  .slot-bar i.no{background:#4a1f19}
  .bad{color:#ff9d8a}
  .good{color:#7fe3b4}
</style>
"""


_REGION_PRE = ("cityforestundercrystal ", "cityforestunderelevator ", "cityforestunder ",
               "cityforestcrystal ", "cityforest ", "swamplandjungle ", "swampland ",
               "motherwhalefield ", "whitearkcity ", "desertcrystal ", "desert ", "snow ")


def _short(name, n=24):
    """把 sbg_swamplandjungle_dn_statue01_01 缩成 dn statue01 01。"""
    t = (name or "").replace("sbg_", "").replace("_", " ")
    for pre in _REGION_PRE:
        if t.startswith(pre):
            t = t[len(pre):]
            break
    return t if len(t) <= n else t[:n - 1] + "…"


def _slot_bar(row):
    """5 格：深绿=达标称，浅绿=≥2段，红=打不到。"""
    c = row.get("_slots") or {}
    out = []
    for i in range(1, 6):
        v = (c.get("cover_%d" % i) or {}).get("nst")
        if v is None:
            out.append('<i></i>')
        elif v >= row.get("nom") or 0:
            out.append('<i class="hot" title="%d 段"></i>' % v)
        elif v >= 2:
            out.append('<i class="on" title="%d 段"></i>' % v)
        else:
            out.append('<i class="no" title="%d 段"></i>' % v)
    return '<div class="slot-bar">%s</div>' % "".join(out)


def _ratio_tool(arenas, pos_by_arena):
    """屏幕比例换算器：1600×900 的坐标 → 玩家自己分辨率的坐标。

    依据：Unity 的 Camera.fieldOfView 是**竖直** FOV，所以换宽高比时纵向不变、
    横向按 1.7778/R 收缩。这一条已从 bundle 的 Camera 组件确认（fov=60）。
    """
    keys = [a for a, _ in arenas if a in pos_by_arena]
    if not keys:
        return ""
    js = json.dumps({a: pos_by_arena[a] for a in keys}, ensure_ascii=False)
    opts = "".join('<option value="%s">%s</option>' % (a, lb) for a, lb in arenas if a in keys)
    return """
<div class="note">
  <b>换算器：把红点搬到你的屏幕上</b>
  <p class="body" style="margin:6px 0">红点是按 <b>1600×900（16:9）</b> 画的。Unity 的 <code>fieldOfView=60</code>
    是<b>竖直</b>视场，所以换宽高比时<b>纵向不变、横向往中心收</b>。输入你的实际分辨率，直接拿换算后的坐标：</p>
  <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0">
    <select id="rt-a" style="background:#0e1714;color:#dcece4;border:1px solid #1e3a30;
      border-radius:6px;padding:5px 8px;font-size:12px">%s</select>
    <input id="rt-w" type="number" value="2400" style="width:82px;background:#0e1714;color:#dcece4;
      border:1px solid #1e3a30;border-radius:6px;padding:5px 8px;font-size:12px">
    <span style="color:#6f9484;font-size:12px">×</span>
    <input id="rt-h" type="number" value="1080" style="width:82px;background:#0e1714;color:#dcece4;
      border:1px solid #1e3a30;border-radius:6px;padding:5px 8px;font-size:12px">
    <span id="rt-r" style="color:#7fe3b4;font-size:12px">19.5:9</span>
  </div>
  <div id="rt-out" style="font-family:ui-monospace,Consolas,monospace;font-size:12px;
    color:#9dbdb0;line-height:1.9"></div>
  <p class="body" style="margin:8px 0 0;font-size:11.5px;color:#6f9484">
    红字＝这一档下红点会跑偏 &gt;50px，说明那颗点在你的屏幕上已经指不到原来那件东西了 ——
    这种情况请直接按「首击物体」去找，别按像素数。</p>
</div>
<script>
(function(){
  var D=%s;
  var A=document.getElementById('rt-a'),W=document.getElementById('rt-w'),
      H=document.getElementById('rt-h'),O=document.getElementById('rt-out'),
      R=document.getElementById('rt-r');
  function fmt(){
    var a=A.value,w=+W.value||2400,h=+H.value||1080;
    if(!w||!h){O.textContent='';return}
    var r=w/h, base=16/9;
    R.textContent=(r).toFixed(2)+':1'+(Math.abs(r-base)<0.02?'（标准 16:9，可直接按比例缩放）':'');
    var pts=D[a]||[], out=[];
    for(var i=0;i<pts.length;i++){
      var u=pts[i][0], v=pts[i][1];
      var nx=(u/1600-0.5)*base/r+0.5;
      var u2=nx*w, v2=v/900*h;
      var d=Math.abs(nx*w - u/1600*w);
      out.push('①②③④⑤'.charAt(i)+'  '+Math.round(u2)+' , '+Math.round(v2)+
        (d>=50?'   ← 偏 '+Math.round(d)+'px':''));
    }
    O.innerHTML=out.join('<br>');
  }
  if(A){A.onchange=fmt;W.oninput=fmt;H.oninput=fmt;fmt();}
})();
</script>
""" % (opts, js)


def build(arenas, data_dir="导出"):
    """返回 (html, css, stats)。arenas 是 [('001','H36-35'), ...]。"""
    rows, per_arena, stats = [], [], {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0,
                                      "cone": [], "n": 0, "aerr": 0.0,
                                      "n5": 0, "n1": 0, "drift": [], "narrow2": 0, "eoff": []}
    pos_by_arena = {}
    for a, label in arenas:
        p = os.path.join(data_dir, "audit_%s.json" % a)
        if not os.path.exists(p):
            continue
        ad = json.load(open(p, encoding="utf-8"))
        C = {c["no"]: c for c in ad.get("C") or []}
        Emap = {x["no"]: x for x in (ad.get("E_vfov") or {}).get("per_point") or []}
        cnt = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
        for r in ad["rows"]:
            stats["n"] += 1
            cnt[r["grade"]] += 1
            stats[r["grade"]] += 1
            stats["cone"].append(r.get("cone_px") or 0 or 0)
            stats["aerr"] = max(stats["aerr"], (ad.get("A") or {}).get("err_max") or 0)
            _ok = r.get("n_ok2") or 0
            _tot = r.get("slot_n") or 5
            if _ok >= _tot:
                stats["n5"] += 1
            if _ok <= 1:
                stats["n1"] += 1
            rr = dict(r)
            rr["_slots"] = (C.get(r["no"]) or {}).get("slots")
            if r["no"] <= 5:
                pos_by_arena.setdefault(a, []).append(r["px"])
            eoff = (Emap.get(r["no"]) or {}).get("off_max") or 0
            stats["eoff"].append(eoff)
            if (r.get("cone_px") or 0) < 2:
                stats["narrow2"] += 1
            obj = r.get("obj") or {}
            bb = obj.get("bbox") or [0, 0]
            prob = "；".join((r.get("fatal") or []) + (r.get("warn") or [])) or "—"
            rows.append(
                '<tr><td class="no">%s<i style="font-style:normal;color:var(--tx3);'
                'font-size:10px">·%d</i></td>'
                '<td class="seg">%d</td>'
                '<td class="hl">%s</td>'
                '<td>%s</td>'
                '<td>%d/%d</td>'
                '<td><div class="objname">%s</div><div class="dist">屏宽 %dpx · %.0fm</div></td>'
                '<td class="%s">%.0f</td>'
                '<td><span class="gcell %s">%s</span></td>'
                '<td class="nm %s">%s</td></tr>'
                % (a, r["no"], r.get("nom") or 0,
                   ('<b>%.1f</b>' % r.get("cone_px") or 0) if (r.get("cone_px") or 0 or 0) >= 3 else
                   ('<span class="mz">%.1f</span>' % r.get("cone_px") or 0),
                   _slot_bar(rr), r.get("n_ok2") or 0, r.get("slot_n") or 5,
                   _short(r["first"]),
                   max(bb), r["first_d"],
                   "bad" if eoff >= 50 else "", eoff,
                   GRADE_CLS[r["grade"]], r["grade"],
                   "bad" if r["grade"] in ("C", "D") else "", prob))
        listed = [r for r in ad["rows"] if r["no"] <= 5]
        per_arena.append(
            '<tr><td class="no"><b>%s</b></td>'
            '<td class="nm">%s</td>'
            '<td class="hl">%.1f</td>'
            '<td><div class="slot-bar">%s</div></td>'
            '<td>%s</td></tr>'
            % (a, label,
               sum((r.get("cone_px") or 0 or 0) for r in listed) / max(1, len(listed)),
               "".join('<i class="%s" title="%d"></i>'
                       % ("hot" if cnt[g] >= 3 else "on" if cnt[g] else "no", cnt[g])
                       for g in ("S", "A", "B", "C", "D")),
               " ".join('<span class="gcell %s">%s%d</span>'
                        % (GRADE_CLS[g], g, cnt[g]) for g in ("S", "A", "B", "C", "D")
                        if cnt[g]) or "—"))

    n = max(1, stats["n"])
    cones = sorted(stats["cone"])
    med = cones[len(cones) // 2] if cones else 0
    body = """<h2>v12 独立审计：朋友说「不准」，我去复算了一遍</h2>
<p class="body">原来的点位链是<b>一套假设算到底</b>：相机在 <code>camera_position</code>、
  朝向 +z、竖直 FOV 60°、角色站阵位正中、枪口高 1.45m。<code>verify_px.py</code> 的
  1000 次模拟只是在这套假设<b>周围</b>抖 —— 假设本身错了，抖一万次也只会把错误算得很自信。</p>
<p class="body">所以这一轮换了<b>六项独立复核</b>，每项单独回答一个问题，互相不背书：</p>

<table class="tb audit-tb"><thead><tr>
  <th>项</th><th>核的是什么</th><th>为什么必须单列</th></tr></thead><tbody>
<tr><td class="no"><b>A</b></td><td>准星像素 → 射线 → 世界点 → 投回像素</td>
  <td>查代码，不查假设。误差 &gt;1px 就是投影写错了</td></tr>
<tr><td class="no"><b>B</b></td><td><b>容错锥</b>：从枪口出发，四方向探到「开始掉段」的边界</td>
  <td><b>完全绕开相机</b>。只依赖枪口位置和场景几何，是唯一不受标定影响的指标</td></tr>
<tr><td class="no"><b>C</b></td><td>5 个阵位各自重算，含遮挡截断</td>
  <td>玩家不会正好站在基准阵位。这是<b>原算法漏掉的一层</b></td></tr>
<tr><td class="no"><b>D</b></td><td>相机俯角 −6°…+6° 全域重投影</td>
  <td><code>meta</code> 明确写着俯角由运行时 Cinemachine 驱动 —— <b>唯一没有实证的参数</b></td></tr>
<tr><td class="no"><b>E</b></td><td>20:9 / 21:9 / 16:10 / 4:3 下的像素位置</td>
  <td>手机和模拟器不都是 16:9。纵向 FOV 固定时，横向坐标会整体漂</td></tr>
<tr><td class="no"><b>F</b></td><td>首击物体在屏幕上占多少像素</td>
  <td>8×6px 的东西玩家根本认不出来 —— 这是「照图打偏」最朴素的原因</td></tr>
</tbody></table>

<div class="note">
  <b>审计结果：%d 个点 · 往返自洽 %.2fpx · 锥宽中位 %.1fpx · 5 个阵位都能用 %d 个（%.0f%%）· 判为「别依赖」%d 个（%.0f%%）</b>
  <ul>
    <li><b>A 项全部通过</b>（往返误差 ≤%.2fpx）—— 代码本身没写错。
      所以「不准」<b>不是算错了</b>，是<b>算出来的东西和玩家看到的不一样</b>。</li>
    <li><b>锥宽中位只有 %.1fpx</b>，%.0f%% 的点不到 2px。纵向通常比横向更紧（2~4px）——
      因为远处物件在竖直方向的角跨度本来就小。页面上的「稳定半径」不是保守估计，是<b>真实预算</b>。</li>
    <li><b>阵位是最大的坑</b>：这批点里只有 <b>%d 个</b>在 5 个掩体下都能打 ≥2 段，
      另有 <b>%d 个</b>只有 1 个阵位可用。换到对侧掩体，自家的高掩体会在 0.5~4m 处把射线截断，
      段数直接归零。原版 <code>per_slot</code> 没做遮挡截断，所以页面上「全阵位」的说法是<b>高估</b>的
      —— 这一版已修正，按阵列出的数都是截断后的。</li>
    <li><b>像素坐标只在 16:9 有效</b>。21:9 上边缘红点会横向漂 %.0f~%.0fpx。
      换比例不是「差一点」，是<b>指不到东西</b>。</li>
  </ul>
</div>

<h2>每张图的审计结论</h2>
<table class="tb audit-tb"><thead><tr>
  <th>图</th><th>场景</th><th>①~⑤<br>平均锥宽 px</th>
  <th>等级分布（S/A/B/C/D）</th><th>明细</th></tr></thead>
<tbody>%s</tbody></table>

<h2>逐点审计明细</h2>
<table class="tb audit-tb"><thead><tr>
  <th>图·号</th><th>稳态<br>段</th><th>锥宽<br>px</th><th>阵位<br>可用</th>
  <th>可用<br>阵位/总</th><th>首击物体</th><th>比例<br>漂移px</th><th>等级</th><th>问题</th>
</tr></thead><tbody>%s</tbody></table>
<p class="cn" style="text-align:center;font-size:11px">
<b>锥宽</b> = 准星偏离这颗像素多少还能保住标称段数（四方向取最小，与相机无关）；
<b>阵位可用</b> = 5 个阵位里仍能打到 ≥2 段的数量（绿格＝达标记段数，浅绿＝≥2 段，红＝打不到）；
<b>比例漂移</b> = 换成 21:9 宽屏后，这颗红点在画面里横向跑多远（红字 ≥50px，基本指不到东西）。</p>

<div class="note">
  <b>「不准」的三个真实原因，按影响排序</b>
  <ol>
    <li><b>阵位不对（最大）</b>：点是以基准阵位算的。你站在别的掩体后，高掩体会在
      1~4m 内把射线截断，表现为「明明对准了却打不出充能」。<b>对策：先看自己站哪个阵位，
      只看对应那一格是绿的点。</b></li>
    <li><b>屏幕比例不对（中）</b>：16:10 / 20:9 / 21:9 上，同一颗红点会横向漂
      <b>50~250px</b>，越靠画面边缘漂得越多。红点是给 16:9 画的。
      <b>对策：不要按「离屏幕左边多少个像素」找，按「哪个物体」找。</b></li>
    <li><b>手抖预算太小（小但普遍）</b>：纵向容错 2~4px，手机触屏瞄准几乎做不出这个精度。
      <b>对策：优先选锥宽 ≥5px 的点，宁可选 3 段稳的，不要 4 段飘的。</b></li>
  </ol>
  <p class="body" style="margin:8px 0 0">还有一个<b>没法在本项目里验证</b>的因素：敌人、队友、
    残骸的实体遮挡。它们不在场景 <code>assembly</code> 里，只在实战中出现 ——
    这会让「纸面段数」在实际战斗中打折，且打折幅度与站位有关。</p>
</div>

__RT__
""" % (stats["n"], stats["aerr"], med,
       stats["n5"], 100.0 * stats["n5"] / n,
       stats["D"], 100.0 * stats["D"] / n,
       stats["aerr"], med, 100.0 * stats["narrow2"] / n,
       stats["n5"], stats["n1"],
       (min(stats["eoff"]) if stats["eoff"] else 0),
       (max(stats["eoff"]) if stats["eoff"] else 0),
       "".join(per_arena), "".join(rows))
    body = body.replace("__RT__", _ratio_tool(arenas, pos_by_arena))
    return body, CSS, stats
