# -*- coding: utf-8 -*-
"""探测战场 bundle 里的「装配参数」：Mesh 真实顶点 / Renderer 排序 / Material shader。
目的：确认能否用原生顶点+TRS 替代现在的高估 AABB。"""
import UnityPy, json, math, collections, sys

P = r"原始bundle/sbg/sbg_swamplandjungle_001.bundle"
env = UnityPy.load(P)

script_name = {}
for o in env.objects:
    if o.type.name == "MonoScript":
        d = o.read()
        script_name[o.path_id] = getattr(d, "m_ClassName", None) or "?"

trs, meshes, rends, mats, go_name = {}, {}, {}, {}, {}

for o in env.objects:
    t = o.type.name
    if t == "Transform":
        tt = o.read_typetree()
        q = tt.get("m_LocalRotation", {})
        s = tt.get("m_LocalScale", {})
        p = tt.get("m_LocalPosition", {})
        trs[o.path_id] = dict(
            p=(p.get("x", 0), p.get("y", 0), p.get("z", 0)),
            q=(q.get("x", 0), q.get("y", 0), q.get("z", 0), q.get("w", 1)),
            s=(s.get("x", 1), s.get("y", 1), s.get("z", 1)),
            father=tt.get("m_Father", {}).get("m_PathID", 0),
            go=tt.get("m_GameObject", {}).get("m_PathID", 0),
        )
    elif t == "GameObject":
        tt = o.read_typetree()
        go_name[o.path_id] = tt.get("m_Name", "")
    elif t == "Mesh":
        tt = o.read_typetree()
        vs = tt.get("m_VertexData", {})
        n = vs.get("m_VertexCount", 0)
        ch = [c.get("format") for c in vs.get("m_Channels", [])[:3]]
        raw = vs.get("m_DataSize")
        pts = []
        # 只取前 8 个顶点用于判断形状
        try:
            import struct
            if isinstance(raw, (bytes, bytearray)) and n:
                stride = 0
                # 简化：position 是 float32 x3 在 channel0 偏移 0
                for i in range(min(n, 8)):
                    off = i * (len(raw) // n)
                    x, y, z = struct.unpack_from("<3f", raw, off)
                    pts.append([round(x, 4), round(y, 4), round(z, 4)])
        except Exception as e:
            pts = [["err", str(e)]]
        a = tt.get("m_LocalAABB", {})
        meshes[o.path_id] = dict(n=n, pts=pts,
                                 aabb=[a.get("m_Center", {}), a.get("m_Extent", {})])
    elif t == "MeshRenderer":
        tt = o.read_typetree()
        rends[o.path_id] = dict(
            go=tt.get("m_GameObject", {}).get("m_PathID", 0),
            mats=[m.get("m_PathID", 0) for m in tt.get("m_Materials", [])],
            order=tt.get("m_SortingOrder"),
            layer=tt.get("m_SortingLayerID"),
            layer_name=tt.get("m_SortingLayer"),
            cast=tt.get("m_CastShadows"),
            recv=tt.get("m_ReceiveShadows"),
            en=tt.get("m_Enabled"),
        )
    elif t == "Material":
        tt = o.read_typetree()
        mats[o.path_id] = dict(name=tt.get("m_Name"), shader=tt.get("m_Shader", {}).get("m_PathID"),
                               saved=tt.get("m_SavedProperties", {}))

print("=" * 70)
print("Mesh 形状抽样")
cnt = collections.Counter()
for mid, m in list(meshes.items())[:200]:
    xs = [p[0] for p in m["pts"] if isinstance(p[0], (int, float))]
    ys = [p[1] for p in m["pts"] if isinstance(p[1], (int, float))]
    if xs:
        dx = round(max(xs) - min(xs), 3)
        dy = round(max(ys) - min(ys), 3)
        cnt[(m["n"], dx, dy)] += 1
for k, v in cnt.most_common(12):
    print("  verts=%d  dx=%s dy=%s  ×%d" % (k[0], k[1], k[2], v))

print("\n" + "=" * 70)
print("MeshRenderer 字段抽样（前 6 个）")
for rid, r in list(rends.items())[:6]:
    print(" ", go_name.get(r["go"], "?"), "| order=", r["order"], "layerID=", r["layer"],
          "layerName=", r["layer_name"], "cast=", r["cast"], "recv=", r["recv"], "en=", r["en"])

print("\nSortingOrder 分布:", collections.Counter(r["order"] for r in rends.values()).most_common(8))
print("SortingLayer 分布:", collections.Counter(str(r["layer_name"]) for r in rends.values()).most_common(8))
print("CastShadows 分布:", collections.Counter(r["cast"] for r in rends.values()).most_common())
print("Enabled 分布:", collections.Counter(r["en"] for r in rends.values()).most_common())

print("\n" + "=" * 70)
print("Material 全部")
for mid, m in mats.items():
    sp = m["saved"] or {}
    texenvs = sp.get("m_TexEnvs") or []
    col = sp.get("m_Colors") or []
    print(" -", m["name"], "| shader=", m["shader"])
    for te in texenvs[:6]:
        nm = te.get("first", {})
        if isinstance(nm, dict):
            nm = nm.get("name") or nm.get("Name")
        tx = (te.get("second") or {}).get("m_Texture", {}).get("m_PathID", 0)
        if tx:
            print("      tex", nm, "->", tx)
    for c in col[:8]:
        nm = c.get("first", {})
        if isinstance(nm, dict):
            nm = nm.get("name") or nm.get("Name")
        v = c.get("second", {})
        print("      col", nm, v)

print("\n" + "=" * 70)
print("Transform 局部旋转分布（非单位旋转占比）")
non_id = 0
eul = collections.Counter()
for tid, t in trs.items():
    x, y, z, w = t["q"]
    if abs(x) + abs(y) + abs(z) > 1e-3:
        non_id += 1
        # 绕 Y 轴角
        ang = round(math.degrees(2 * math.atan2(y, w)), 1)
        eul[ang] += 1
print("  非单位旋转:", non_id, "/", len(trs))
print("  绕Y角度分布:", eul.most_common(12))
sc = collections.Counter(tuple(round(v, 3) for v in t["s"]) for t in trs.values())
print("  scale 分布:", sc.most_common(8))
