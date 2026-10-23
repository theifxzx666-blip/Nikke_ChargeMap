# -*- coding: utf-8 -*-
"""导出 5 个阵位（cover_1..cover_5）的完整世界变换 + 相机世界位姿。

实证结构（sbg_swamplandjungle_00N）：
  cover_1..cover_5                     5 个阵位根（各自位置 + 各自 yaw）
    ├─ character_position   local (-0.60, -2.34, -0.40)
    ├─ cover_object
    ├─ hide_position        local ( 0.00,  0.236, -0.577) 等
    └─ camera_position      local ( 0.60,  0.00, -4.90)
         └─ aim_position    local (-0.10,  0.00, -0.10)   <- 相机看向的点

所以「每个站位视野不同」= cover 根的 yaw 不同，相机随根旋转。
"""
import UnityPy, json, os, sys, math

ANCH = {"character_position", "camera_position", "aim_position",
        "hide_position", "cover_object"}


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qrot(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    # v' = v + 2*cross(q.xyz, cross(q.xyz, v) + w*v)
    cx = y * vz - z * vy + w * vx
    cy = z * vx - x * vz + w * vy
    cz = x * vy - y * vx + w * vz
    return (vx + 2 * (y * cz - z * cy),
            vy + 2 * (z * cx - x * cz),
            vz + 2 * (x * cy - y * cx))


def yaw_of(q):
    x, y, z, w = q
    return math.degrees(math.atan2(2 * (w * y + x * z), 1 - 2 * (y * y + x * x)))


def build(path):
    env = UnityPy.load(path)
    go, tr = {}, {}
    for o in env.objects:
        if o.type.name == "GameObject":
            tt = o.read_typetree()
            go[o.path_id] = tt.get("m_Name", "")
        elif o.type.name == "Transform":
            tr[o.path_id] = o.read_typetree()
    t2g = {}
    for tid, tt in tr.items():
        g = tt.get("m_GameObject", {}).get("m_PathID", 0)
        if g:
            t2g[tid] = g
    g2t = {}
    for tid, g in t2g.items():
        g2t.setdefault(g, tid)

    cache = {}

    def world(tid, depth=0):
        if tid in cache:
            return cache[tid]
        tt = tr[tid]
        p = tt.get("m_LocalPosition") or {}
        r = tt.get("m_LocalRotation") or {}
        s = tt.get("m_LocalScale") or {}
        lp = (p.get("x", 0), p.get("y", 0), p.get("z", 0))
        lq = (r.get("x", 0), r.get("y", 0), r.get("z", 0), r.get("w", 1))
        ls = (s.get("x", 1), s.get("y", 1), s.get("z", 1))
        f = tt.get("m_Father", {}).get("m_PathID", 0)
        if f and depth < 32:
            fp, fq, fs = world(f, depth + 1)
            sp = (lp[0] * fs[0], lp[1] * fs[1], lp[2] * fs[2])
            rp = qrot(fq, sp)
            pos = (fp[0] + rp[0], fp[1] + rp[1], fp[2] + rp[2])
            q = qmul(fq, lq)
            sc = (fs[0] * ls[0], fs[1] * ls[1], fs[2] * ls[2])
        else:
            pos, q, sc = lp, lq, ls
        cache[tid] = (pos, q, sc)
        return cache[tid]

    slots = {}
    for gid, nm in go.items():
        if nm not in ("cover_1", "cover_2", "cover_3", "cover_4", "cover_5"):
            continue
        tid = g2t.get(gid)
        if tid is None:
            continue
        cp, cq, cs = world(tid)
        key = nm
        entry = dict(
            slot=key,
            root=[round(v, 3) for v in cp],
            root_yaw=round(yaw_of(cq), 2),
            root_quat=[round(v, 5) for v in cq],
            root_scale=[round(v, 4) for v in cs],
        )
        # 子锚点：递归找
        stack = [(tid, 0)]
        seen = set()
        while stack:
            cur, d = stack.pop()
            if cur in seen or d > 8:
                continue
            seen.add(cur)
            tt = tr[cur]
            for ch in (tt.get("m_Children") or []):
                ct = ch.get("m_PathID", 0)
                if not ct or ct not in tr:
                    continue
                cg = t2g.get(ct)
                cnm = go.get(cg, "")
                if cnm in ANCH:
                    p, q, s = world(ct)
                    if cnm == "aim_position":
                        p2, q2, s2 = world(tr[ct].get("m_Father", {}).get("m_PathID", 0))
                        entry["aim"] = [round(v, 3) for v in p]
                        entry["cam"] = [round(v, 3) for v in p2]
                        dx = p[0] - p2[0]
                        dz = p[2] - p2[2]
                        entry["cam_yaw"] = round(math.degrees(math.atan2(dx, dz)), 2)
                    else:
                        entry.setdefault(cnm, []).append([round(v, 3) for v in p])
                stack.append((ct, d + 1))
        slots[key] = entry
    return slots


def main():
    out = {}
    for n in ("001", "002", "003", "004", "005"):
        p = os.path.join("原始bundle", "sbg", "sbg_swamplandjungle_%s.bundle" % n)
        if not os.path.exists(p):
            continue
        s = build(p)
        out[n] = s
        print("==", n)
        for k in sorted(s):
            e = s[k]
            print("  %-8s root=(%7.2f,%6.2f,%7.2f) yaw=%7.2f  cam=(%7.2f,%6.2f,%7.2f) camYaw=%7.2f" % (
                k, e["root"][0], e["root"][1], e["root"][2], e["root_yaw"],
                e.get("cam", [0, 0, 0])[0], e.get("cam", [0, 0, 0])[1],
                e.get("cam", [0, 0, 0])[2], e.get("cam_yaw", 0)))
    json.dump(out, open(os.path.join("导出", "slots.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("-> 导出/slots.json")


if __name__ == "__main__":
    main()
