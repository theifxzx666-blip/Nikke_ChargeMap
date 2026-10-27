# -*- coding: utf-8 -*-
"""在原生渲染画面上标注充能点位（游戏视角平面标注）。

数据链：
  h36-35_scan.json  每个战场的 Top 站位（px/yaw）+ 命中物体清单
  map_001~005.json  物体世界 AABB
  render_plane.py   同一套相机参数 -> 原生画面
标注：
  高亮重绘 = 射线实际打到的可破坏体（从底图里提亮抠出来）
  括号框 + 标签 = 该物体的充能等级与单发贡献
  站位标记 = 建议站位与开火方向
"""
import json, os, re, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import render_plane as R

BASE = os.path.dirname(os.path.abspath(__file__))
EX = os.path.join(BASE, "导出")
OUT = os.path.join(BASE, "render")

GRADE_CN = {"hard": "硬", "medium": "中", "soft": "软", "dynamic_object": "动态"}
GRADE_COLOR = {"hard": (255, 92, 84), "medium": (255, 176, 62), "soft": (128, 226, 148),
               "dynamic_object": (150, 190, 255)}
PER_SEG = 280.0
PLAYER_Z = 4.5
GROUND_Y = -2.34


def font(sz, bold=False):
    c = r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"
    try:
        return ImageFont.truetype(c, sz)
    except Exception:
        return ImageFont.load_default()


def pre(name):
    return name if name.startswith("sbg_") else "sbg_swamplandjungle_" + name


def norm(n):
    return re.sub(r"\s*\(\d+\)$", "", n).strip()


def dist_to_box(x, z, b):
    dx = max(b[0] - x, 0.0, x - b[3])
    dz = max(b[2] - z, 0.0, z - b[5])
    return math.hypot(dx, dz)


def bracket(d, box, color, w=2):
    x1, y1, x2, y2 = box
    L = max(8, int(min(x2 - x1, y2 - y1) * 0.30))
    for pa, pb in (((x1, y1), (x1 + L, y1)), ((x1, y1), (x1, y1 + L)),
                   ((x2, y1), (x2 - L, y1)), ((x2, y1), (x2, y1 + L)),
                   ((x1, y2), (x1 + L, y2)), ((x1, y2), (x1, y2 - L)),
                   ((x2, y2), (x2 - L, y2)), ((x2, y2), (x2, y2 - L))):
        d.line([pa, pb], fill=color, width=w)


def outline_layer(layer, color, px=2):
    """只在该贴片轮廓外侧加一圈描边（不填充内部），让被标注物从背景里跳出来"""
    from PIL import ImageChops
    a = layer.split()[3]
    solid = a.point(lambda v: 255 if v > 120 else 0)      # 先二值化，只描外轮廓
    grow = solid.filter(ImageFilter.MaxFilter(px * 2 + 1))
    ring_alpha = ImageChops.subtract(grow, solid).point(lambda v: 210 if v > 0 else 0)
    ring = Image.new("RGBA", layer.size, color + (255,))
    ring.putalpha(ring_alpha)
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(ring)
    out.alpha_composite(layer)
    return out


def pickup_targets(scan, top):
    """把命中清单映射到具体 prop 实例 + 屏幕框"""
    props = [p for p in scan["props"] if p.get("b")]
    px, yaw = top["px"], top["yaw"]
    yr = math.radians(yaw)
    ux, uz = math.sin(yr), math.cos(yr)
    out = []
    for hit in top["hitList"]:
        ex, ez = px + hit["t"] * ux, PLAYER_Z + hit["t"] * uz
        cands = [(i, p) for i, p in enumerate(props) if norm(p["n"]) == norm(pre(hit["n"]))]
        if not cands:
            continue
        pi, p = min(cands, key=lambda t2: dist_to_box(ex, ez, t2[1]["b"]))
        if dist_to_box(ex, ez, p["b"]) > 4.0:
            continue
        out.append(dict(pi=pi, hit=hit, prop=p))
    return out


def render_annotated(arena_id, top_idx=0, out_name=None):
    scan = json.load(open(os.path.join(EX, "h36-35_scan.json"), encoding="utf-8"))[arena_id]
    tops = scan["top"]
    t = tops[top_idx]
    cam = R.CAM

    bgp, canvas, placed = R.render(os.path.join(EX, "map_%s.json" % arena_id),
                                   os.path.join(OUT, "_bg_%s.png" % arena_id), cam,
                                   arena=arena_id)
    W, H = canvas.size
    im = canvas.copy()

    # 顶部 / 底部压暗，给文字留呼吸
    for (y0, hh, al) in ((0, int(H * 0.11), 165), (H - int(H * 0.10), int(H * 0.10), 120)):
        sh = Image.new("RGBA", (W, hh), (6, 10, 8, al))
        im.alpha_composite(sh, (0, y0))

    targets = pickup_targets(scan, t)

    # ---- 1. 小目标提亮重绘（大块远景只用框标，避免糊片） ----
    for tg in targets:
        p = placed.get(tg["pi"])
        if not p:
            continue
        x0, y0, layer, sbox = p
        if layer.width * layer.height > W * H * 0.02:
            continue
        im.alpha_composite(R.brighten(layer, 1.22), (x0, y0))

    d = ImageDraw.Draw(im)

    # ---- 2. 框 + 标签（带避让） ----
    used = []

    def overlap(a, b):
        return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

    n = 0
    for tg in targets:
        p = placed.get(tg["pi"])
        if not p:
            continue
        sbox = p[3]
        x1, y1, x2, y2 = [max(-40, min(W + 40, v)) for v in sbox]
        if x2 - x1 < 3:
            continue
        # 贴地物体 AABB 很扁：撑到可读的最小尺寸，围绕中心
        if y2 - y1 < 22:
            cy = (y1 + y2) / 2
            y1, y2 = cy - 11, cy + 11
        if x2 - x1 < 16:
            cx = (x1 + x2) / 2
            x1, x2 = cx - 8, cx + 8
    targets.sort(key=lambda g: g["hit"]["t"])      # 由近及远编号
    n = 0
    for tg in targets:
        p = placed.get(tg["pi"])
        if not p:
            continue
        sbox = p[3]
        x1, y1, x2, y2 = [max(-40, min(W + 40, v)) for v in sbox]
        if x2 - x1 < 3:
            continue
        # 贴地物体 AABB 很扁：撑到可读的最小尺寸，围绕中心
        if y2 - y1 < 22:
            cy = (y1 + y2) / 2
            y1, y2 = cy - 11, cy + 11
        if x2 - x1 < 16:
            cx = (x1 + x2) / 2
            x1, x2 = cx - 8, cx + 8
        n += 1
        g = tg["hit"]["g"]
        col = GRADE_COLOR.get(g, (255, 255, 255)) + (255,)
        if n > 5:
            # 超出前 5 个：只留一个点位圆点，保持画面清爽
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            d.ellipse([mx - 4, my - 4, mx + 4, my + 4], fill=col, outline=(10, 14, 12, 255))
            d.text((mx + 7, my - 8), str(n), font=font(11, True), fill=col)
            continue
        bracket(d, (x1, y1, x2, y2), col, 2)
        lab = "%02d %s" % (n, GRADE_CN.get(g, g))
        f = font(14, True)
        tw = d.textlength(lab, font=f) + 12
        # 默认贴框右上外侧，越界则改左上
        lx = x2 + 4 if x2 + 4 + tw < W - 8 else x1 - 4 - tw
        ty = y1 - 22
        tries = 0
        box = (lx, ty, lx + tw, ty + 18)
        while any(overlap(box, u) for u in used) and tries < 24:
            ty += 19
            box = (lx, ty, lx + tw, ty + 18)
            tries += 1
        used.append(box)
        d.rectangle(box, fill=(8, 12, 10, 225))
        d.rectangle(box, outline=col, width=1)
        d.text((lx + 5, ty + 1), lab, font=f, fill=col)

    # ---- 3. 站位 + 朝向 ----
    px, yaw = t["px"], t["yaw"]
    st = R.proj(px, GROUND_Y, PLAYER_Z, cam)
    if st:
        sx, sy = st[0], st[1]
        yawr = math.radians(yaw)
        cone = []
        for ang in (-9, -4.5, 0, 4.5, 9):
            a2 = yawr + math.radians(ang)
            ex, ez = px + 9.0 * math.sin(a2), PLAYER_Z + 9.0 * math.cos(a2)
            q = R.proj(ex, GROUND_Y, ez, cam)
            if q:
                cone.append((q[0], q[1]))
        if len(cone) >= 3:
            d.polygon([(sx, sy)] + cone, fill=(96, 205, 255, 30))
            d.line([(sx, sy), cone[0]], fill=(130, 220, 255, 150), width=1)
            d.line([(sx, sy), cone[-1]], fill=(130, 220, 255, 150), width=1)
            d.line([(sx, sy), cone[len(cone) // 2]], fill=(180, 240, 255, 210), width=2)
        d.ellipse([sx - 8, sy - 8, sx + 8, sy + 8], fill=(70, 180, 240, 220),
                  outline=(210, 242, 255, 255), width=2)
        f = font(14, True)
        txt = "站位 x=%+.1f   偏角 %+.0f°" % (px, yaw)
        tw = d.textlength(txt, font=f) + 14
        d.rectangle([sx - tw / 2, sy + 14, sx + tw / 2, sy + 35], fill=(8, 14, 18, 220))
        d.rectangle([sx - tw / 2, sy + 14, sx + tw / 2, sy + 35], outline=(90, 175, 210, 220), width=1)
        d.text((sx - tw / 2 + 7, sy + 16), txt, font=f, fill=(196, 238, 255, 255))

    # ---- 4. 标题 ----
    d.text((26, 14), "H36-35    沼泽丛林战场 #%s    穿透充能点位 %d/%d"
           % (arena_id, top_idx + 1, len(tops)), font=font(23, True), fill=(242, 246, 242, 255))
    d.text((26, 45), "小红帽  SR  弹匣6 / 蓄力1.0s / 换弹2.0s / 技能② 穿透特化（永久）"
           "    每命中 1 个可破坏体 = 1 段 = %d 能量" % int(PER_SEG),
           font=font(14), fill=(178, 198, 182, 255))

    # ---- 5. 信息卡 ----
    cw, ch = 316, 150
    cx0, cy0 = W - cw - 24, H - ch - 26
    card = Image.new("RGBA", (cw, ch), (8, 12, 10, 222))
    im.alpha_composite(card, (cx0, cy0))
    d.rectangle([cx0, cy0, cx0 + cw, cy0 + ch], outline=(72, 100, 86, 255), width=2)
    d.text((cx0 + 14, cy0 + 10), "本点位充能收益", font=font(16, True), fill=(236, 240, 236, 255))
    rows = [
        ("命中可破坏体", "%d 段  (%s)" % (int(t["nHit"]),
                                     " ".join("%s×%d" % (k, v) for k, v in t["grade"].items())),
         (214, 224, 214)),
        ("保底（仅地形）", "%d 能量  →  %d 发" % (t["e0"], t["shots0"]), (200, 214, 200)),
        ("理想（+敌点位）", "%d 能量  →  %d 发" % (t["e1"], t["shots1"]), (255, 212, 116)),
        ("爆裂条 / 单发", "10000 / %d" % int(t["e0"] / max(1, t["nHit"])), (150, 170, 154)),
    ]
    yy = cy0 + 38
    for k, v, c in rows:
        d.text((cx0 + 14, yy), k, font=font(13), fill=(146, 164, 148, 255))
        d.text((cx0 + 128, yy), v, font=font(13, True), fill=c + (255,))
        yy += 26

    # ---- 6. 图例 ----
    lx, ly = 26, H - 46
    for key, lab in (("hard", "硬（大幅）"), ("medium", "中"), ("soft", "软（小幅）")):
        d.rectangle([lx, ly + 3, lx + 12, ly + 15], fill=GRADE_COLOR[key] + (255,))
        d.text((lx + 18, ly), lab, font=font(13), fill=(206, 216, 206, 255))
        lx += 18 + int(d.textlength(lab, font=font(13))) + 22

    from PIL import ImageEnhance
    out = im.convert("RGB")
    out = ImageEnhance.Color(out).enhance(1.10)
    out = ImageEnhance.Contrast(out).enhance(1.10)
    out = ImageEnhance.Brightness(out).enhance(1.04)
    outp = os.path.join(OUT, out_name or ("h36_%s_top%d.png" % (arena_id, top_idx + 1)))
    out.save(outp)
    print("->", outp, "标注 %d 个目标" % n)
    return outp


if __name__ == "__main__":
    render_annotated("001", 0)
