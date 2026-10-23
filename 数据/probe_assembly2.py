# -*- coding: utf-8 -*-
"""深挖装配参数: Mesh 几何真相 / Material 属性 / MonoBehaviour 脚本清单 / 贴图绑定通道"""
import UnityPy, collections, struct, math, json

P = r"原始bundle/sbg/sbg_swamplandjungle_001.bundle"
env = UnityPy.load(P)
objs = list(env.objects)

script_name = {}
for o in objs:
    if o.type.name == "MonoScript":
        d = o.read()
        script_name[o.path_id] = getattr(d, "m_ClassName", None) or "?"

print("MonoScript 清单:", sorted(set(script_name.values())))
print()

# ---- MonoBehaviour 各脚本出现次数 ----
mb_by_script = collections.Counter()
mb_sample = {}
for o in objs:
    if o.type.name != "MonoBehaviour":
        continue
    tt = o.read_typetree()
    sn = script_name.get(tt.get("m_Script", {}).get("m_PathID", 0), "?")
    mb_by_script[sn] += 1
    if sn not in mb_sample:
        mb_sample[sn] = tt
print("MonoBehaviour 按脚本:", dict(mb_by_script))
print()

for sn, tt in mb_sample.items():
    if sn in ("RuntimeTextureInstanceSetter",):
        print("=== %s 字段 ===" % sn)
        for k, v in tt.items():
            if k in ("m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance",
                     "m_PrefabAsset", "m_GameObject", "m_Enabled", "m_EditorHideFlags", "m_Script", "m_Name"):
                continue
            print("   ", k, "=", json.dumps(v, ensure_ascii=False)[:200])
        print()

# ---- Mesh 几何：是否平面 ----
print("=" * 70)
print("Mesh 几何分析")
mesh_rows = []
for o in objs:
    if o.type.name != "Mesh":
        continue
    tt = o.read_typetree()
    vd = tt.get("m_VertexData", {})
    n = vd.get("m_VertexCount", 0)
    raw = vd.get("m_DataSize")
    chans = vd.get("m_Channels", [])
    if not n or not isinstance(raw, (bytes, bytearray)):
        continue
    # 求 stride: 从最后一个 channel 的 offset+dim 推断不可靠, 用 len/n
    stride = len(raw) // n
    pts = []
    for i in range(n):
        off = i * stride
        try:
            x, y, z = struct.unpack_from("<3f", raw, off)
            pts.append((x, y, z))
        except Exception:
            break
    if len(pts) < 3:
        continue
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; zs = [p[2] for p in pts]
    mesh_rows.append(dict(
        name=tt.get("m_Name", ""), n=n, stride=stride,
        dx=round(max(xs)-min(xs), 4), dy=round(max(ys)-min(ys), 4), dz=round(max(zs)-min(zs), 4),
        zmin=round(min(zs), 4), zmax=round(max(zs), 4),
        cx=round((max(xs)+min(xs))/2, 4), cy=round((max(ys)+min(ys))/2, 4),
        submeshes=len(tt.get("m_SubMeshes", [])),
    ))
mesh_rows.sort(key=lambda r: -r["n"])
print("  mesh 总数:", len(mesh_rows))
flat = [r for r in mesh_rows if r["dz"] < 1e-4]
print("  dz<1e-4（严格平面 z=0）:", len(flat), "/", len(mesh_rows))
print("  dz 分布:", collections.Counter(round(r["dz"], 3) for r in mesh_rows).most_common(8))
print("  dx/dy 组合 top10:")
for k, v in collections.Counter((r["dx"], r["dy"]) for r in mesh_rows).most_common(10):
    print("     w=%s h=%s  ×%d" % (k[0], k[1], v))
print("  顶点数 top8:")
for r in mesh_rows[:8]:
    print("     %-42s n=%-4d stride=%-3d dx=%-6s dy=%-6s dz=%-6s sub=%d"
          % (r["name"][:42], r["n"], r["stride"], r["dx"], r["dy"], r["dz"], r["submeshes"]))
print()

# ---- Material 属性 ----
print("=" * 70)
print("Material 属性")
def pname(x):
    if isinstance(x, dict):
        return x.get("name") or x.get("Name")
    return x
for o in objs:
    if o.type.name != "Material":
        continue
    tt = o.read_typetree()
    sp = tt.get("m_SavedProperties", {}) or {}
    print(" -", tt.get("m_Name"), "| shaderPathID=", tt.get("m_Shader", {}).get("m_PathID"))
    for key in ("m_TexEnvs", "m_Floats", "m_Colors", "m_Ints"):
        items = sp.get(key) or []
        for it in items:
            if isinstance(it, (list, tuple)) and len(it) == 2:
                k, v = it
            elif isinstance(it, dict):
                k, v = it.get("first"), it.get("second")
            else:
                continue
            k = pname(k)
            if key == "m_TexEnvs":
                tx = (v or {}).get("m_Texture", {}).get("m_PathID", 0)
                if tx:
                    print("      tex  %-24s -> %s  scale=%s off=%s" % (k, tx, (v or {}).get("m_Scale"), (v or {}).get("m_Offset")))
            elif key == "m_Colors":
                print("      col  %-24s %s" % (k, {kk: round(vv, 3) for kk, vv in (v or {}).items() if isinstance(vv, float)}))
            elif key == "m_Floats":
                print("      flt  %-24s %s" % (k, v))
