# -*- coding: utf-8 -*-
"""把 NIKKE 战场场景 bundle (sbg_*) 解析成可计算的 2D 地图 JSON。

产出：每个 GameObject 的
  - 名称 / 组件分类（NKSpotStaticObject / NKSpotDynamicObject / NKSpotNonColObject / NKSpotCover）
  - 所属根分组（static_object / dynamic_object / noncol_object / cover_object ...）
  - 世界坐标 AABB（由 Mesh 的 m_LocalAABB 经父链 TRS 变换得到）
另外导出场景锚点：character_position / aim_position / camera_position / NotCombatZone
"""
import UnityPy, json, os, sys, math, collections

ROOTS = {
    "static_object", "dynamic_object", "noncol_object", "cover_object",
    "hard", "medium", "soft", "NotCombatZone",
}
ANCHOR_KEYS = ("character_position", "aim_position", "camera_position",
               "hide_position", "cover_1", "cover_2", "NotCombatZone")


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def trs(pos, rot, scl):
    x, y, z, w = rot
    xx, yy, zz = x * x, y * y, z * z
    m = [[1 - 2 * (yy + zz), 2 * (x * y - z * w), 2 * (x * z + y * w), pos[0]],
         [2 * (x * y + z * w), 1 - 2 * (xx + zz), 2 * (y * z - x * w), pos[1]],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (xx + yy), pos[2]],
         [0, 0, 0, 1]]
    for j in range(3):
        for i in range(3):
            m[i][j] *= (scl[i] if i < 3 else 1) if False else scl[j]
    return m


def apply(m, p):
    x, y, z = p
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def vec(d, w=0.0):
    return (d.get("x", 0.0), d.get("y", 0.0), d.get("z", 0.0), d.get("w", w))


def parse(path):
    env = UnityPy.load(path)
    objs = list(env.objects)
    kind = {o.path_id: o.type.name for o in objs}

    # ---------- 第一遍：Transform / Mesh / Collider / MonoBehaviour ----------
    trs_map = {}
    mesh_aabb = {}
    coll_map = {}        # go_pathid -> ("mesh"/"box", extents info)
    mb_types = {}        # go_pathid -> set(script names)
    go_comp = {}
    go_name = {}
    mb_raw = {}

    for o in objs:
        t = o.type.name
        if t in ("Transform", "RectTransform"):
            tt = o.read_typetree()
            trs_map[o.path_id] = {
                "pos": vec(tt.get("m_LocalPosition", {}) )[:3],
                "rot": vec(tt.get("m_LocalRotation", {}), 1.0),
                "scl": vec(tt.get("m_LocalScale", {}), 1.0)[:3],
                "father": tt.get("m_Father", {}).get("m_PathID", 0),
                "go": tt.get("m_GameObject", {}).get("m_PathID", 0),
            }
        elif t == "Mesh":
            tt = o.read_typetree()
            a = tt.get("m_LocalAABB", {})
            c = a.get("m_Center", {})
            e = a.get("m_Extent", {})
            mesh_aabb[o.path_id] = (
                (c.get("x", 0), c.get("y", 0), c.get("z", 0)),
                (e.get("x", 0), e.get("y", 0), e.get("z", 0)),
            )
        elif t == "MeshCollider":
            tt = o.read_typetree()
            coll_map[tt["m_GameObject"]["m_PathID"]] = ("mesh", tt.get("m_Mesh", {}).get("m_PathID", 0))
        elif t == "BoxCollider":
            tt = o.read_typetree()
            c = tt.get("m_Center", {})
            s = tt.get("m_Size", {})
            coll_map[tt["m_GameObject"]["m_PathID"]] = ("box", (
                (c.get("x", 0), c.get("y", 0), c.get("z", 0)),
                (s.get("x", 0) / 2, s.get("y", 0) / 2, s.get("z", 0) / 2),
            ))
        elif t == "MonoBehaviour":
            tt = o.read_typetree()
            mb_raw[o.path_id] = tt

    # 脚本名
    script_name = {}
    for o in objs:
        if o.type.name == "MonoScript":
            d = o.read()
            script_name[o.path_id] = getattr(d, "m_ClassName", None) or getattr(d, "m_Name", "?")

    go_transform = {}
    for o in objs:
        if o.type.name != "GameObject":
            continue
        tt = o.read_typetree()
        go_name[o.path_id] = tt.get("m_Name", "")
        comps = [c["component"]["m_PathID"] for c in tt.get("m_Component", [])]
        go_comp[o.path_id] = comps
        for cid in comps:
            if cid in trs_map:
                go_transform[o.path_id] = cid

    grade = {}
    for pid, tt in mb_raw.items():
        go = tt.get("m_GameObject", {}).get("m_PathID", 0)
        s = tt.get("m_Script", {}).get("m_PathID", 0)
        nm = script_name.get(s, "?")
        mb_types.setdefault(go, set()).add(nm)
        if "CollisionGradeType" in tt:
            grade[go] = tt["CollisionGradeType"]

    # ---------- 世界矩阵 ----------
    world_cache = {}

    def world_of(tr_id, depth=0):
        if tr_id in world_cache:
            return world_cache[tr_id]
        t = trs_map.get(tr_id)
        if t is None or depth > 64:
            return [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        local = trs(t["pos"], t["rot"], t["scl"])
        f = t["father"]
        m = mat_mul(world_of(f, depth + 1), local) if f else local
        world_cache[tr_id] = m
        return m

    # 根分组名
    def root_group(go_id, depth=0):
        tr = trs_map.get(go_transform.get(go_id, 0))
        cur_go = go_id
        guard = 0
        while tr and tr["father"] and guard < 64:
            father_tr = trs_map.get(tr["father"])
            if not father_tr:
                break
            cur_go = father_tr["go"]
            nm = go_name.get(cur_go, "")
            if nm in ROOTS:
                return nm
            tr = father_tr
            guard += 1
        return go_name.get(cur_go, "")

    props = []
    anchors = collections.defaultdict(list)

    for go_id, comps in go_comp.items():
        name = go_name.get(go_id, "")
        tr = trs_map.get(go_transform.get(go_id, 0))
        if tr is None:
            continue
        m = world_of(go_transform[go_id])
        px, py, pz = apply(m, (0, 0, 0))
        base = name.split(" (")[0]

        if base in ANCHOR_KEYS or name in ANCHOR_KEYS:
            anchors[base].append([round(px, 3), round(py, 3), round(pz, 3)])
            continue

        comp_types = sorted(mb_types.get(go_id, []))
        col = coll_map.get(go_id)

        aabb = None
        ctype = None
        if col:
            ctype = col[0]
            if col[0] == "mesh":
                box = mesh_aabb.get(col[1])
            else:
                box = col[1]
            if box:
                (cx, cy, cz), (ex, ey, ez) = box
                pts = [(cx + sx * ex, cy + sy * ey, cz + sz * ez)
                       for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
                w = [apply(m, p) for p in pts]
                aabb = [
                    round(min(p[0] for p in w), 3), round(min(p[1] for p in w), 3), round(min(p[2] for p in w), 3),
                    round(max(p[0] for p in w), 3), round(max(p[1] for p in w), 3), round(max(p[2] for p in w), 3),
                ]

        if not comp_types and not col:
            # 纯空节点/组节点，跳过
            continue

        props.append({
            "n": name,
            "g": root_group(go_id),
            "t": comp_types,
            "c": ctype,
            "q": grade.get(go_id, -1),
            "p": [round(px, 3), round(py, 3), round(pz, 3)],
            "b": aabb,
        })

    out = {
        "arena": os.path.splitext(os.path.basename(path))[0],
        "anchors": {k: v for k, v in anchors.items()},
        "props": props,
    }
    return out


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2]
    data = parse(src)
    json.dump(data, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print("arena:", data["arena"])
    print("props:", len(data["props"]))
    c = collections.Counter(tuple(p["t"]) for p in data["props"])
    for k, v in c.most_common(10):
        print("  ", "+".join(k) or "(none)", v)
    g = collections.Counter(p["g"] for p in data["props"])
    print("根分组:", dict(g))
    print("锚点:", {k: len(v) for k, v in data["anchors"].items()})
    print("带碰撞:", sum(1 for p in data["props"] if p["c"]), "/ 有包围盒:", sum(1 for p in data["props"] if p["b"]))
