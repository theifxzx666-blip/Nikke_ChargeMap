# -*- coding: utf-8 -*-
"""全角度覆盖栅格 —— 求「最佳充能点」，不设候选数上限。

与 scan_charge.py 的区别
------------------------
scan_charge.py 是「采样射线 + top-K + 角距强制分散」，本质是找**一组能标注的点**，
会主动丢掉挨得近的点，因而可能漏掉真实峰值，也无法回答「这个点的角度窗口有多宽」。

本脚本改为**完整覆盖**：
  1. 把每个可充能物体的所有三角形反投影到 (yaw, pitch) 角度域；
  2. 按 0.25° 栅格做点在三角形内判定，得到「每个物体在哪些瞄准方向上被命中」的掩膜；
  3. 逐格累加不同物体数 → 整个瞄准空间的穿透段数热力图（无上限、无间隔约束）；
  4. 取全局峰值 + 连通域，得到「最佳充能点」及其**角度容差窗口**；
  5. 用精确 Möller–Trumbore 复核该角度，防止栅格化误差。

配置来源（全部拆包）
--------------------
  阵位        cover_1..5 世界变换                          -> 导出/slots.json
  相机        field of view = 60 / near 0.1 / far 300       -> spotcameracontrol
  hitbox      root: soft / medium / hard                    -> ConfigBattleTable
  排除        root: cover_object（自家掩体）
  爆裂条      burst_energy_max = 1000000（显示口径 /100 = 10000）
  每发        小红帽 SR 攻击充能 2.80% -> 280 能量/发

用法
----
  python scan_best.py 001
  python scan_best.py all
  python scan_best.py all --step 0.1
"""
import json, math, os, sys
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W_BAR = 10000.0
PER_SHOT_PCT = 2.80                       # 小红帽 SR 攻击充能（%）
CHARGE = PER_SHOT_PCT / 100.0 * W_BAR     # 280 能量/发
GUN_H = 1.45                              # 枪口高度（表现参数）

HITBOX = {"soft": 100, "medium": 500, "hard": 1000}
COVER = "cover_object"
MAX_SPAN = 60.0
MIN_DIST = 1.0

STEP = 0.25
YAW = (-45.0, 45.0)
PITCH = (-3.0, 20.0)


# ---------------------------------------------------------------- 数据装载
def load_tris(props, maxdist=None):
    tris, owner, objs = [], [], []
    skipped = {"cover": [], "huge": []}
    for p in props:
        g = p.get("g")
        if g == COVER:
            skipped["cover"].append(p.get("n", ""))
            continue
        if g not in HITBOX:
            continue
        v = p.get("v") or []
        idx = p.get("i") or []
        if len(v) < 3 or len(idx) < 3:
            continue
        xs = [c[0] for c in v]; ys = [c[1] for c in v]; zs = [c[2] for c in v]
        span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        if span > MAX_SPAN:
            skipped["huge"].append((p.get("n", ""), round(span, 1), g))
            continue
        oi = len(objs)
        objs.append(dict(name=p.get("n", ""), grp=g, hp=HITBOX[g], span=round(span, 1),
                         center=[round(sum(xs) / len(v), 2), round(sum(ys) / len(v), 2),
                                 round(sum(zs) / len(v), 2)]))
        for t in range(0, len(idx) - 2, 3):
            a, b, c = idx[t], idx[t + 1], idx[t + 2]
            if a < len(v) and b < len(v) and c < len(v):
                tris.append([v[a], v[b], v[c]])
                owner.append(oi)
    return objs, np.array(tris, dtype=np.float64), np.array(owner, dtype=np.int32), skipped


# ---------------------------------------------------------------- 角度域栅格
def build_mask(origin, tri, oi, nobj, gy, gp, maxdist=None):
    """返回 (nobj, nPitch, nYaw) bool：物体是否在某个瞄准方向上被射线穿过。"""
    ny, npp = len(gy), len(gp)
    mask = np.zeros((nobj, npp, ny), dtype=bool)
    d = tri - origin[None, None, :]
    dist = np.linalg.norm(d, axis=2)
    ya = np.degrees(np.arctan2(d[:, :, 0], d[:, :, 2]))
    pa = np.degrees(np.arctan2(d[:, :, 1], np.hypot(d[:, :, 0], d[:, :, 2])))
    sy = gy[1] - gy[0]
    sp = gp[1] - gp[0]

    ok = np.all(np.abs(ya) < 88.0, axis=1)                      # 剔除跨到身后的大三角
    ok &= (ya.max(1) > gy[0]) & (ya.min(1) < gy[-1])
    ok &= (pa.max(1) > gp[0]) & (pa.min(1) < gp[-1])
    if maxdist:
        ok &= (dist.max(1) <= maxdist)
    sel = np.where(ok)[0]

    for t in sel:
        y0, y1, y2 = ya[t]
        p0, p1, p2 = pa[t]
        i0 = max(0, int(math.floor((min(y0, y1, y2) - gy[0]) / sy)))
        i1 = min(ny - 1, int(math.ceil((max(y0, y1, y2) - gy[0]) / sy)))
        j0 = max(0, int(math.floor((min(p0, p1, p2) - gp[0]) / sp)))
        j1 = min(npp - 1, int(math.ceil((max(p0, p1, p2) - gp[0]) / sp)))
        if i1 < i0 or j1 < j0:
            continue
        Y, P = np.meshgrid(gy[i0:i1 + 1], gp[j0:j1 + 1])
        d1 = (y1 - y0) * (P - p0) - (p1 - p0) * (Y - y0)
        d2 = (y2 - y1) * (P - p1) - (p2 - p1) * (Y - y1)
        d3 = (y0 - y2) * (P - p2) - (p0 - p2) * (Y - y2)
        neg = (d1 < -1e-12) | (d2 < -1e-12) | (d3 < -1e-12)
        pos = (d1 > 1e-12) | (d2 > 1e-12) | (d3 > 1e-12)
        inside = ~(neg & pos)
        if inside.any():
            mask[oi[t], j0:j1 + 1, i0:i1 + 1] |= inside
    return mask, len(sel), len(tri)


# ---------------------------------------------------------------- 精确复核
def ray_dirs(yaw, pitch):
    y = math.radians(yaw); p = math.radians(pitch)
    return np.array([[math.sin(y) * math.cos(p), math.sin(p), math.cos(y) * math.cos(p)]])


def exact_hits(origin, yaw, pitch, tri, oi, maxdist=None):
    """Möller–Trumbore 精确求交，返回 (物体序号, 距离) 列表，按距离升序。"""
    dirs = ray_dirs(yaw, pitch)
    v0 = tri[:, 0, :]; e1 = tri[:, 1, :] - v0; e2 = tri[:, 2, :] - v0
    pv = np.cross(dirs[:, None, :], e2[None, :, :])
    det = np.einsum("tj,mtj->mt", e1, pv)
    m = np.abs(det) > 1e-9
    inv = np.where(m, 1.0 / np.where(m, det, 1.0), 0.0)
    tv = origin[None, None, :] - v0[None, :, :]
    u = np.einsum("mtj,mtj->mt", np.broadcast_to(tv, (1,) + tv.shape[1:]), pv) * inv
    qv = np.cross(tv, e1[None, :, :])
    vv = np.einsum("mj,mtj->mt", dirs, qv) * inv
    t = np.einsum("tj,mtj->mt", e2, qv) * inv
    hit = m & (u >= -1e-5) & (vv >= -1e-5) & (u + vv <= 1 + 1e-5) & (t > MIN_DIST)
    if maxdist:
        hit &= (t <= maxdist)
    tt = np.where(hit, t, np.inf)[0]
    best = {}
    for k in np.where(np.isfinite(tt))[0]:
        o = int(oi[k])
        if o not in best or tt[k] < best[o]:
            best[o] = float(tt[k])
    return sorted(((o, dd) for o, dd in best.items()), key=lambda x: x[1])


# ---------------------------------------------------------------- 稳健性
def min_filter(cnt, k):
    """k×k 邻域最小值：某格的值 = 它周围 ±(k//2) 格内**都至少**能达到的段数。
    用来把「0.25° 的窄缝峰值」和「能稳稳瞄住的点」区分开。"""
    if k <= 1:
        return cnt.copy()
    pad = k // 2
    a = np.pad(cnt, pad, mode="edge")
    h, w = cnt.shape
    stack = [a[dj:dj + h, di:di + w] for dj in range(k) for di in range(k)]
    return np.min(np.stack(stack), axis=0)


# ---------------------------------------------------------------- 连通域
def regions(cnt, value):
    """返回所有取值为 value 的连通域（8 邻接），按面积降序。"""
    hit = cnt == value
    seen = np.zeros_like(hit)
    h, w = hit.shape
    out = []
    for j in range(h):
        for i in range(w):
            if not hit[j, i] or seen[j, i]:
                continue
            q = deque([(j, i)]); seen[j, i] = True; cells = []
            while q:
                cj, ci = q.popleft(); cells.append((cj, ci))
                for dj in (-1, 0, 1):
                    for di in (-1, 0, 1):
                        nj, ni = cj + dj, ci + di
                        if 0 <= nj < h and 0 <= ni < w and hit[nj, ni] and not seen[nj, ni]:
                            seen[nj, ni] = True; q.append((nj, ni))
            js = [c[0] for c in cells]; is_ = [c[1] for c in cells]
            out.append(dict(size=len(cells),
                            j=float(np.mean(js)), i=float(np.mean(is_)),
                            j0=min(js), j1=max(js), i0=min(is_), i1=max(is_)))
    out.sort(key=lambda r: -r["size"])
    return out


# ---------------------------------------------------------------- 热力图
def save_heatmap(cnt, gy, gp, path, title, mark=None, mark2=None, crop=None, sc=6):
    """cnt:(nPitch,nYaw)  gy:yaw 轴  gp:pitch 轴。crop=(yaw0,yaw1,p0,p1) 局部放大。"""
    if crop:
        i0 = int(np.searchsorted(gy, crop[0])); i1 = int(np.searchsorted(gy, crop[1]))
        j0 = int(np.searchsorted(gp, crop[2])); j1 = int(np.searchsorted(gp, crop[3]))
        cnt = cnt[j0:j1 + 1, i0:i1 + 1]; gy = gy[i0:i1 + 1]; gp = gp[j0:j1 + 1]
    h, w = cnt.shape
    mx = max(int(cnt.max()), 1)
    t = cnt.astype(np.float64) / mx
    r = np.clip(1.55 * t - 0.22, 0, 1)
    g = np.clip(1.65 * t, 0, 1)
    b = np.clip(1.15 - 1.9 * t, 0, 1)
    img = (np.stack([r, g, b], axis=2) * 255).astype(np.uint8)[::-1]
    data = Image.fromarray(img).resize((w * sc, h * sc), Image.NEAREST)

    LE, TOP, BO, RI = 54, 34, 34, 12
    canvas = Image.new("RGB", (w * sc + LE + RI, h * sc + TOP + BO), (9, 17, 14))
    canvas.paste(data, (LE, TOP))
    d = ImageDraw.Draw(canvas)
    def txt(xy, msg, font, fill=(230, 240, 235)):
        try:
            d.text(xy, msg, font=font, fill=fill, stroke_width=2, stroke_fill=(6, 12, 9))
        except TypeError:
            d.text(xy, msg, font=font, fill=fill)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
        fb = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 19)
    except Exception:
        f = fb = ImageFont.load_default()

    txt((10, 7), title, fill=(255, 255, 255), font=fb)
    txt((canvas.size[0] - 78, 10), "max %d" % mx, fill=(210, 210, 210), font=f)

    # yaw 轴（底部）
    step_y = 10 if (gy[-1] - gy[0]) > 34 else 5
    ya = math.ceil(gy[0] / step_y) * step_y
    while ya <= gy[-1] + 1e-6:
        x = LE + int((ya - gy[0]) / (gy[1] - gy[0])) * sc + sc // 2
        d.line([(x, TOP + h * sc), (x, TOP + h * sc + 5)], fill=(150, 180, 165), width=1)
        txt((x - 11, TOP + h * sc + 7), "%+d" % ya, fill=(190, 205, 198), font=f)
        ya += step_y
    

    # pitch 轴（左侧）
    step_p = 5 if (gp[-1] - gp[0]) > 12 else 2
    pa = math.ceil(gp[0] / step_p) * step_p
    while pa <= gp[-1] + 1e-6:
        y = TOP + h * sc - int((pa - gp[0]) / (gp[1] - gp[0])) * sc - sc // 2
        d.line([(LE - 6, y), (LE - 1, y)], fill=(150, 180, 165), width=1)
        txt((16, y - 9), "%+d" % pa, fill=(190, 205, 198), font=f)
        pa += step_p
    txt((16, TOP - 20), "pitch", fill=(120, 145, 133), font=f)

    def px_of(yaw, pitch):
        i = (yaw - gy[0]) / (gy[1] - gy[0])
        j = (pitch - gp[0]) / (gp[1] - gp[0])
        return LE + (i + 0.5) * sc, TOP + (h - 1 - j + 0.5) * sc

    if mark:
        px, py = px_of(*mark)
        R = max(11, sc + 4)
        d.ellipse([px - R, py - R, px + R, py + R], outline=(255, 255, 255), width=2)
        for a, b in (((-R - 12, 0), (-R - 3, 0)), ((R + 3, 0), (R + 12, 0)),
                     ((0, -R - 12), (0, -R - 3)), ((0, R + 3), (0, R + 12))):
            d.line([(px + a[0], py + a[1]), (px + b[0], py + b[1])], fill=(255, 255, 255), width=2)
        tx = px + R + 13
        if tx > canvas.size[0] - 150:
            tx = px - R - 150
        txt((tx, py - R - 8), "峰值 %+.1f° / %+.1f°" % mark, fill=(255, 255, 255), font=f)
    if mark2:
        px, py = px_of(*mark2)
        R = max(15, sc + 8)
        d.ellipse([px - R, py - R, px + R, py + R], outline=(120, 235, 255), width=2)
        txt((px - R, py + R + 2), "1°稳定", fill=(120, 235, 255), font=f)
    canvas.save(path)


# ---------------------------------------------------------------- 主流程
def scan(arena, keys, step, maxdist=None):
    asm = json.load(open(os.path.join("导出", "assembly_%s.json" % arena), encoding="utf-8"))
    slots = json.load(open(os.path.join("导出", "slots.json"), encoding="utf-8"))[arena]

    objs, tri, oi, skipped = load_tris(asm["props"], maxdist)
    gy = np.round(np.arange(YAW[0], YAW[1] + 1e-9, step), 4)
    gp = np.round(np.arange(PITCH[0], PITCH[1] + 1e-9, step), 4)
    print("  hitbox obj=%d tri=%d  排除 cover=%d 远景=%d  栅格 %dx%d 步进 %.2f°" % (
        len(objs), len(tri), len(skipped["cover"]), len(skipped["huge"]), len(gy), len(gp), step))
    if skipped["huge"]:
        for n, s, g in skipped["huge"][:6]:
            print("    远景剔除: %-44s span=%.1f  %s" % (n[:44], s, g))

    out_slots = {}
    for sk in keys:
        e = slots[sk]
        cp = e["character_position"][0] if isinstance(e.get("character_position"), list) else None
        if cp is None:
            continue
        origin = np.array([cp[0], cp[1] + GUN_H, cp[2]], dtype=np.float64)

        mask, nsel, ntri = build_mask(origin, tri, oi, len(objs), gy, gp, maxdist)
        cnt = mask.sum(axis=0)                     # (nPitch, nYaw)
        mx = int(cnt.max())

        # 稳健性：k=5 -> 1.0° 窗口；k=9 -> 2.0° 窗口
        k1 = max(1, int(round(1.0 / step)) | 1)
        k2 = max(1, int(round(2.0 / step)) | 1)
        e1 = min_filter(cnt, k1)
        e2 = min_filter(cnt, k2)
        r1 = int(e1.max())
        r2 = int(e2.max())

        regs = regions(cnt, mx)
        print("     %s  峰值 %d 段 | 1°窗口稳 %d 段 | 2°窗口稳 %d 段 | 峰值区 %d 个（最大 %.2f°×%.2f°）" % (
            sk, mx, r1, r2, len(regs),
            (regs[0]["i1"] - regs[0]["i0"] + 1) * step,
            (regs[0]["j1"] - regs[0]["j0"] + 1) * step))

        # 推荐点：在「1° 窗口内不掉段」的格子里取段数最高者（并列取窗口更宽者）
        rec = None
        if r1 > 0:
            jj, ii = np.unravel_index(int(np.argmax(e1)), e1.shape)
            # 在该等值区里取 e2 最大的格，作为更稳的子位置
            best_j, best_i = int(jj), int(ii)
            eq = e1 == r1
            jj2, ii2 = np.where(eq)
            k3 = np.argmax(e2[jj2, ii2])
            best_j, best_i = int(jj2[k3]), int(ii2[k3])
            yaw = float(gy[best_i]); pit = float(gp[best_j])
            hits = exact_hits(origin, yaw, pit, tri, oi, maxdist)
            rec = dict(yaw=yaw, pitch=pit, n=len(hits), win_y=1.0, win_p=1.0,
                       grid_cells=int((cnt == mx).sum()), objs=hits)

        # 每个峰值区域取质心，精确复核
        cands = []
        for r in regs:
            yaw = float(gy[int(round(r["i"]))])
            pit = float(gp[int(round(r["j"]))])
            hits = exact_hits(origin, yaw, pit, tri, oi, maxdist)
            cands.append(dict(yaw=yaw, pitch=pit, n=len(hits),
                              win_y=round((r["i1"] - r["i0"] + 1) * step, 2),
                              win_p=round((r["j1"] - r["j0"] + 1) * step, 2),
                              grid_cells=r["size"],
                              objs=hits))
        cands.sort(key=lambda c: (-c["n"], -c["grid_cells"]))

        # 角度去重：同一区域已按连通域唯一，但复核后 n 可能变化，重排即可
        bestn = cands[0]["n"] if cands else 0
        keep = [c for c in cands if c["n"] == bestn][:8]
        other = [c for c in cands if c["n"] < bestn]
        # 其余次优点也全带上（按 n 降序，最多 40 条，供参考）
        other.sort(key=lambda c: (-c["n"], -c["grid_cells"]))
        ranked = keep + other[:40]

        def finalize(c):
            c["pct"] = round(c["n"] * PER_SHOT_PCT, 2)
            c["energy"] = c["n"] * CHARGE
            c["shots"] = int(math.ceil(W_BAR / (c["n"] * CHARGE))) if c["n"] else None
            c["first"] = round(c["objs"][0][1], 1) if c["objs"] else None
            c["last"] = round(c["objs"][-1][1], 1) if c["objs"] else None
            c["detail"] = [dict(name=objs[o]["name"], grp=objs[o]["grp"], hp=objs[o]["hp"],
                                d=round(dd, 1), center=objs[o]["center"]) for o, dd in c["objs"]]
            c.pop("objs", None)
            return c

        for c in ranked:
            finalize(c)
        if rec:
            finalize(rec)

        # 全空间统计：每个段数出现多少个瞄准格
        hist = {}
        for v in range(mx, 0, -1):
            k = int((cnt == v).sum())
            if k:
                hist[str(v)] = k

        out_slots[sk] = dict(
            char=[round(float(v), 3) for v in cp],
            origin=[round(float(v), 3) for v in origin],
            cam=e.get("cam"),
            n_max=mx, n_r1=r1, n_r2=r2,
            best=ranked[0] if ranked else None,
            rec=rec,
            peak_regions=len(regs), hist=hist, cands=ranked)

        hp = os.path.join("render", "best_%s_%s%s_heat.png" % (
            arena, sk, "" if not maxdist else "_d%d" % int(maxdist)))
        mk = (ranked[0]["yaw"], ranked[0]["pitch"]) if ranked else None
        mk2 = (rec["yaw"], rec["pitch"]) if rec else None
        save_heatmap(cnt, gy, gp, hp,
                     "%s %s  峰值 %d 段 (%.1f%%)  %s发%s" % (
                         arena, sk, mx, mx * PER_SHOT_PCT,
                         int(math.ceil(W_BAR / (mx * CHARGE))) if mx else "-",
                         "" if not maxdist else "  ≤%dm" % int(maxdist)),
                     mark=mk, mark2=mk2)
        # 局部放大：围绕峰值 ±14° / -6~+8°
        if mk and not maxdist:
            zc = (max(YAW[0], mk[0] - 13), min(YAW[1], mk[0] + 13),
                  max(PITCH[0], mk[1] - 5.5), min(PITCH[1], mk[1] + 7.5))
            save_heatmap(cnt, gy, gp, os.path.join("render", "zoom_%s_%s.png" % (arena, sk)),
                         "%s %s  峰值 %d 段 · %s发" % (arena, sk, mx,
                                                   int(math.ceil(W_BAR / (mx * CHARGE))) if mx else "-"),
                         mark=mk, mark2=None, crop=zc, sc=14)

    return dict(arena="sbg_swamplandjungle_%s" % arena, step=step, maxdist=maxdist,
                yaw_range=list(YAW), pitch_range=list(PITCH),
                fov=60.0, near=0.1, far=300.0,
                charge_per_shot=CHARGE, bar=W_BAR,
                hitbox_groups=HITBOX, excluded=["cover_object", "static_object", "noncol_object"],
                slots=out_slots)


def main():
    global YAW, PITCH
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    step = STEP
    maxdist = None
    for a in sys.argv[1:]:
        if a.startswith("--step="):
            step = float(a.split("=")[1])
        elif a.startswith("--maxdist="):
            maxdist = float(a.split("=")[1])
        elif a.startswith("--yaw="):
            v = a.split("=")[1].split(",")
            YAW = (float(v[0]), float(v[1]))
        elif a.startswith("--pitch="):
            v = a.split("=")[1].split(",")
            PITCH = (float(v[0]), float(v[1]))
    arg = args[0] if args else "001"
    keys = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]
    arenas = ["001", "002", "003", "004", "005"] if arg == "all" else [arg]
    os.makedirs("render", exist_ok=True)
    for a in arenas:
        print("== arena", a, "" if not maxdist else "(≤%dm)" % maxdist)
        d = scan(a, keys, step, maxdist)
        out = os.path.join("导出", "best_%s%s.json" % (a, "" if not maxdist else "_d%d" % int(maxdist)))
        json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False)
        for sk, r in d["slots"].items():
            b = r["best"]
            c = r.get("rec")
            if b:
                print("   %s  理论峰值 %d段 %.1f%% %d发 @yaw%+.2f pitch%+.2f (窗口%.2f°×%.2f°)" % (
                    sk, b["n"], b["pct"], b["shots"], b["yaw"], b["pitch"], b["win_y"], b["win_p"]))
            if c:
                print("          推荐点 %d段 %.1f%% %d发 @yaw%+.2f pitch%+.2f (1°窗口不掉段) 首击 %.1fm 共%d件" % (
                    c["n"], c["pct"], c["shots"], c["yaw"], c["pitch"], c["first"], len(c["detail"])))
        print("   ->", out)


if __name__ == "__main__":
    main()
