# -*- coding: utf-8 -*-
"""v2 场景合成器：正规 2.5D 分层，而不是把贴图硬拉到包围盒。

改进点（相对 v1）：
1. 地面做**透视正确的 tile 映射**（逐行反投射线求交），不再是整张图拉满下半屏
2. 天空用**垂直角度→球面 v** 映射，地平线和地面用雾色过渡，没有硬接缝
3. 纸片按 AABB 近面 z 从远到近叠加，每个物体按**真实距离**做雾化
4. 不再丢弃大贴片，靠排序和雾解决遮挡
5. 统一色调映射：降饱和 + 青绿偏移 + 暗角
"""
import os, json, math, re
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
TEXROOT = os.path.join(BASE, "素材")
OUT = os.path.join(BASE, "render")
EX = os.path.join(BASE, "导出")

W, H = 1600, 900
CAM = dict(x=0.0, y=3.2, z=-9.0, pitch=5.0, fov=40.0, yaw=0.0)
GROUND_Y = -2.34          # character_position 的 y
NEAR, FAR = 2.0, 260.0
FOG_NEAR, FOG_FAR = 10.0, 150.0
SKIP_Z = -12.0

_TEX = {}
def tex_dir(arena=None):
    if arena is None:
        return os.path.join(TEXROOT, "tex")
    d = os.path.join(TEXROOT, "tex_%s" % arena)
    return d if os.path.isdir(d) else os.path.join(TEXROOT, "tex")

def tex_index(arena=None):
    key = arena or "_"
    if key not in _TEX:
        d = tex_dir(arena)
        _TEX[key] = {os.path.splitext(f)[0]: os.path.join(d, f)
                     for f in os.listdir(d) if f.lower().endswith(".png")}
    return _TEX[key]

def base_name(n):
    return re.sub(r"\s*\(\d+\)$", "", n).strip()

# ---------------- 相机 ----------------
def _basis(cam):
    p = math.radians(cam["pitch"])
    fwd = np.array([0.0, -math.sin(p), math.cos(p)])
    up = np.array([0.0, math.cos(p), math.sin(p)])
    return fwd, up

def focal(cam):
    return (H / 2.0) / math.tan(math.radians(cam["fov"]) / 2.0)

def proj(X, Y, Z, cam=CAM):
    """世界点 -> (sx, sy, depth)。depth<=0 表示在相机后面"""
    dx, dy, dz = X - cam["x"], Y - cam["y"], Z - cam["z"]
    yaw = math.radians(cam.get("yaw", 0.0))
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    xc = dx * cy_ - dz * sy_          # 右向分量
    fh = dx * sy_ + dz * cy_          # 水平前向分量
    p = math.radians(cam["pitch"])
    zc = -dy * math.sin(p) + fh * math.cos(p)
    yc = dy * math.cos(p) + fh * math.sin(p)
    if zc <= 0.05:
        return None
    f = focal(cam)
    return (W / 2.0 + xc * f / zc, H / 2.0 - yc * f / zc, zc)

def horizon_sy(cam=CAM):
    return H / 2.0 - math.tan(math.radians(cam["pitch"])) * focal(cam)

# ---------------- 地形高度场 ----------------
_TERR = {}
def height_curve(props, key):
    """用场景物体底边 y 的低分位，拟合 z -> 地形高度。沼泽是缓上坡。"""
    if key in _TERR:
        return _TERR[key]
    buckets = {}
    for p in props:
        b = p.get("b")
        if not b:
            continue
        zc = (b[2] + b[5]) / 2.0
        y1 = min(b[1], b[4])
        if y1 < -25 or y1 > 30:
            continue
        buckets.setdefault(int(zc // 5) * 5, []).append(y1)
    xs, ys = [], []
    for k in sorted(buckets):
        v = sorted(buckets[k])
        if len(v) < 3:
            continue
        xs.append(k + 2.5)
        ys.append(v[min(len(v) - 1, int(len(v) * 0.15))])
    if len(xs) < 2:
        xs, ys = [0.0, 100.0], [GROUND_Y, GROUND_Y]
    # 强制单调不减：沼泽是连续缓上坡，有凹陷会让求交跳到另一个分支
    for i in range(1, len(ys)):
        if ys[i] < ys[i - 1]:
            ys[i] = ys[i - 1]
    _TERR[key] = (xs, ys)
    return xs, ys

def hz(z, xs, ys):
    return float(np.interp(z, xs, ys))

# ---------------- 天空 ----------------
def build_sky(cam, arena):
    ti = tex_index(arena)
    p = tex_index(None)
    path = ti.get("sbg_swamplandjungle_skybox_side") or p.get("sbg_swamplandjungle_skybox_side")
    sky = Image.open(path).convert("RGB")
    hor = horizon_sy(cam)
    out = Image.new("RGB", (W, H), (99, 111, 98))
    f = focal(cam)
    sp = sky.load()
    # 逐行：屏幕 sy -> 仰角 -> 球面 v（v=0.5 是地平线，v=0 是天顶）
    rows = np.arange(H)
    if len(rows):
        elev = np.degrees(np.arctan((H / 2.0 - rows) / f)) - cam["pitch"]
        vv = np.clip(0.5 - elev / 180.0, 0.0, 0.5)
        hor = max(hor, 1)
        vpix = np.clip((vv * sky.height).astype(int), 0, sky.height - 1)
        arr = np.array(sky)
        # 横向按 yaw 采样：这里视野不宽，取贴图中段一行拉伸
        strip = arr[vpix]                                    # (n, W_sky, 3)
        yaw_ = cam.get("yaw", 0.0)
        hfov = math.degrees(2 * math.atan(math.tan(math.radians(cam["fov"]) / 2) * W / H))
        c_ = (0.5 + yaw_ / 360.0)
        hw_ = hfov / 720.0
        xs = np.clip(((np.linspace(c_ - hw_, c_ + hw_, W)) * sky.width).astype(int), 0, sky.width - 1)
        band = strip[:, xs, :]                               # (n, W, 3)
        out_arr = np.array(out)
        out_arr[rows, :, :] = band
        out = Image.fromarray(out_arr)
    return out

# ---------------- 地面 ----------------
def solve_dz(sy, cam, f, pr, tx, ty, lo=0.35, hi=420.0):
    """二分求根：找 dz 使该世界地面点投影后落在 sy。地形单调 => 单调可解。"""
    yaw = math.radians(cam.get("yaw", 0.0))
    def g(dz):
        # dz 是水平前向距离
        Z = cam["z"] + dz * math.cos(yaw)
        gy = hz(Z, tx, ty)
        dy = gy - cam["y"]
        zc = -dy * math.sin(pr) + dz * math.cos(pr)
        if zc <= 0.06:
            return 1e9
        yc = dy * math.cos(pr) + dz * math.sin(pr)
        return (H / 2.0 - yc * f / zc) - sy

    glo, ghi = g(lo), g(hi)
    if glo == 1e9 or ghi == 1e9:
        return None
    if glo * ghi > 0:
        return None
    for _ in range(26):
        mid = 0.5 * (lo + hi)
        gm = g(mid)
        if gm == 1e9:
            hi = mid
            continue
        if gm * glo <= 0:
            hi = mid
        else:
            lo, glo = mid, gm
    return 0.5 * (lo + hi)


def build_ground(cam, arena, fog_rgb, terr=None):
    """逐行二分求交，返回 RGBA（无解的行 alpha=0，交给天空）"""
    ti = tex_index(arena)
    p0 = tex_index(None)
    path = ti.get("sbg_swamplandjungle_ground01_c") or p0.get("sbg_swamplandjungle_ground01_c")
    gt = Image.open(path).convert("RGB")
    garr = np.array(gt)
    gh, gw = garr.shape[:2]
    mips = [garr]
    for _ in range(4):
        prev = mips[-1]
        if prev.shape[0] <= 24:
            break
        mips.append(prev[::4, ::4])

    f = focal(cam)
    pr = math.radians(cam["pitch"])
    tx, ty = terr if terr else ([0.0, 300.0], [GROUND_Y, GROUND_Y])

    out = np.zeros((H, W, 4), np.uint8)
    xs = np.arange(W)
    TILE = 7.0
    VTOP = 0.13
    for sy in range(0, H):
        dz = solve_dz(sy, cam, f, pr, tx, ty)
        if dz is None:
            continue
        yaw = math.radians(cam.get("yaw", 0.0))
        cyw, syw = math.cos(yaw), math.sin(yaw)
        Zc = cam["z"] + dz * cyw
        gy = hz(Zc, tx, ty)
        dy = gy - cam["y"]
        zc = -dy * math.sin(pr) + dz * math.cos(pr)
        if zc <= 0.06:
            continue
        dxs = (xs - W / 2.0) * zc / f          # 右向偏移
        X = cam["x"] + dxs * cyw + dz * syw
        Z = Zc - dxs * syw
        dist = np.sqrt(dxs ** 2 + dz ** 2)

        lvl = np.clip(((dist - 20.0) / 20.0).astype(int), 0, len(mips) - 1)
        row = np.zeros((W, 3), np.float32)
        for L in range(len(mips)):
            m = lvl == L
            if not m.any():
                continue
            mg = mips[L]
            mh, mw = mg.shape[:2]
            uu = np.mod(X[m] / TILE, 1.0)
            upix = np.clip((uu * (mw - 1)).astype(int), 0, mw - 1)
            t_ = np.clip(np.log(np.clip(dist[m], NEAR, FAR) / NEAR) / math.log(FAR / NEAR), 0, 1)
            vpix = np.clip(((VTOP + (1.0 - VTOP) * (1.0 - t_)) * (mh - 1)).astype(int), 0, mh - 1)
            row[m] = mg[vpix, upix]
        fog = np.clip((dist - FOG_NEAR) / (FOG_FAR - FOG_NEAR), 0, 0.94)[:, None]
        row = row * (1 - fog) + np.array(fog_rgb, np.float32) * fog
        out[sy, :, :3] = np.clip(row, 0, 255).astype(np.uint8)
        out[sy, :, 3] = 255
    return Image.fromarray(out, "RGBA")


# ---------------- 纸片 ----------------
def collect_props(map_json):
    sc = json.load(open(map_json, encoding="utf-8"))
    return sc, [p for p in sc["props"] if p.get("b")]

def blend_fog(layer, factor, fog_rgb):
    if factor <= 0.001:
        return layer
    r, g, b, a = layer.split()
    solid = Image.new("RGB", layer.size, fog_rgb)
    base = Image.composite(solid, Image.new("RGB", layer.size, fog_rgb), a).convert("RGBA")
    # 用 alpha 做权重，把图层整体向雾色靠
    fogged = Image.new("RGBA", layer.size, fog_rgb + (255,))
    fogged.putalpha(a)
    mixed = Image.blend(layer, fogged, factor)
    mixed.putalpha(a)
    return mixed

def draw_shadows(canvas, props, cam, fog_rgb, terr=None):
    """给贴地物体在地面上投软椭圆阴影，消除『悬浮贴纸』感"""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    n = 0
    for p in props:
        b = p["b"]
        y1 = min(b[1], b[4])
        z1 = min(b[2], b[5])
        if z1 < SKIP_Z:
            continue
        tx_, ty_ = terr if terr else ([0.0, 300.0], [GROUND_Y, GROUND_Y])
        gy = hz((min(b[2], b[5]) + max(b[2], b[5])) / 2.0, tx_, ty_)
        if y1 > gy + 2.2:
            continue            # 只给贴地的物体投
        cx = (min(b[0], b[3]) + max(b[0], b[3])) / 2.0
        cz = (min(b[2], b[5]) + max(b[2], b[5])) / 2.0
        w3 = max(abs(b[3] - b[0]), 0.35)
        q = proj(cx, gy + 0.02, cz, cam)
        if q is None:
            continue
        ql = proj(cx - w3 * 0.55, gy + 0.02, cz, cam)
        qr = proj(cx + w3 * 0.55, gy + 0.02, cz, cam)
        if ql is None or qr is None:
            continue
        rx = max(abs(qr[0] - ql[0]) / 2.0, 3.0)
        ry = max(rx * 0.24, 1.6)      # 地面被压扁
        fog = max(0.0, min(1.0, (q[2] - FOG_NEAR) / (FOG_FAR - FOG_NEAR)))
        al = int(120 * max(0.0, 1.0 - fog))
        if al < 6 or rx > W:
            continue
        d.ellipse([q[0] - rx, q[1] - ry, q[0] + rx, q[1] + ry], fill=(6, 10, 6, al))
        n += 1
    if n:
        lay = lay.filter(ImageFilter.GaussianBlur(7))
        canvas.alpha_composite(lay)
    return n

def draw_props(canvas, props, cam, arena, fog_rgb, terr=None):
    ti = tex_index(arena)
    n_done = 0
    items = []
    for i, p in enumerate(props):
        b = p["b"]
        z1 = min(b[2], b[5])
        if z1 < SKIP_Z:
            continue
        png = ti.get(base_name(p["n"]))
        if not png:
            continue
        items.append((z1, i, p, png))
    items.sort(key=lambda t: -t[0])          # 远 -> 近

    for z1, i, p, png in items:
        b = p["b"]
        x1, x2 = min(b[0], b[3]), max(b[0], b[3])
        y1, y2 = min(b[1], b[4]), max(b[1], b[4])
        if x2 - x1 < 0.02 or y2 - y1 < 0.02:
            continue
        q = [proj(x1, y1, z1, cam), proj(x2, y1, z1, cam),
             proj(x2, y2, z1, cam), proj(x1, y2, z1, cam)]
        if any(v is None for v in q):
            continue
        sx1 = min(v[0] for v in q); sx2 = max(v[0] for v in q)
        sy1 = min(v[1] for v in q); sy2 = max(v[1] for v in q)
        if sx2 - sx1 < 1.0 or sy2 - sy1 < 1.0:
            continue
        if sx2 < -20 or sx1 > W + 20:
            continue
        depth = q[0][2]
        # 裁掉画面外的部分，避免巨图 resize
        cx0, cy0 = max(0, int(sx1)), max(0, int(sy1))
        cx1, cy1 = min(W, int(math.ceil(sx2))), min(H, int(math.ceil(sy2)))
        if cx1 <= cx0 or cy1 <= cy0:
            continue
        tw, th = cx1 - cx0, cy1 - cy0
        U0 = (cx0 - sx1) / (sx2 - sx1)
        U1 = (cx1 - sx1) / (sx2 - sx1)
        V0 = (cy0 - sy1) / (sy2 - sy1)
        V1 = (cy1 - sy1) / (sy2 - sy1)
        lay = Image.open(png).convert("RGBA")
        sw, sh = lay.width, lay.height
        # 只截取需要的贴图区域，再 resize 到目标块
        # 注意：贴图 v=0 是顶部，屏幕 cy 增大方向是向下，方向一致
        crop = lay.crop((int(U0 * sw), int(V0 * sh), max(int(U1 * sw), int(U0 * sw) + 1),
                         max(int(V1 * sh), int(V0 * sh) + 1)))
        if crop.width < 1 or crop.height < 1:
            continue
        crop = crop.resize((tw, th), Image.LANCZOS)
        # 超大纸片（水面/雾片/大底板）压暗透明度，否则会糊住整个画面
        if tw * th > W * H * 0.10:
            a_big = np.array(crop.split()[3]).astype(np.float32) * 0.28
            crop.putalpha(Image.fromarray(np.clip(a_big, 0, 255).astype(np.uint8)))
        # 贴地物体：底部做 alpha 渐隐，避免一堆纸片在坡上齐刷刷切边
        if terr is not None:
            tx_, ty_ = terr
            gy_ = hz((min(b[2], b[5]) + max(b[2], b[5])) / 2.0, tx_, ty_)
            if y1 <= gy_ + 0.6 and th > 6:
                fade = min(int(th * 0.16), 40)
                if fade >= 2:
                    a_ = np.array(crop.split()[3]).astype(np.float32)
                    ramp_ = np.linspace(1.0, 0.0, fade) ** 0.8
                    a_[th - fade:, :] *= ramp_[:, None]
                    crop.putalpha(Image.fromarray(np.clip(a_, 0, 255).astype(np.uint8)))
        fogf = 0.78 * max(0.0, min(0.94, (depth - FOG_NEAR) / (FOG_FAR - FOG_NEAR)))
        if fogf > 0.002:
            crop = blend_fog(crop, fogf, fog_rgb)
        canvas.alpha_composite(crop, (cx0, cy0))
        n_done += 1
    return n_done

# ---------------- 接缝柔化 / 光晕 ----------------
def soften_horizon(img, cam, half=34):
    """在地平线上下做垂直方向柔化，彻底磨掉天空/地面的硬接缝"""
    hor = int(round(horizon_sy(cam)))
    y0, y1 = max(0, hor - half), min(H, hor + half)
    if y1 - y0 < 4:
        return img
    band = img.crop((0, y0, W, y1))
    blurred = band.filter(ImageFilter.GaussianBlur(9))
    # 三角权重：地平线处 1，边缘 0
    w = 1.0 - np.abs(np.arange(y1 - y0) - (hor - y0)) / float(half)
    w = np.clip(w, 0, 1) ** 1.2
    a = np.array(band).astype(np.float32)
    b = np.array(blurred).astype(np.float32)
    out = a * (1 - w[:, None, None]) + b * w[:, None, None]
    img = img.copy()
    img.paste(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), (0, y0))
    return img

def bloom(img, thresh=168, radius=22, strength=0.34):
    """高光扩散，模拟游戏后期处理的辉光"""
    a = np.array(img.convert("RGB")).astype(np.float32)
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    m = np.clip((lum - thresh) / (255.0 - thresh), 0, 1)
    if m.max() < 0.01:
        return img
    hi = (a * m[:, :, None]).astype(np.uint8)
    hb = Image.fromarray(hi).filter(ImageFilter.GaussianBlur(radius))
    base = a
    add = np.array(hb).astype(np.float32) * strength
    return Image.fromarray(np.clip(base + add, 0, 255).astype(np.uint8))

# ---------------- 后处理 ----------------
def post(img, cam):
    im = img.convert("RGB")
    # 暗角
    mask = Image.new("L", (W, H), 0)
    d = np.zeros((H, W))
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    v = np.clip(1.0 - 0.55 * np.clip((d - 0.45) / 0.55, 0, 1) ** 1.6, 0, 1)
    arr = np.array(im).astype(np.float32)
    arr *= v[:, :, None]
    # 青绿偏移 + 轻微降饱和
    rgb = arr
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    sat = 0.79
    rgb = lum[:, :, None] + (rgb - lum[:, :, None]) * sat
    rgb[:, :, 0] *= 0.95
    rgb[:, :, 1] *= 1.02
    rgb[:, :, 2] *= 1.00
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    im = ImageEnhance.Contrast(im).enhance(1.07)
    im = ImageEnhance.Brightness(im).enhance(1.03)
    return im

# ---------------- 主流程 ----------------
def render(map_json, out_png=None, cam=None, arena=None):
    cam = cam or CAM
    sc, props = collect_props(map_json)
    if arena is None:
        arena = sc.get("arena", "").replace("sbg_swamplandjungle_", "") or None

    sky = build_sky(cam, arena)
    sarr = np.array(sky)
    hor = int(max(0, horizon_sy(cam)))
    band = sarr[max(0, hor - 24):max(1, hor - 2)]        # 只取地平线上方真实天空色
    fog_rgb = tuple(int(v) for v in band.reshape(-1, 3).mean(axis=0)) if band.size else (99, 111, 98)

    terr = height_curve(props, arena or "x")
    ground = build_ground(cam, arena, fog_rgb, terr)
    canvas = sky.convert("RGBA")
    canvas.alpha_composite(ground)

    ns = draw_shadows(canvas, props, cam, fog_rgb, terr)
    n = draw_props(canvas, props, cam, arena, fog_rgb, terr)
    print("  阴影 %d" % ns)
    canvas = soften_horizon(canvas.convert("RGB"), cam).convert("RGBA")
    final = post(canvas, cam)
    final = bloom(final)

    os.makedirs(OUT, exist_ok=True)
    outp = out_png or os.path.join(OUT, "v2_%s.png" % (arena or "map"))
    final.save(outp)
    print("  纸片 %d/%d  地平线 y=%d  雾色 %s -> %s" % (n, len(props), hor, fog_rgb, outp))
    return outp, fog_rgb

if __name__ == "__main__":
    import sys
    ids = sys.argv[1:] or ["001"]
    for a in ids:
        print("== arena", a)
        render(os.path.join(EX, "map_%s.json" % a),
               os.path.join(OUT, "v2_%s.png" % a), arena=a)
