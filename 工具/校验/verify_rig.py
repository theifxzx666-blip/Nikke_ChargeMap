# -*- coding: utf-8 -*-
"""机位校验：用「完整矩阵累乘」独立重算，比对 slots.json 里的 camera_aim / camera_hide。

为什么单独写这个：
  build_slot_rigs.py 用一条简化公式算机位，公式本身错了没人能发现 ——
  2026-11-14 就是这么漏掉 CameraN 偏航对 Aim/HideCamera local 偏移的旋转，差了 3.5 cm，
  5 m 距离上只有 0.4°，肉眼和出图都看不出来。
  本脚本走第二条实现：UnityPy 沿 m_Father 链做 4×4 矩阵累乘（四元数旋转 × 父级缩放 → 平移），
  与落库值逐位比对。两套实现结果一致，才说明公式没错。

原理：
  模板里 AimCamera 的世界位置是相对 Cover_N 的定值（5 阵位各一套），
  其它场景只是把同一套模板摆到自己的 root / root_scale / root_yaw 上，所以：
      scene_pos = root + R_y(root_yaw) · [ (template_pos − template_cover_local) × scale ]

用法：
  python verify_rig.py                 # 抽查 tw003 + ocebg001001（含缩放场景）
  python verify_rig.py --all           # 全库 112 场景 × 5 阵位
  python verify_rig.py 001 c003        # 指定场景
  python verify_rig.py --tol=0.002     # 自定义容差（米），默认 0.002
"""
import glob
import json
import os
import sys

try:
    import numpy as np
    import UnityPy
except ModuleNotFoundError as _e:                              # noqa: N816
    raise SystemExit("缺依赖 %s —— 本脚本要用拆包环境跑：\n"
                     "  D:/Codex/依赖/venv-nikke/Scripts/python.exe 工具/校验/verify_rig.py"
                     % (_e.name,))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))

RIG_BUNDLE = os.path.join(ROOT, "临时车间", "重解包_20261114", "probe", "spotcharactermap.bundle")
# 抽查场景：一个普通场景 + 一个带 1.3575 / 1.053 缩放的场景（验证 scale 分支）
SPOT = ["tw003", "ocebg001001"]


def load_bundle(path):
    env = UnityPy.load(path)
    T, typ = {}, {}
    for o in env.objects:
        typ[o.path_id] = o.type.name
        try:
            T[o.path_id] = o.read_typetree()
        except Exception:
            T[o.path_id] = None
    go = {p: t.get("m_Name", "") for p, t in T.items() if t and typ[p] == "GameObject"}
    tr = {t: (v.get("m_GameObject") or {}).get("m_PathID")
          for t, v in T.items() if v and typ[t] == "Transform"}
    name_of = {t: go.get(tr.get(t), "?") for t in tr}
    return T, name_of


def qmat(q):
    x, y, z, w = q["x"], q["y"], q["z"], q["w"]
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def local_mat(t):
    p = t.get("m_LocalPosition") or {}
    r = t.get("m_LocalRotation") or {"x": 0, "y": 0, "z": 0, "w": 1}
    s = t.get("m_LocalScale") or {"x": 1, "y": 1, "z": 1}
    M = np.eye(4)
    M[:3, :3] = qmat(r) @ np.diag([s["x"], s["y"], s["z"]])
    M[:3, 3] = [p.get("x", 0), p.get("y", 0), p.get("z", 0)]
    return M


def world(T, name_of, tid):
    """沿 m_Father 一路累乘到根，返回 (4×4 世界矩阵, 链上名字)"""
    M, cur, chain = np.eye(4), tid, []
    for _ in range(30):
        if not cur:
            break
        t = T.get(cur) or {}
        chain.append(name_of.get(cur, "?"))
        M = local_mat(t) @ M
        cur = (t.get("m_Father") or {}).get("m_PathID")
    return M, list(reversed(chain))


def template_offsets():
    """从模板 bundle 里取 5 阵位的 Aim/HideCamera 世界位置，减去 Cover_N 的 local 位置，
    得到「相对 cover 根的偏移」。这一步用完整矩阵，不看 build_slot_rigs 的公式。"""
    if not os.path.exists(RIG_BUNDLE):
        raise SystemExit("找不到机位模板包：%s" % RIG_BUNDLE)
    T, name_of = load_bundle(RIG_BUNDLE)

    cover_local = {}
    for tid, nm in name_of.items():
        if nm.startswith("Cover_") and nm[6:].isdigit():
            p = (T[tid] or {}).get("m_LocalPosition") or {}
            cover_local["cover_" + nm[6:]] = np.array([p.get("x", 0), p.get("y", 0), p.get("z", 0)])

    by_name = {}
    for tid, nm in name_of.items():
        by_name.setdefault(nm, []).append(tid)

    out = {}
    for i in range(1, 6):
        key = "cover_%d" % i
        for tag, node in (("aim", "AimCamera"), ("hide", "HideCamera")):
            hit = None
            for tid in by_name.get(node, []):
                M, ch = world(T, name_of, tid)
                if ("Cover_%d" % i) in " ".join(ch):
                    hit = M
                    break
            if hit is None:
                raise SystemExit("模板里找不到 %s 的 %s" % (key, node))
            out[(key, tag)] = hit[:3, 3] - cover_local[key]
    return out


def rot_y(v, deg):
    """Unity 左手系绕 +Y 旋转。root_yaw 全库为 0，但公式要能处理非零。"""
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c])


def check(arena, hdr, tol):
    p = glob.glob(os.path.join(ROOT, "资源库", "场景库", "*", "%s_*" % arena, "mesh", "slots.json"))
    if not p:
        return None, "无 slots.json"
    block = (json.load(open(p[0], encoding="utf-8")) or {}).get(arena) or {}
    mx = 0.0
    for i in range(1, 6):
        key = "cover_%d" % i
        e = block.get(key)
        if not e:
            continue
        root = np.array(e.get("root") or [0, 0, 0], float)
        scale = (e.get("root_scale") or [1, 1, 1])[0]
        yaw0 = float(e.get("root_yaw") or 0.0)
        for tag, field in (("aim", "camera_aim"), ("hide", "camera_hide")):
            off = hdr[(key, tag)]
            pos = root + rot_y(off * scale, yaw0)
            ref = (e.get(field) or {}).get("pos")
            if not ref:
                return None, "%s 缺 %s" % (key, field)
            d = float(np.max(np.abs(pos - np.array(ref, float))))
            mx = max(mx, d)
    return mx, None


def main(argv):
    tol = 0.002
    only = []
    all_scenes = False
    for a in argv:
        if a.startswith("--tol="):
            tol = float(a.split("=")[1])
        elif a == "--all":
            all_scenes = True
        elif not a.startswith("-"):
            only.append(a)

    hdr = template_offsets()
    if all_scenes:
        reg = json.load(open(os.path.join(ROOT, "资源库", "场景库", "registry.json"), encoding="utf-8"))["scenes"]
        targets = sorted(reg)
    else:
        targets = only or SPOT

    worst = []
    bad = 0
    for a in targets:
        mx, err = check(a, hdr, tol)
        if err:
            print("  %-16s !! %s" % (a, err))
            bad += 1
            continue
        flag = "OK" if mx <= tol else "!! 超差"
        if mx > tol:
            bad += 1
        worst.append((mx, a))
        print("  %-16s 最大偏差 %.4f m  %s" % (a, mx, flag))

    worst.sort(reverse=True)
    print("\n场景 %d｜超差 %d｜容差 %.3f m｜最大偏差 %.4f m（%s）"
          % (len(targets), bad, tol, worst[0][0] if worst else 0.0,
             worst[0][1] if worst else "-"))
    print("比对对象：slots.json 的 camera_aim / camera_hide ↔ 模板 bundle 的完整矩阵重算值")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
