# -*- coding: utf-8 -*-
"""充能点分析内核（纯函数，无 IO）—— 从历史脚本 scan_best.py 抽出。

保留顶层名与签名完全不变（调用方写成 `import charge_core as sb`），
所以 scan_px / verify_px / audit_px 的数学部分一行都不用改。

对外：W_BAR / PER_SHOT_PCT / CHARGE / GUN_H / HITBOX / COVER / MAX_SPAN / MIN_DIST
      load_tris(props) · build_mask(...) · ray_dirs(yaw,pitch) · exact_hits(...)
      min_filter(cnt,k) · regions(cnt,value)

不含：save_heatmap（画图）、scan（读 导出/ 的旧口径）、main（旧 CLI）。
"""

import json, math, os, sys
from collections import deque

import numpy as np

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
