# -*- coding: utf-8 -*-
"""用游戏原生美术贴图 + 原生天空盒/地面，按游戏战斗视角合成战场画面。

素材全部来自拆包（sbg_swamplandjungle bundle）：
  skybox_side     天空（青灰雾带，v=0.5 正好是地平线）
  ground01_c      地面（远景雾化 -> 近景泥沼，已烘焙景深）
  sbg_..._<名>     每个战场物体的原图贴片（带 alpha）
每个贴片按自身世界 AABB 做透视投影，按 z 由远及近叠加。
"""
import json, os, re, math
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(BASE, "素材", "tex")
OUT = os.path.join(BASE, "render")

W, H = 1600, 900
CAM = dict(x=0.0, y=3.2, z=-9.0, pitch=5.0, fov=40.0)
FOG = (150, 160, 148)
FOG_NEAR, FOG_FAR = 34.0, 120.0
BRIGHT = 1.10
SKIP_Z = 7.0


def proj(px, py, pz, cam):
    p = math.radians(cam["pitch"])
    rx, ry, rz = px - cam["x"], py - cam["y"], pz - cam["z"]
    vy = ry * math.cos(p) + rz * math.sin(p)
    vz = -ry * math.sin(p) + rz * math.cos(p)
    if vz <= 0.05:
        return None
    fpx = (H / 2.0) / math.tan(math.radians(cam["fov"] / 2.0))
    return (W / 2.0 + fpx * rx / vz, H / 2.0 - fpx * vy / vz, vz)


def base_name(n):
    return re.sub(r"\s*\(\d+\)$", "", n).strip()


_TEX = {}
def tex_index(arena=None):
    """arena 专属贴图目录优先，缺失时回退到 001 的通用素材"""
    if arena in _TEX:
        return _TEX[arena]
    out = {}
    for d in (TEX, os.path.join(BASE, "素材", "tex_" + arena) if arena and arena != "001" else None):
        if not d or not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.lower().endswith(".png"):
                out[os.path.splitext(f)[0]] = os.path.join(d, f)
    _TEX[arena] = out
    return out


def brighten(img, k):
    if abs(k - 1.0) < 0.01:
        return img
    r, g, b, a = img.split()
    lut = [min(255, int(i * k)) for i in range(256)]
    return Image.merge("RGBA", (r.point(lut), g.point(lut), b.point(lut), a))


def fog_blend(img, f):
    if f <= 0.01:
        return img
    a = img.split()[3].point(lambda v: int(v * (1 - f * 0.6)))
    base = Image.new("RGBA", img.size, FOG + (255,))
    base.paste(img, (0, 0), img)
    base = Image.blend(base, Image.new("RGBA", img.size, FOG + (255,)), f * 0.5)
    base.putalpha(a)
    return base


def build_ground(total_h, hy, arena=None):
    """地面：取原生 ground01_c 的近景泥沼段，顶部向雾色过渡（避免分段接缝）"""
    src = Image.open(tex_index(arena)["sbg_swamplandjungle_ground01_c"]).convert("RGB")
    gh = max(9, total_h - hy)
    # 用近景段（贴图下方 40%），并轻微纵向拉伸
    seg = src.crop((0, int(src.height * 0.60), src.width, src.height))
    g = seg.resize((W, gh), Image.LANCZOS)
    px = g.load()
    bandh = max(1, int(gh * 0.30))
    for y in range(min(bandh, gh)):
        t = (1.0 - y / float(bandh)) ** 1.5
        for x in range(W):
            c = px[x, y]
            px[x, y] = (int(c[0] * (1 - t) + FOG[0] * t),
                        int(c[1] * (1 - t) + FOG[1] * t),
                        int(c[2] * (1 - t) + FOG[2] * t))
    return g


def render(map_json, out_png=None, cam=CAM, skip_z=SKIP_Z, arena=None):
    scene = json.load(open(map_json, encoding="utf-8"))
    props = [p for p in scene["props"] if p.get("b")]
    tex = tex_index(arena)
    if out_png is None:
        out_png = os.path.join(OUT, os.path.basename(map_json).replace(".json", ".png"))

    fpx = (H / 2.0) / math.tan(math.radians(cam["fov"] / 2.0))
    hy = int(H / 2.0 - fpx * math.tan(math.radians(cam["pitch"])))
    hy = max(int(H * 0.18), min(int(H * 0.72), hy))

    sky = Image.open(tex.get("sbg_swamplandjungle_skybox_side", tex_index("001")["sbg_swamplandjungle_skybox_side"])).convert("RGB")
    canvas = Image.new("RGBA", (W, H), FOG + (255,))
    canvas.paste(sky.resize((W, max(1, hy * 2)), Image.LANCZOS).convert("RGBA"), (0, 0))

    canvas.paste(build_ground(H, hy, arena).convert("RGBA"), (0, hy))

    bh = max(2, int(H * 0.10))
    band = Image.new("RGBA", (1, bh))
    for y in range(bh):
        t = 1 - y / bh
        band.putpixel((0, y), FOG + (int(110 * t ** 1.5),))
    canvas.alpha_composite(band.resize((W, bh)), (0, max(0, hy - bh)))

    items = []
    for pi, p in enumerate(props):
        x1, y1, z1, x2, y2, z2 = p["b"]
        items.append(((z1 + z2) / 2.0, (x1 + x2) / 2.0, min(y1, y2), max(y1, y2),
                      max(abs(x2 - x1), 0.15), p, tex.get(base_name(p["n"])), pi))
    items.sort(key=lambda t: -t[0])

    placed = {}
    drawn = 0
    for cz, cx, ymin, ymax, w3, p, png, pi in items:
        if cz < skip_z or not png:
            continue
        zf = min(p["b"][2], p["b"][5])
        a = proj(cx - w3 / 2, ymin, zf, cam)
        b = proj(cx + w3 / 2, ymax, zf, cam)
        if not a or not b:
            continue
        sx1, sy1, dep = a[0], b[1], a[2]
        sx2, sy2 = b[0], a[1]
        sw, sh = sx2 - sx1, sy2 - sy1
        if sw < 1.5 or sh < 1.5:
            continue
        tw, th = int(round(sw)), int(round(sh))
        # 面积过大的多半是地形/天空底板，跳过以免糊住画面
        if tw * th > W * H * 0.22:
            continue
        ox, oy = int(round(sx1)), int(round(sy1))
        cx0, cy0 = max(0, ox), max(0, oy)
        cx1, cy1 = min(W, ox + tw), min(H, oy + th)
        if cx1 <= cx0 or cy1 <= cy0:
            continue
        layer = Image.open(png).convert("RGBA")
        cap = 2600.0
        if max(tw, th) > cap:
            k = cap / float(max(tw, th))
            nw, nh = max(1, int(tw * k)), max(1, int(th * k))
            # 缩放后按比例回推左上角，保证底边/中心对齐
            ox = int(round(ox + (tw - nw) / 2.0))
            oy = int(round(oy + (th - nh) / 2.0))
            tw, th = nw, nh
            cx0, cy0 = max(0, ox), max(0, oy)
            cx1, cy1 = min(W, ox + tw), min(H, oy + th)
            if cx1 <= cx0 or cy1 <= cy0:
                continue
        layer = layer.resize((max(1, tw), max(1, th)), Image.LANCZOS)
        layer = layer.crop((cx0 - ox, cy0 - oy, min(layer.width, cx1 - ox), min(layer.height, cy1 - oy)))
        layer = brighten(layer, BRIGHT)
        f = max(0.0, min(1.0, (dep - FOG_NEAR) / (FOG_FAR - FOG_NEAR)))
        layer = fog_blend(layer, f)
        canvas.alpha_composite(layer, (cx0, cy0))
        placed[pi] = (cx0, cy0, layer.copy(), (sx1, sy1, sx2, sy2))
        drawn += 1

    os.makedirs(OUT, exist_ok=True)
    canvas.convert("RGB").save(out_png)
    print("hy=%d 贴片 %d/%d -> %s" % (hy, drawn, len(items), out_png))
    return out_png, canvas, placed


if __name__ == "__main__":
    for i in range(1, 6):
        render(os.path.join(BASE, "导出", "map_%03d.json" % i))
