# -*- coding: utf-8 -*-
"""在 v2 原生场景图上标注小红帽穿透充能点位。

图层顺序：v2 场景 -> 命中物高亮框 -> 穿透射线 -> 站位 -> 卡片/图例
"""
import os, json, math, re
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import render_v2 as R

BASE = os.path.dirname(os.path.abspath(__file__))
EX = os.path.join(BASE, "导出")
OUT = os.path.join(BASE, "render")
SCAN = os.path.join(EX, "h36-35_scan.json")

W, H = R.W, R.H
PLAYER_Z = 4.5
PER_SEG = 280.0

GRADE_CN = {"hard": "硬", "medium": "中", "soft": "软", "static": "景", "cover": "掩"}
GRADE_COL = {"hard": (255, 96, 96), "medium": (255, 152, 62),
             "soft": (255, 214, 96), "static": (170, 182, 176),
             "cover": (140, 200, 255)}
CYAN = (108, 216, 255)
INK = (238, 246, 252)

_FONT = {}
def font(sz, bold=False):
    key = (sz, bold)
    if key in _FONT:
        return _FONT[key]
    names = ["msyhbd.ttc", "msyh.ttc"] if bold else ["msyh.ttc", "msyhbd.ttc"]
    for n in names:
        for d in (r"C:\Windows\Fonts", r"C:\Windows\Fonts\zh-cn"):
            p = os.path.join(d, n)
            if os.path.exists(p):
                try:
                    _FONT[key] = ImageFont.truetype(p, sz)
                    return _FONT[key]
                except Exception:
                    pass
    _FONT[key] = ImageFont.load_default()
    return _FONT[key]

def base_name(n):
    return re.sub(r"\s*\(\d+\)$", "", n).strip()

def dist_to_box(x, z, b):
    x1, x2 = min(b[0], b[3]), max(b[0], b[3])
    z1, z2 = min(b[2], b[5]), max(b[2], b[5])
    dx = max(x1 - x, 0, x - x2)
    dz = max(z1 - z, 0, z - z2)
    return math.hypot(dx, dz)

def short(n):
    return base_name(n).replace("sbg_swamplandjungle_", "").replace("_sbg_swamplandjungle_", "")

def match_props(props, name):
    bn = short(name)
    return [p for p in props if p.get("b") and short(p["n"]) == bn]

def bracket(d, box, color, w=2, arm=14):
    x1, y1, x2, y2 = box
    arm = min(arm, (x2 - x1) / 2, (y2 - y1) / 2)
    for (cx, cy, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        d.line([(cx, cy), (cx + dx * arm, cy)], fill=color, width=w)
        d.line([(cx, cy), (cx, cy + dy * arm)], fill=color, width=w)

def overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])

def top_box(prop, cam):
    b = prop["b"]
    x1, x2 = min(b[0], b[3]), max(b[0], b[3])
    y1, y2 = min(b[1], b[4]), max(b[1], b[4])
    z1 = min(b[2], b[5])
    q = [cam and R.proj(x1, y1, z1, cam), R.proj(x2, y1, z1, cam),
         R.proj(x2, y2, z1, cam), R.proj(x1, y2, z1, cam)]
    if any(v is None for v in q):
        return None
    return (min(v[0] for v in q), min(v[1] for v in q),
            max(v[0] for v in q), max(v[1] for v in q))


def annotate(arena_id, top_idx=0, out_name=None, cam=None, bg=None, scale=1.0):
    scan = json.load(open(SCAN, encoding="utf-8"))[arena_id]
    props = [p for p in scan["props"] if p.get("b")]
    tops = scan["top"]
    t = tops[top_idx]

    terr0 = R.height_curve(props, arena_id)
    gy0 = R.hz(PLAYER_Z, *terr0)
    if cam is None:
        # 相机站在该点位身后 13.5m，朝向点位目标方向 —— 等同于玩家实际操作视角
        yw = math.radians(t["yaw"])
        cam = dict(x=t["px"] - 13.5 * math.sin(yw), y=gy0 + 5.54,
                   z=PLAYER_Z - 13.5 * math.cos(yw),
                   pitch=5.0, fov=40.0, yaw=t["yaw"])
    if bg is None:
        bg = os.path.join(OUT, "_scene_%s_top%d.png" % (arena_id, top_idx + 1))
        R.render(os.path.join(EX, "map_%s.json" % arena_id), bg, cam=cam, arena=arena_id)
    im = Image.open(bg).convert("RGBA")
    if im.size != (W, H):
        im = im.resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(im)

    terr = R.height_curve(props, arena_id)
    gy_stand = R.hz(PLAYER_Z, *terr)

    # ---------- 1. 命中物定位 ----------
    yawr = math.radians(t["yaw"])
    ux, uz = math.sin(yawr), math.cos(yawr)
    hits = []
    for h in t["hitList"]:
        ex, ez = t["px"] + h["t"] * ux, PLAYER_Z + h["t"] * uz
        insts = match_props(props, h["n"])
        if not insts:
            continue
        best = min(insts, key=lambda p: dist_to_box(ex, ez, p["b"]))
        box = top_box(best, cam)
        if not box:
            continue
        if box[2] < -40 or box[0] > W + 40:
            continue
        if box[3] < -40 or box[1] > H + 40:
            continue
        hits.append(dict(box=box, g=h["g"], n=h["n"], t=h["t"], prop=best))
    hits.sort(key=lambda h: h["t"])

    # ---------- 2. 高亮：按物体自身贴图的 alpha 轮廓提亮（不是矩形） ----------
    ti = R.tex_index(arena_id)
    for h in hits:
        prop = h.get("prop")
        if prop is None:
            continue
        png = ti.get(short(prop["n"]))
        if not png:
            continue
        x1, y1, x2, y2 = [int(round(v)) for v in h["box"]]
        x1c, y1c = max(0, x1), max(0, y1)
        x2c, y2c = min(W, x2), min(H, y2)
        tw, th = x2c - x1c, y2c - y1c
        if tw < 4 or th < 4:
            continue
        try:
            lay = Image.open(png).convert("RGBA")
        except Exception:
            continue
        # 贴合帧：AABB 的 alpha 包围盒 与 屏幕框 一一对应
        ab = lay.split()[3].getbbox()
        if ab:
            lay = lay.crop(ab)
        lay = lay.resize((tw, th), Image.LANCZOS)
        mask = lay.split()[3].point(lambda v: int(v * 0.92))
        patch = im.crop((x1c, y1c, x2c, y2c))
        arr = np.array(patch).astype(np.float32)
        arr[:, :, :3] = np.clip(arr[:, :, :3] * 1.30 + 22, 0, 255)
        boosted = Image.fromarray(arr.astype(np.uint8))
        im.paste(Image.composite(boosted, patch, mask), (x1c, y1c))
    d = ImageDraw.Draw(im)

    # ---------- 3. 穿透射线 ----------
    st = R.proj(t["px"], gy_stand, PLAYER_Z, cam)
    if st and hits:
        inb = [h["t"] for h in hits if 0 <= h["box"][0] <= W and 0 <= h["box"][2] <= W]
        far_t = (max(inb) if inb else max(h["t"] for h in hits)) + 1.5
        ex, ez = t["px"] + far_t * ux, PLAYER_Z + far_t * uz
        eg = R.hz(ez, *terr)
        ep = R.proj(ex, min(eg + 0.55, gy_stand + 1.2), ez, cam)
        if ep:
            # 底层光带
            ny = max(1, int(abs(ep[1] - st[1])))
            for k in range(ny):
                yy = st[1] + (ep[1] - st[1]) * k / ny
                xx = st[0] + (ep[0] - st[0]) * k / ny
                aw = int(70 * max(0.0, 1.0 - abs(yy - st[1]) / max(1.0, abs(ep[1] - st[1] + 1))))
                d.ellipse([xx - 2.6, yy - 1.0, xx + 2.6, yy + 1.0], fill=CYAN + (max(12, aw // 5),))
            # 虚线
            n_dash = 26
            for i in range(n_dash):
                if i % 2:
                    continue
                p0 = (st[0] + (ep[0] - st[0]) * i / n_dash, st[1] + (ep[1] - st[1]) * i / n_dash)
                p1 = (st[0] + (ep[0] - st[0]) * (i + 1) / n_dash, st[1] + (ep[1] - st[1]) * (i + 1) / n_dash)
                d.line([p0, p1], fill=CYAN + (200,), width=2)

    # ---------- 4. 命中物框 + 编号 ----------
    used = []
    for i, h in enumerate(hits):
        n = i + 1
        g = h["g"]
        col = GRADE_COL.get(g, (200, 200, 200))
        x1, y1, x2, y2 = h["box"]
        small = (x2 - x1) < 11 or (y2 - y1) < 11
        if n <= 3 and not small:
            bracket(d, (x1, y1, x2, y2), col, 2, arm=11)
            lab = str(n)
            f = font(12, True)
            tw = d.textlength(lab, font=f) + 15
            ty = y1 - 18
            box = (x1 - 1, ty, x1 - 1 + tw, ty + 17)
            tries = 0
            while any(overlap(box, u) for u in used) and tries < 7:
                ty += 18
                box = (x1 - 1, ty, x1 - 1 + tw, ty + 17)
                tries += 1
                if ty > y2:
                    break
            used.append(box)
            d.rectangle(box, fill=(8, 14, 12, 230))
            d.rectangle([box[0], box[1], box[0] + 5, box[3]], fill=col + (255,))
            d.text((box[0] + 8, ty + 1), lab, font=f, fill=col + (255,))
        else:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            d.ellipse([mx - 3, my - 3, mx + 3, my + 3], fill=col + (215,))
            d.text((mx + 6, my - 8), str(n), font=font(11, True), fill=col + (215,))

    # ---------- 5. 其余候选站位 ----------
    for k in range(len(tops)):
        if k == top_idx:
            continue
        tk = tops[k]
        p = R.proj(tk["px"], R.hz(tk["px"] and PLAYER_Z, *terr), PLAYER_Z, cam)
        if not p:
            continue
        r = 11
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r],
                  fill=(10, 18, 22, 150), outline=(150, 200, 220, 200), width=1)
        lab = str(k + 1)
        f = font(13, True)
        tw = d.textlength(lab, font=f)
        d.text((p[0] - tw / 2, p[1] - 8), lab, font=f, fill=(190, 220, 235, 230))

    # ---------- 6. 主站位 ----------
    if st:
        sx, sy = st[0], st[1]
        # 朝向扇形
        pts = []
        for ang in (-8, -4, 0, 4, 8):
            a2 = math.radians(t["yaw"] + ang)
            ex, ez = t["px"] + 3.2 * math.sin(a2), PLAYER_Z + 3.2 * math.cos(a2)
            q = R.proj(ex, R.hz(ez, *terr) + 0.05, ez, cam)
            if q:
                pts.append((q[0], q[1]))
        if len(pts) >= 3:
            d.polygon([(sx, sy)] + pts, fill=(88, 200, 255, 34))
            d.line([(sx, sy), pts[0]], fill=CYAN + (180,), width=2)
            d.line([(sx, sy), pts[-1]], fill=CYAN + (180,), width=2)
        for rr, aa in ((17, 60), (11, 130), (7, 255)):
            d.ellipse([sx - rr, sy - rr, sx + rr, sy + rr],
                      fill=CYAN + (aa,) if rr > 7 else CYAN + (255,))
        d.ellipse([sx - 4, sy - 4, sx + 4, sy + 4], fill=(255, 255, 255, 255))
        f = font(14, True)
        txt = "站位 %d  x%+.1f  %+.0f°" % (top_idx + 1, t["px"], t["yaw"])
        tw = d.textlength(txt, font=f) + 14
        bx = min(max(8, sx - tw / 2), W - tw - 8)
        d.rectangle([bx, sy - 44, bx + tw, sy - 22], fill=(8, 16, 22, 225),
                    outline=CYAN + (150,), width=1)
        d.text((bx + 7, sy - 42), txt, font=f, fill=(205, 240, 255, 255))

    # ---------- 7. 顶部标题 ----------
    bar = Image.new("RGBA", (W, 64), (4, 10, 9, 0))
    ba = np.zeros((64, W, 4), np.uint8)
    ba[:, :, :3] = (6, 12, 10)
    ba[:, :, 3] = np.clip(np.linspace(205, 0, 64).astype(int), 0, 255)[:, None]
    im.alpha_composite(Image.fromarray(ba), (0, 0))
    d = ImageDraw.Draw(im)
    d.text((30, 8), "H36-35  沼泽丛林", font=font(24, True), fill=INK + (250,))
    d.text((30, 39), "战场 %s / 5    小红帽 SR 穿透充能    每段 %d 能量" % (arena_id, int(PER_SEG)),
           font=font(13), fill=(160, 190, 182, 240))

    # ---------- 8. 图例 ----------
    lx, ly = W - 250, 16
    d.rectangle([lx, ly, W - 24, ly + 96], fill=(6, 12, 11, 175), outline=(90, 120, 112, 120), width=1)
    d.text((lx + 12, ly + 8), "命中判定", font=font(13, True), fill=(190, 214, 206, 240))
    for i, (g, cn) in enumerate((("hard", "硬质"), ("medium", "中质"), ("soft", "软质"))):
        yy = ly + 30 + i * 21
        d.rectangle([lx + 14, yy + 4, lx + 26, yy + 14], fill=GRADE_COL[g] + (255,))
        d.text((lx + 34, yy), "%s 可破坏" % cn, font=font(12), fill=(200, 220, 214, 230))

    # ---------- 9. 数据卡 ----------
    cw, ch = 306, 172
    cx0, cy0 = W - cw - 24, H - ch - 24
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rectangle([0, 0, cw - 1, ch - 1], fill=(6, 13, 11, 208), outline=CYAN + (90,), width=1)
    cd.rectangle([0, 0, 4, ch - 1], fill=CYAN + (220,))
    cd.text((18, 12), "点位 1  ·  推荐", font=font(15, True), fill=(210, 240, 255, 250))
    cd.line([18, 38, cw - 18, 38], fill=(70, 100, 94, 180), width=1)
    rows = [
        ("穿透段数", "%d 段" % int(t["nHit"])),
        ("敌点", "%d 个" % int(t["nPt"])),
        ("保底能量", "%d" % int(t["e0"])),
        ("理想能量", "%d" % int(t["e1"])),
        ("所需发数", "%d → %d" % (int(t["shots0"]), int(t["shots1"]))),
    ]
    for i, (k, v) in enumerate(rows):
        yy = 48 + i * 24
        cd.text((20, yy), k, font=font(13), fill=(150, 178, 170, 235))
        f2 = font(14, True)
        tw = cd.textlength(v, font=f2)
        cd.text((cw - 20 - tw, yy - 1), v, font=f2, fill=INK + (250,))
    im.alpha_composite(card, (cx0, cy0))

    os.makedirs(OUT, exist_ok=True)
    outp = os.path.join(OUT, out_name or ("h36_%s_top%d.png" % (arena_id, top_idx + 1)))
    im.convert("RGB").save(outp, quality=95)
    print("  -> %s   命中 %d  段%d 能量%d/%d" % (outp, len(hits), t["nHit"], t["e0"], t["e1"]))
    return outp


if __name__ == "__main__":
    import sys
    ids = sys.argv[1:] or ["001", "002", "003", "004", "005"]
    for a in ids:
        annotate(a, 0)
