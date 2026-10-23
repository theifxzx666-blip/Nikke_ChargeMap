# -*- coding: utf-8 -*-
"""截图点位反查：给一张 fp.html 出的图 + 图上的像素坐标，算出这个位置到底是什么点。

用法：
    python probe_pixel.py mw003 288 369                 # 单点
    python probe_pixel.py mw003 266,350 313,389         # 多点
    python probe_pixel.py mw003 288 369 --box=262,347,315,391   # 框内 5px 网格扫描

为什么要从像素反查：
    图是相机（cover_N.camera_position，FOV 60）渲的，但射线判定从枪口
    （character_position + 1.45m）出发，两者差 1.2m 横 / 0.89m 高 / 4.5m 纵深。
    所以「截图上的一个位置」→ 相机射线命中点 P → 再从枪口瞄准 P，才是玩家的真实角度。

输出：
    相机距 / 首击物体 / 枪口角度 / 单发段数 / 耐久构成 / 五阵位各自段数
"""
import json, math, os, sys
import numpy as np

import scan_best as sb

W, H, FOV = 1600, 900, 60.0
BASE = os.path.dirname(os.path.abspath(__file__))


def load(arena):
    asm = json.load(open(os.path.join(BASE, "导出", "assembly_%s.json" % arena), encoding="utf-8"))
    objs, tri, oi, _ = sb.load_tris(asm["props"])
    slots = json.load(open(os.path.join(BASE, "导出", "slots.json"), encoding="utf-8"))[arena]
    fp = json.load(open(os.path.join(BASE, "导出", "fp_%s.json" % arena), encoding="utf-8"))
    orgs = {}
    for k in sorted(slots):
        c = slots[k]["character_position"]
        if isinstance(c[0], list):
            c = c[0]
        orgs[k] = np.array([c[0], c[1] + sb.GUN_H, c[2]], float)
    return objs, tri, oi, orgs, np.array(fp["cam"], float)


def pix2dir(px, py):
    """屏幕像素 → 世界方向（three 相机朝 three 的 −z，世界 z 取反）。"""
    th = math.tan(math.radians(FOV / 2))
    asp = W / H
    xn = 2 * (px + 0.5) / W - 1
    yn = 1 - 2 * (py + 0.5) / H
    d = np.array([xn * th * asp, yn * th, -1.0])
    d /= np.linalg.norm(d)
    return np.array([d[0], d[1], -d[2]])


def nearest(origin, d, tri, oi, maxd=400.0):
    """任意方向的 Möller–Trumbore，返回最近交点距离与物体序号。"""
    v0 = tri[:, 0, :]
    e1 = tri[:, 1, :] - v0
    e2 = tri[:, 2, :] - v0
    D = np.broadcast_to(d, (len(tri), 3))
    pv = np.cross(D, e2)
    det = np.einsum("tj,tj->t", e1, pv)
    m = np.abs(det) > 1e-9
    inv = np.where(m, 1 / np.where(m, det, 1.0), 0.0)
    tv = origin - v0
    u = np.einsum("tj,tj->t", tv, pv) * inv
    qv = np.cross(tv, e1)
    vv = np.einsum("tj,tj->t", D, qv) * inv
    t = np.einsum("tj,tj->t", e2, qv) * inv
    ok = m & (u >= -1e-5) & (vv >= -1e-5) & (u + vv <= 1 + 1e-5) & (t > 0.05) & (t < maxd)
    if not ok.any():
        return None, None
    k = np.where(ok)[0][np.argmin(t[ok])]
    return float(t[k]), int(oi[k])


def probe(objs, tri, oi, orgs, cam, px, py, verbose=True):
    d = pix2dir(px, py)
    t, o = nearest(cam, d, tri, oi)
    if o is None:
        if verbose:
            print("px(%d,%d)  该像素没有打到任何可破坏物" % (px, py))
        return None
    P = cam + d * t
    view = "cover_3" if "cover_3" in orgs else sorted(orgs)[0]
    v = P - orgs[view]
    yaw = math.degrees(math.atan2(v[0], v[2]))
    pit = math.degrees(math.atan2(v[1], math.hypot(v[0], v[2])))
    hk = sb.exact_hits(orgs[view], yaw, pit, tri, oi, None)
    mix = {"soft": 0, "medium": 0, "hard": 0}
    for oo, _ in hk:
        mix[objs[oo]["grp"]] += 1
    per = {}
    for k, o0 in orgs.items():
        dv = P - o0
        y2 = math.degrees(math.atan2(dv[0], dv[2]))
        p2 = math.degrees(math.atan2(dv[1], math.hypot(dv[0], dv[2])))
        per[k] = len(sb.exact_hits(o0, y2, p2, tri, oi, None))
    short = lambda s: s.replace("sbg_swamplandjungle_", "").replace("sbg_motherwhalefield_", "")
    if verbose:
        print("px(%4d,%4d) 相机距 %5.1fm | 首击 %-24s %5.1fm" % (px, py, t, short(objs[o]["name"]), t))
        print("            枪口角度 yaw%+7.2f  pitch%+6.2f" % (yaw, pit))
        print("            单发 %d 段 = %.1f%% 爆裂条  软%d/中%d/硬%d  五阵位 %s (合计 %d)" % (
            len(hk), len(hk) * sb.PER_SHOT_PCT, mix["soft"], mix["medium"], mix["hard"],
            "/".join(str(per[k]) for k in sorted(per)), sum(per.values())))
        print("            命中：" + " → ".join(short(objs[x]["name"]) for x, _ in hk))
    return dict(px=px, py=py, dist=t, yaw=yaw, pitch=pit, n=len(hk), mix=mix,
                per=per, total=sum(per.values()), P=P,
                names=[objs[x]["name"] for x, _ in hk])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    box = None
    for a in sys.argv[1:]:
        if a.startswith("--box="):
            box = [int(v) for v in a.split("=")[1].split(",")]
    if not args or (len(args) < 2 and not box):
        print(__doc__)
        return
    arena = args[0]
    objs, tri, oi, orgs, cam = load(arena)
    print("== %s  可破坏物 %d 件  机位 %s  （图 1600x900，FOV 60）" % (
        arena, len(objs), np.round(cam, 2)))

    if box:
        x0, y0, x1, y1 = box
        print("\n框内 (%d,%d)~(%d,%d) 5px 网格，数字 = 单发段数，. = 空" % (x0, y0, x1, y1))
        best = None
        for py in range(y0, y1 + 1, 5):
            line = ""
            for px in range(x0, x1 + 1, 5):
                r = probe(objs, tri, oi, orgs, cam, px, py, verbose=False)
                if not r:
                    line += "."
                    continue
                line += str(min(r["n"], 9))
                if best is None or r["n"] > best["n"]:
                    best = r
            print("  y=%4d  %s" % (py, line))
        if best:
            print("\n框内最佳：")
            probe(objs, tri, oi, orgs, cam, best["px"], best["py"])
        return

    for a in args[1:]:
        if "," in a:
            px, py = (int(v) for v in a.split(","))
        else:
            px, py = int(a), int(args[args.index(a) + 1])
        probe(objs, tri, oi, orgs, cam, px, py)


if __name__ == "__main__":
    main()
