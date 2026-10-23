# -*- coding: utf-8 -*-
"""玩家视角 · 像素级选点（v10，取代 scan_fp.py 的 v9 口径）

四条需求 → 四个改动
-------------------
| 需求                     | 旧（v9）                              | 新（v10）                                  |
|--------------------------|---------------------------------------|--------------------------------------------|
| 过滤只有单判的点         | 只淘汰稳态 0 段                       | 稳态 < `MIN_MULTI`(2) 段直接不进候选        |
| 我方掩体不作判定点       | `cover_object` 不计段数（已排除）     | 再加一条：掩体占住的像素在深度图里被截断，准星压上去就是 0 段 |
| 精确到像素级             | 0.25° 角度栅格（≈4px）、角距去重      | 1600×900 逐像素、像素距离去重              |
| 打多判 / 打最多 / 要稳   | 排序 (-稳态, -首轮, -齐射)            | 排序 (-稳态, -首轮, -支撑半径) + 逐像素腐蚀 |
| 点数可调（默认 5）        | 写死 12                               | 一次算满 `N_MAX`，页面 5/8/12/24 切         |

为什么必须从「角度」换成「像素」——一个被旧口径系统忽略的误差
------------------------------------------------------------
  v9 直接在**枪口角度域**扫描，等价于假设「准星指哪，枪口就打哪」。
  实际链路是：准星像素 → 相机射线 → 命中点 Pc → 枪口瞄准 Pc。
  相机在 `camera_position`（角色身后 4.5m、右偏 1.2m、高 0.89m），枪口在角色身上，
  两者不是同一点 —— **近景 15m 处横移 1.2m 就是 4.6° ≈ 80px**。
  也就是说：v9 报的「yaw −43.5 / pitch −6.4 有 3 段」，玩家照着把准星挪到对应像素，
  枪口实际打到的是别的东西。这个偏差随距离衰减，但恰恰最近的那批点误差最大。

  本版把主循环放到像素上：先算相机深度图 → 每个像素反推枪口角度 → 查角度域段数。
  选点在像素上做，角度只是**导出量**。

三个可借鉴的成熟算法（不是自创）
------------------------------
  · Z-buffer 光栅化（深度图）—— 图形学第一课。用它对每个像素求「准星压在这儿会锁到哪件东西」。
  · 形态学腐蚀 / 可分离最小值滤波 —— 「准星歪 R 像素还掉不掉段」。
    ±R 的**方框**结构元包含半径 R 的圆，所以结论比圆形腐蚀更保守（说稳就是真稳）。
  · NMS（non-maximum suppression）+ Jaccard —— 目标检测去重的老办法。
    判据从「角度」换成「屏幕像素中心距」，就和分辨率 / FOV / 运镜彻底解耦。

用法
----
  python scan_px.py mw003
  python scan_px.py all                # 沼泽丛林 001~005
  python scan_px.py mw                 # 母鲸领域 mw001~003
  python scan_px.py all --min-multi=3 --step=0.05 --no-occ
"""
import json, math, os, re, sys

import numpy as np

import scan_best as sb

# ---------------------------------------------------------------- 常量
W, H, FOV = 1600, 900, 60.0
HALF_Y = math.degrees(math.atan(math.tan(math.radians(FOV / 2)) * W / H))   # 45.7°
PX_Y = W / (2 * HALF_Y)                      # 17.5 px/°（横）
PX_P = H / FOV                               # 15.0 px/°（纵）
STEP = 0.05                                  # 角度域栅格（≈0.875px 横 / 0.75px 纵）

MIN_MULTI = 2                                # 稳态段数下限（单判 = 1 段 → 淘汰）
N_MAX = 24                                   # 一次算满
N_SHOW = 5                                   # 默认显示
GAP_MIN, GAP_OK = 50.0, 72.0                 # 屏幕中心距：<50 必冲突 / >72 直接共存
DEPTH_DIFF = 15.0                            # 50~72px 之间要求首击纵深差 ≥ 15m
JACCARD = 0.5                                # 命中集合重合度上限
LEVELS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16]   # 支撑半径档位（px）
POOL_MAX = 1200                              # 送进精确复核的候选数
SUPPRESS = 6                                 # 候选池内同一平台抑制半径（px）
MARGIN = 26                                  # 靶心（46px）要完整落在画面内的边距

BLOCK_GROUPS = ("static_object", "ground")   # 只挡不充能
SOLID_GROUPS = ("soft", "medium", "hard", "static_object", "ground", "cover_object")

YAW = (-48.0, 48.0)
PITCH = (-12.0, 22.0)
PITCH_MW = (-24.0, 24.0)


# ---------------------------------------------------------------- 装载
def expand(e, key):
    v = e.get(key)
    if isinstance(v, list) and v and isinstance(v[0], list):
        return v[0]
    return v


def load_props(props, groups, maxspan=sb.MAX_SPAN):
    """按组名抽三角面。返回 (objs, tri, oi, skipped)。大于 maxspan 的远景件直接丢。"""
    tris, owner, objs, skipped = [], [], [], {"cover": [], "huge": []}
    for p in props:
        g = p.get("g")
        if g not in groups:
            if g == "cover_object":
                skipped["cover"].append(p.get("n", ""))
            continue
        v = p.get("v") or []
        idx = p.get("i") or []
        if len(v) < 3 or len(idx) < 3:
            continue
        xs = [c[0] for c in v]; ys = [c[1] for c in v]; zs = [c[2] for c in v]
        span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        if span > maxspan:
            skipped["huge"].append((p.get("n", ""), round(span, 1), g))
            continue
        oi = len(objs)
        objs.append(dict(name=p.get("n", ""), grp=g, hp=sb.HITBOX.get(g),
                         span=round(span, 1),
                         center=[round(sum(xs) / len(v), 2), round(sum(ys) / len(v), 2),
                                 round(sum(zs) / len(v), 2)]))
        for t in range(0, len(idx) - 2, 3):
            a, b, c = idx[t], idx[t + 1], idx[t + 2]
            if a < len(v) and b < len(v) and c < len(v):
                tris.append([v[a], v[b], v[c]])
                owner.append(oi)
    if not tris:
        return objs, np.zeros((0, 3, 3)), np.zeros(0, np.int32), skipped
    return objs, np.array(tris, np.float64), np.array(owner, np.int32), skipped


# ---------------------------------------------------------------- 相机深度图
def camera_depth(tri, cam, w=W, h=H, fov=FOV, near=0.12):
    """Z-buffer 光栅化：每个像素沿相机射线看到的**最近实心表面**，返回 (depth, P)。

    depth 是相机空间 z（沿视线），P 是世界点。天空/未命中处 depth=inf。
    """
    th = math.tan(math.radians(fov / 2))
    asp = w / h
    zb = np.full((h, w), np.inf, np.float64)
    if len(tri) == 0:
        return zb, np.zeros((h, w, 3))
    V = tri.reshape(-1, 3) - cam[None, :]
    z = V[:, 2]
    okv = z > near
    with np.errstate(divide="ignore", invalid="ignore"):
        sx = ((V[:, 0] / (z * th * asp)) * 0.5 + 0.5) * w
        sy = (0.5 - (V[:, 1] / (z * th)) * 0.5) * h
    sx = np.where(okv, sx, np.nan)
    sy = np.where(okv, sy, np.nan)
    SX = sx.reshape(-1, 3); SY = sy.reshape(-1, 3); Z = z.reshape(-1, 3)
    for t in range(len(tri)):
        if not (okv[3 * t] and okv[3 * t + 1] and okv[3 * t + 2]):
            continue
        x0, x1, x2 = SX[t]; y0, y1, y2 = SY[t]
        if max(x0, x1, x2) < 0 or min(x0, x1, x2) >= w or max(y0, y1, y2) < 0 or min(y0, y1, y2) >= h:
            continue
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        i0 = max(0, int(math.floor(min(x0, x1, x2)))); i1 = min(w - 1, int(math.ceil(max(x0, x1, x2))))
        j0 = max(0, int(math.floor(min(y0, y1, y2)))); j1 = min(h - 1, int(math.ceil(max(y0, y1, y2))))
        if i1 < i0 or j1 < j0:
            continue
        X, Y = np.meshgrid(np.arange(i0, i1 + 1) + 0.5, np.arange(j0, j1 + 1) + 0.5)
        l0 = ((x1 - X) * (y2 - Y) - (x2 - X) * (y1 - Y)) / area
        l1 = ((x2 - X) * (y0 - Y) - (x0 - X) * (y2 - Y)) / area
        l2 = 1.0 - l0 - l1
        inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not inside.any():
            continue
        # 透视除法后 1/z 在屏幕空间线性
        zz = 1.0 / (l0 / Z[t][0] + l1 / Z[t][1] + l2 / Z[t][2])
        blk = zb[j0:j1 + 1, i0:i1 + 1]
        np.minimum(blk, np.where(inside, zz, np.inf), out=blk)
    # 反投影
    xs = (np.arange(w) + 0.5 - w / 2) / (w / 2) * th * asp
    ys = (h / 2 - (np.arange(h) + 0.5)) / (h / 2) * th
    DX = np.broadcast_to(xs[None, :], (h, w))
    DY = np.broadcast_to(ys[:, None], (h, w))
    Dz = np.where(np.isfinite(zb), zb, 0.0)
    P = np.stack([cam[0] + DX * Dz, cam[1] + DY * Dz, cam[2] + Dz], axis=2)
    return zb, P


def to_px(P, cam, w=W, h=H, fov=FOV):
    """世界点 → 屏幕像素（相机沿 +z、rotation=identity、FOV 60）。"""
    v = np.asarray(P, float) - np.asarray(cam, float)
    if v[2] <= 0.05:
        return None
    th = math.tan(math.radians(fov / 2))
    ndc_x = v[0] / (v[2] * th * (w / h))
    ndc_y = v[1] / (v[2] * th)
    return [round((ndc_x * .5 + .5) * w, 1), round((.5 - ndc_y * .5) * h, 1)]


# ---------------------------------------------------------------- 角度域栅格
def build_mask_grouped(origin, tri, oi, gy, gp, steady_mask, chunk=40):
    """分块累加：(全部受击体数, 稳态受击体数)。chunk 控内存。"""
    cnt = np.zeros((len(gp), len(gy)), np.int16)
    cnt_st = np.zeros((len(gp), len(gy)), np.int16)
    nobj = int(oi.max()) + 1 if len(oi) else 0
    for s in range(0, nobj, chunk):
        sub = (oi >= s) & (oi < s + chunk)
        if not sub.any():
            continue
        m, _, _ = sb.build_mask(origin, tri[sub], oi[sub] - s, min(chunk, nobj - s), gy, gp, None)
        cnt += m.sum(axis=0)
        keep = steady_mask[s:s + m.shape[0]]
        if keep.any():
            cnt_st += m[keep].sum(axis=0)
    return cnt, cnt_st


def minfilt(a, ka, kb):
    """可分离矩形最小值滤波 = 用 ka×kb 方框做腐蚀，O(n) 而不是 O(n·k²)。"""
    def axis_min(x, k, axis):
        if k <= 1:
            return x
        pad = k // 2
        p = np.pad(x, [(pad, pad) if i == axis else (0, 0) for i in range(x.ndim)], mode="edge")
        out = x.copy()
        for s in range(k):
            sl = [slice(None)] * x.ndim
            sl[axis] = slice(s, s + x.shape[axis])
            np.minimum(out, p[tuple(sl)], out=out)
        return out
    return axis_min(axis_min(a, ka, 1), kb, 0)


def support_radius(nt):
    """支撑半径图：rad[j,i] = 最大的 R（px），使以该像素为中心、±R 的方框内段数不降。

    方框 ⊃ 半径 R 的圆 → 结论保守：报 ±R 就一定稳。
    """
    rad = np.zeros(nt.shape, np.uint8)
    for R in LEVELS:
        k = 2 * R + 1
        E = minfilt(nt, k, k)
        rad[E == nt] = R
    return rad


# ---------------------------------------------------------------- 精确复核
def blocker_dist(origin, yaw, pitch, tri_b):
    """射线到遮挡体（static/ground）的最近距离；没打到返回 inf。"""
    if tri_b is None or not len(tri_b):
        return math.inf
    d = sb.ray_dirs(yaw, pitch)[0]
    v0 = tri_b[:, 0, :]; e1 = tri_b[:, 1, :] - v0; e2 = tri_b[:, 2, :] - v0
    D = np.broadcast_to(d, (len(tri_b), 3))
    pv = np.cross(D, e2)
    det = np.einsum("tj,tj->t", e1, pv)
    m = np.abs(det) > 1e-9
    inv = np.where(m, 1.0 / np.where(m, det, 1.0), 0.0)
    tv = origin - v0
    u = np.einsum("tj,tj->t", tv, pv) * inv
    qv = np.cross(tv, e1)
    vv = np.einsum("tj,tj->t", D, qv) * inv
    t = np.einsum("tj,tj->t", e2, qv) * inv
    ok = m & (u >= -1e-5) & (vv >= -1e-5) & (u + vv <= 1 + 1e-5) & (t > sb.MIN_DIST)
    return float(t[ok].min()) if ok.any() else math.inf


# ---------------------------------------------------------------- 主流程
def scan(arena, min_multi=MIN_MULTI, n_show=N_SHOW, n_max=N_MAX, occ=True,
         step=STEP, yaw_rng=None, pitch_rng=None):
    asm = json.load(open(os.path.join("导出", "assembly_%s.json" % arena), encoding="utf-8"))
    slots = json.load(open(os.path.join("导出", "slots.json"), encoding="utf-8"))[arena]
    props = asm["props"]

    objs, tri, oi, skipped = load_props(
        [p for p in props if p.get("g") in sb.HITBOX], set(sb.HITBOX))
    # 遮挡体 = 地形 + 我方掩体（子弹不会穿过自家掩体）
    _, tri_b, _, _ = load_props(
        [p for p in props if p.get("g") in BLOCK_GROUPS or p.get("g") == "cover_object"],
        set(BLOCK_GROUPS) | {"cover_object"})
    cover_names = [p.get("n", "") for p in props if p.get("g") == "cover_object"]
    _, tri_cover, _, _ = load_props(
        [p for p in props if p.get("g") == "cover_object"], {"cover_object"})
    # 可锁定表面 = 受击体 + 地形（不含我方掩体：掩体占住的像素单独剔除）
    _, tri_all, _, _ = load_props(
        [p for p in props if p.get("g") in SOLID_GROUPS and p.get("g") != "cover_object"],
        (set(SOLID_GROUPS) - {"cover_object"}))

    orgs = {}
    for k in sorted(slots):
        cp = expand(slots[k], "character_position")
        if cp:
            orgs[k] = np.array([cp[0], cp[1] + sb.GUN_H, cp[2]], np.float64)
    view = "cover_3" if "cover_3" in orgs else sorted(orgs)[0]
    org = orgs[view]
    cam = np.array(expand(slots[view], "camera_position"), np.float64)

    # ---- 1) 相机深度图：准星压在这个像素上，会锁到哪件实心物 -----------------
    # 只对「可锁定表面」建深度图（受击体 + 地形），我方掩体单独一张 —— 两者的区别见 2)
    depth, P = camera_depth(tri_all, cam)
    dcov, _ = camera_depth(tri_cover, cam) if len(tri_cover) else (np.full((H, W), np.inf), None)
    hit_px = np.isfinite(depth)
    # 我方掩体挡在前面 → 这个像素不是瞄准点（准星压在自家掩体上打不出去）
    behind_cover = np.isfinite(dcov) & (~hit_px | (dcov < depth - 0.05))
    hit_px &= ~behind_cover

    # ---- 2) 像素 → 枪口角度 ---------------------------------------------
    v = P - org[None, None, :]
    yaw_px = np.degrees(np.arctan2(v[:, :, 0], v[:, :, 2]))
    pit_px = np.degrees(np.arctan2(v[:, :, 1], np.hypot(v[:, :, 0], v[:, :, 2])))
    # 相机与枪口差 1.2m 横 / 0.89m 高 / 4.5m 纵深 → 近景视差可达数度，扫描范围必须由像素反推
    if yaw_rng is None:
        yaw_rng = (float(np.floor(yaw_px[hit_px].min())) - 1, float(np.ceil(yaw_px[hit_px].max())) + 1)
    if pitch_rng is None:
        pitch_rng = (float(np.floor(pit_px[hit_px].min())) - 1, float(np.ceil(pit_px[hit_px].max())) + 1)
    gy = np.round(np.arange(yaw_rng[0], yaw_rng[1] + 1e-9, step), 4)
    gp = np.round(np.arange(pitch_rng[0], pitch_rng[1] + 1e-9, step), 4)
    ii = np.clip(np.round((yaw_px - gy[0]) / step).astype(np.int32), 0, len(gy) - 1)
    jj = np.clip(np.round((pit_px - gp[0]) / step).astype(np.int32), 0, len(gp) - 1)

    steady_mask = np.array([o["grp"] in ("medium", "hard") for o in objs])
    cnt_g, cnt_st_g = build_mask_grouped(org, tri, oi, gy, gp, steady_mask)
    N = np.where(hit_px, cnt_g[jj, ii], 0).astype(np.int16)      # 逐像素首轮段数
    Nst = np.where(hit_px, cnt_st_g[jj, ii], 0).astype(np.int16)  # 逐像素稳态段数

    # ---- 3) 像素级腐蚀：支撑半径 ----------------------------------------
    rad = support_radius(Nst)
    rad[Nst < min_multi] = 0

    # ---- 视差统计（v9 就是漏了这一项）--------------------------------------
    a = P[hit_px & (Nst >= min_multi)] - cam[None, :]
    b = P[hit_px & (Nst >= min_multi)] - org[None, :]
    if len(a):
        cosang = np.einsum("ij,ij->i", a, b) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
        par = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
        parallax = dict(max=round(float(par.max()), 2), median=round(float(np.median(par)), 2),
                        p90=round(float(np.percentile(par, 90)), 2), n=int(len(par)))
    else:
        parallax = dict(max=0, median=0, p90=0, n=0)

    # ---- 4) 峰值枚举 + 像素 NMS -----------------------------------------
    names_of = [o["name"] for o in objs]
    key = (Nst.astype(np.int32) * 10000 + N.astype(np.int32) * 100
           + np.minimum(rad, 99).astype(np.int32))
    order = np.argsort(-key.ravel())
    taken = np.zeros(Nst.shape, bool)
    pool = []
    for idx in order:
        j, i = np.unravel_index(int(idx), Nst.shape)
        if Nst[j, i] < min_multi:
            break                                  # 排序降序，后面全不达标
        if taken[j, i]:
            continue
        if not (MARGIN <= i < W - MARGIN and MARGIN <= j < H - MARGIN):
            continue                               # 靶心要能完整落在画面里
        px = [float(i) + 0.5, float(j) + 0.5]
        Pc = P[j, i]
        dv = Pc - org
        yaw = float(np.degrees(np.arctan2(dv[0], dv[2])))
        pit = float(np.degrees(np.arctan2(dv[1], np.hypot(dv[0], dv[2]))))
        pool.append(dict(yaw=yaw, pitch=pit, px=px, rad=int(rad[j, i]),
                         P=Pc.copy(), n_grid=int(N[j, i]), nst_grid=int(Nst[j, i])))
        taken[max(0, j - SUPPRESS):j + SUPPRESS + 1,
              max(0, i - SUPPRESS):i + SUPPRESS + 1] = True
        if len(pool) >= POOL_MAX:
            break

    # ---- 5) 精确复核（含遮挡）-------------------------------------------
    cand = []
    for c in pool:
        hits = sb.exact_hits(org, c["yaw"], c["pitch"], tri, oi, None)
        nblk = 0
        if occ:
            bd = blocker_dist(org, c["yaw"], c["pitch"], tri_b)
            if math.isfinite(bd):
                kept = [(o, d) for o, d in hits if d < bd]
                nblk = len(hits) - len(kept)
                hits = kept
        if len(hits) < min_multi:
            continue
        mix = {"soft": 0, "medium": 0, "hard": 0}
        for o, _ in hits:
            mix[objs[o]["grp"]] += 1
        n_st = mix["medium"] + mix["hard"]
        if n_st < min_multi:
            continue
        cand.append(dict(c, n=len(hits), n_steady=n_st, mix=mix,
                         first=round(float(hits[0][1]), 1), blocked=nblk,
                         _set=set(names_of[o] for o, _ in hits)))
    cand.sort(key=lambda c: (-c["n_steady"], -c["n"], -c["rad"]))

    def clash(c, p):
        gap = math.hypot(c["px"][0] - p["px"][0], c["px"][1] - p["px"][1])
        if gap >= GAP_OK:
            return False
        if gap < GAP_MIN:
            return True
        return abs(c["first"] - p["first"]) < DEPTH_DIFF

    pts = []
    for c in cand:
        if any(clash(c, p) for p in pts):
            continue
        if any(len(c["_set"] & p["_set"]) / max(1, len(c["_set"] | p["_set"])) >= JACCARD for p in pts):
            continue
        pts.append(c)
        if len(pts) >= n_max:
            break

    # ---- 6) 五阵位 / 标签 -------------------------------------------------
    # v12 修正：原版这里只做 exact_hits，**漏了遮挡截断** —— 于是相邻阵位的
    # 掩体（forklift/wood01 那类 cover_object）明明挡在 0.5~4m 处，
    # 却被算成「全阵位可用」。玩家换位置就打不出去，这就是「点位不准」的头号原因。
    # 现在从每个阵位出发都过一遍 blocker_dist，并把挡路物记下来。
    def aim_at(Pw):
        per, per_st, names, mix, blk = {}, {}, set(), {"soft": 0, "medium": 0, "hard": 0}, {}
        for k in sorted(orgs):
            w = Pw - orgs[k]
            y2 = math.degrees(math.atan2(w[0], w[2]))
            p2 = math.degrees(math.atan2(w[1], math.hypot(w[0], w[2])))
            hk = sb.exact_hits(orgs[k], y2, p2, tri, oi, None)
            bd = blocker_dist(orgs[k], y2, p2, tri_b) if occ else math.inf
            if math.isfinite(bd):
                kept = [(o, d) for o, d in hk if d < bd]
                if len(kept) < len(hk):
                    blk[k] = round(bd, 2)
                hk = kept
            per[k] = len(hk)
            per_st[k] = sum(1 for o, _ in hk if objs[o]["grp"] in ("medium", "hard"))
            if k == view:
                names = set(names_of[o] for o, _ in hk)
                for o, _ in hk:
                    mix[objs[o]["grp"]] += 1
        return sum(per.values()), per, per_st, blk

    for n, p in enumerate(pts, 1):
        Pw = p.pop("P")
        p.pop("_set")
        tot, per, per_st, blk = aim_at(Pw)
        hk = sb.exact_hits(org, p["yaw"], p["pitch"], tri, oi, None)
        nom_st = p["n_steady"]
        p.update(total=tot, per_slot=per, per_slot_steady=per_st, slot_blocked=blk,
                 slot_ok=sum(1 for v in per_st.values() if v >= nom_st),
                 slot_ok2=sum(1 for v in per_st.values() if v >= 2),
                 pct=round(p["n"] * sb.PER_SHOT_PCT, 2),
                 steady_pct=round(p["n_steady"] * sb.PER_SHOT_PCT, 2),
                 shots=int(math.ceil(sb.W_BAR / (p["n"] * sb.CHARGE))) if p["n"] else None,
                 steady_shots=(int(math.ceil(sb.W_BAR / (p["n_steady"] * sb.CHARGE)))
                               if p["n_steady"] else None),
                 squad_pct=round(tot * sb.PER_SHOT_PCT, 2),
                 squad_shots=int(math.ceil(sb.W_BAR / (tot * sb.CHARGE))) if tot else None,
                 last=round(hk[-1][1], 1) if hk else None)
        p["detail"] = [dict(name=objs[o]["name"], grp=objs[o]["grp"], hp=objs[o]["hp"],
                            d=round(dd, 1), center=objs[o]["center"]) for o, dd in hk]
        tags = []
        if p["mix"]["soft"] == 0 and any(o["grp"] == "soft" for o in objs):
            tags.append("不掉段")
        if p["n_steady"] >= 3:
            tags.append("高稳态")
        if p["rad"] >= 8:
            tags.append("抗手抖")
        elif p["rad"] <= 2:
            tags.append("窄窗")
        if p["first"] <= 18:
            tags.append("近景")
        elif p["first"] >= 40:
            tags.append("远景")
        if per_st and min(per_st.values()) >= nom_st:
            tags.append("全阵位")
        elif per_st:
            tags.append("%d/5阵位" % sum(1 for v in per_st.values() if v >= 2))
        if p["blocked"]:
            tags.append("挡%d段" % p["blocked"])
        p["tags"] = tags
        p["no"] = n
        p["pos"] = [round(float(x), 3) for x in Pw]
        p["origin"] = [round(float(x), 3) for x in org]
        p["aim"] = [round(float(Pw[m] - org[m]), 3) for m in range(3)]

    # 二次排序：段数 → 首轮 → 支撑半径 → 最弱阵位稳态（换掩体也能用）
    pts.sort(key=lambda p: (-p["n_steady"], -p["n"], -p["rad"],
                            -min(p["per_slot_steady"].values() if p["per_slot_steady"] else [0])))
    for n, p in enumerate(pts, 1):
        p["no"] = n

    # ---- 7) 我方掩体对照统计 ---------------------------------------------
    cover_stat = dict(n=len(cover_names),
                      names=[re.sub(r"^sbg_[a-z]+_", "", c) for c in cover_names][:8])
    cv = []
    for pr in props:
        if pr.get("g") == "cover_object":
            cv += pr.get("v") or []
    if cv:
        A = np.array(cv) - org[None, :]
        pit = np.degrees(np.arctan2(A[:, 1], np.hypot(A[:, 0], A[:, 2])))
        cover_stat["pitch_max"] = round(float(pit.max()), 1)
        cover_stat["dist_min"] = round(float(np.linalg.norm(A, axis=1).min()), 1)
    cover_stat["cover_px"] = int(behind_cover.sum())
    cover_stat["aim_px"] = int(hit_px.sum())

    return dict(arena=arena, view=view, ver="v10", step=step,
                n_pts=n_show, n_pts_max=len(pts), min_multi=min_multi, occ=bool(occ),
                region=(re.search(r"sbg_([a-z]+)_\d+", asm.get("arena", "")) or [None, ""])[1],
                scan=dict(yaw=list(yaw_rng), pitch=list(pitch_rng),
                          px_per_deg=[round(PX_Y, 2), round(PX_P, 2)]),
                nms=dict(gap_min=GAP_MIN, gap_ok=GAP_OK, depth_diff=DEPTH_DIFF,
                         jaccard=JACCARD, kinds="screen-px"),
                support_levels=LEVELS,
                cam=[round(float(x), 3) for x in cam],
                char=[round(float(x), 3) for x in expand(slots[view], "character_position")],
                fov=FOV, w=W, h=H,
                per_shot_pct=sb.PER_SHOT_PCT, energy_per_seg=sb.CHARGE, bar=sb.W_BAR,
                n_hitbox_obj=len(objs), n_tri=len(tri), n_block_tri=len(tri_b),
                excluded=["cover_object", "static_object", "noncol_object"],
                cover_stat=cover_stat, parallax=parallax,
                slots={k: dict(char=[round(float(x), 3) for x in orgs[k]],
                               cam=[round(float(x), 3) for x in expand(slots[k], "camera_position")])
                       for k in orgs},
                points=pts)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    min_multi, n_show, step, occ = MIN_MULTI, N_SHOW, STEP, True
    yaw = pitch = None
    for a in sys.argv[1:]:
        if a.startswith("--min-multi="):
            min_multi = int(a.split("=")[1])
        if a.startswith("--n="):
            n_show = int(a.split("=")[1])
        if a.startswith("--step="):
            step = float(a.split("=")[1])
        if a.startswith("--no-occ"):
            occ = False
        if a.startswith("--yaw="):
            yaw = tuple(float(x) for x in a.split("=")[1].split(","))
        if a.startswith("--pitch="):
            pitch = tuple(float(x) for x in a.split("=")[1].split(","))
    arg = args[0] if args else "all"
    mw = arg.startswith("mw")
    if arg == "all":
        arenas = ["001", "002", "003", "004", "005"]
    elif arg == "mw":
        arenas = ["mw001", "mw002", "mw003"]
    else:
        arenas = [arg]
    if arg != 'all' and arg != 'mw':
        yaw = yaw or None
        pitch = pitch or None

    for a in arenas:
        d = scan(a, min_multi=min_multi, n_show=n_show, occ=occ, step=step,
                 yaw_rng=yaw, pitch_rng=pitch)
        json.dump(d, open(os.path.join("导出", "px_%s.json" % a), "w", encoding="utf-8"),
                  ensure_ascii=False)
        cs = d["cover_stat"]
        px_ = d["parallax"]
        print("== %s  受击体 %d  遮挡三角 %d  掩体 %d 件(占 %d px)  达标点 %d  视差 max%.1f°/中位%.1f°"
              "  扫描 yaw %s" % (
                  a, d["n_hitbox_obj"], d["n_block_tri"], cs.get("n", 0), cs.get("cover_px", 0),
                  d["n_pts_max"], px_["max"], px_["median"],
                  "%+.1f~%+.1f" % tuple(d["scan"]["yaw"])))
        for p in d["points"][:n_show if n_show else 99]:
            per = "/".join(str(p["per_slot"].get("cover_%d" % i, "-")) for i in range(1, 6))
            print("  %2d) px(%4.0f,%4.0f) yaw%+6.2f p%+6.2f 稳态%d(%4.1f%%) 首轮%d ±%2dpx "
                  "软%d中%d硬%d %5.1fm 阵位%s %s" % (
                      p["no"], p["px"][0], p["px"][1], p["yaw"], p["pitch"], p["n_steady"],
                      p["steady_pct"], p["n"], p["rad"], p["mix"]["soft"], p["mix"]["medium"],
                      p["mix"]["hard"], p["first"], per, "/".join(p["tags"])))
        print("   -> 导出/px_%s.json" % a)


if __name__ == "__main__":
    main()
