# -*- coding: utf-8 -*-
"""导出「原生装配参数」——不做任何几何近似。

相对 build_map.py 的差别：
  build_map.py  只给 AABB（旋转被擦平、失去轮廓）
  build_assembly 给 真实顶点 + 三角形索引 + 世界矩阵 + 精确贴图引用

数据来源（全部拆包实证）：
  Mesh.m_VertexData.m_DataSize   ch0 float32x3 = position（stride=12，无 UV）
  Mesh.m_IndexBuffer             uint16 三角形索引
  Transform 父链                 TRS 合成世界矩阵
  RuntimeTextureInstanceSetter   _sprite -> Sprite.m_RD.texture -> Texture2D
  Material.m_SavedProperties     _Color / _FogColor / _FogDensity / _FogGradient
  SpotSingleMap.Near/Mid/Far/End 视差分层 _objectList
  Camera(spotcameracontrol)      field of view 60 / near 0.1 / far 300 / ClearFlags 1

用法：python build_assembly.py <bundle> <out.json> [tex_root]
"""
import UnityPy, json, os, sys, struct, collections

ROOTS = {"static_object", "dynamic_object", "noncol_object", "cover_object",
         "hard", "medium", "soft", "NotCombatZone", "ground"}

ANCHOR_KEYS = ("character_position", "aim_position", "camera_position",
               "hide_position", "cover_1", "cover_2", "cover_3", "cover_4",
               "cover_5", "NotCombatZone")

SKIP_MB = {"m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance",
           "m_PrefabAsset", "m_GameObject", "m_Enabled", "m_EditorHideFlags",
           "m_Script", "m_EditorClassIdentifier"}


# ---------------- 矩阵 ----------------
def trs(pos, rot, scl):
    x, y, z, w = rot
    xx, yy, zz = x * x, y * y, z * z
    m = [[1 - 2 * (yy + zz), 2 * (x * y - z * w), 2 * (x * z + y * w), pos[0]],
         [2 * (x * y + z * w), 1 - 2 * (xx + zz), 2 * (y * z - x * w), pos[1]],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (xx + yy), pos[2]],
         [0.0, 0.0, 0.0, 1.0]]
    for j in range(3):
        for i in range(3):
            m[i][j] *= scl[j]
    return m


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def apply(m, p):
    x, y, z = p
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def v3(d, w=0.0):
    return (d.get("x", 0.0), d.get("y", 0.0), d.get("z", 0.0))


def v4(d, w=1.0):
    return (d.get("x", 0.0), d.get("y", 0.0), d.get("z", 0.0), d.get("w", w))


def pid(d):
    return (d or {}).get("m_PathID", 0)


def pname(x):
    return (x.get("name") or x.get("Name")) if isinstance(x, dict) else x


# ---------------- 主解析 ----------------
def parse(path, tex_root=None):
    env = UnityPy.load(path)
    objs = list(env.objects)

    script_name = {}
    for o in objs:
        if o.type.name == "MonoScript":
            d = o.read()
            script_name[o.path_id] = getattr(d, "m_ClassName", None) or "?"

    trs_map, go_name, go_comp = {}, {}, {}
    mesh_raw, rend, mat, spr, tex = {}, {}, {}, {}, {}
    mb = []          # (script_name, typetree)
    index_buf = {}

    for o in objs:
        t = o.type.name
        if t == "Transform":
            tt = o.read_typetree()
            trs_map[o.path_id] = dict(
                p=v3(tt.get("m_LocalPosition", {})),
                q=v4(tt.get("m_LocalRotation", {})),
                s=v3(tt.get("m_LocalScale", {})),
                father=pid(tt.get("m_Father")),
                go=pid(tt.get("m_GameObject")),
            )
        elif t == "GameObject":
            tt = o.read_typetree()
            go_name[o.path_id] = tt.get("m_Name", "")
            go_comp[o.path_id] = [c["component"]["m_PathID"] for c in tt.get("m_Component", [])]
        elif t == "Mesh":
            tt = o.read_typetree()
            vd = tt.get("m_VertexData", {}) or {}
            n = vd.get("m_VertexCount", 0)
            raw = vd.get("m_DataSize")
            pts = []
            if n and isinstance(raw, (bytes, bytearray)):
                stride = len(raw) // n
                # 定位 position 通道（通常 ch0 offset 0，2 floats 时退化为 2D）
                chans = vd.get("m_Channels", []) or []
                poff, pdim = 0, 3
                if chans and isinstance(chans[0], dict):
                    poff = chans[0].get("offset", 0) or 0
                    pdim = chans[0].get("dimension", 3) or 3
                for i in range(n):
                    off = i * stride + poff
                    try:
                        if pdim >= 3:
                            x, y, z = struct.unpack_from("<3f", raw, off)
                        else:
                            x, y = struct.unpack_from("<2f", raw, off)
                            z = 0.0
                    except Exception:
                        break
                    pts.append((x, y, z))
            idx = tt.get("m_IndexBuffer")
            # UnityPy 的 m_IndexBuffer 有时返回 list[int]（每项一字节），有时返回 bytes，
            # 必须统一成 bytes 再按 uint16 解索引，否则三角形全部丢失。
            if isinstance(idx, list):
                idx = bytes(b & 0xFF for b in idx)
            if isinstance(idx, (bytes, bytearray)):
                index_buf[o.path_id] = bytes(idx)
            mesh_raw[o.path_id] = dict(name=tt.get("m_Name", ""), pts=pts,
                                       aabb=tt.get("m_LocalAABB", {}))
        elif t == "MeshRenderer":
            tt = o.read_typetree()
            rend[pid(tt.get("m_GameObject"))] = dict(
                mats=[pid(m) for m in (tt.get("m_Materials") or [])],
                en=tt.get("m_Enabled"))
        elif t == "Material":
            tt = o.read_typetree()
            sp = tt.get("m_SavedProperties", {}) or {}
            props = {"tex": {}, "col": {}, "flt": {}}
            for it in (sp.get("m_TexEnvs") or []):
                k, v = (it if isinstance(it, (list, tuple)) else (it.get("first"), it.get("second")))
                props["tex"][pname(k)] = pid((v or {}).get("m_Texture"))
            for it in (sp.get("m_Colors") or []):
                k, v = (it if isinstance(it, (list, tuple)) else (it.get("first"), it.get("second")))
                props["col"][pname(k)] = {kk: round(vv, 5) for kk, vv in (v or {}).items()
                                          if isinstance(vv, (int, float))}
            for it in (sp.get("m_Floats") or []):
                k, v = (it if isinstance(it, (list, tuple)) else (it.get("first"), it.get("second")))
                props["flt"][pname(k)] = v
            mat[o.path_id] = dict(name=tt.get("m_Name"), props=props)
        elif t == "Sprite":
            tt = o.read_typetree()
            r = tt.get("m_Rect", {}) or {}
            pv = tt.get("m_Pivot", {}) or {}
            spr[o.path_id] = dict(name=tt.get("m_Name", ""),
                                  tex=pid((tt.get("m_RD") or {}).get("texture")),
                                  w=r.get("width", 0.0), h=r.get("height", 0.0),
                                  ptu=tt.get("m_PixelsToUnits", 100.0) or 100.0,
                                  px=pv.get("x", 0.5), py=pv.get("y", 0.0))
        elif t == "Texture2D":
            tt = o.read_typetree()
            tex[o.path_id] = tt.get("m_Name", "")
        elif t == "MonoBehaviour":
            tt = o.read_typetree()
            mb.append((script_name.get(pid(tt.get("m_Script")), "?"), tt))

    # ---------- 世界矩阵 ----------
    go_tr = {}
    for gid, comps in go_comp.items():
        for c in comps:
            if c in trs_map:
                go_tr[gid] = c
                break

    cache = {}

    def world(tid, depth=0):
        if tid in cache:
            return cache[tid]
        t = trs_map.get(tid)
        if t is None or depth > 64:
            return [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        local = trs(t["p"], t["q"], t["s"])
        f = t["father"]
        m = mat_mul(world(f, depth + 1), local) if f else local
        cache[tid] = m
        return m

    def root_group(gid):
        tr = trs_map.get(go_tr.get(gid, 0))
        cur = gid
        g = 0
        while tr and tr["father"] and g < 64:
            ft = trs_map.get(tr["father"])
            if not ft:
                break
            cur = ft["go"]
            nm = go_name.get(cur, "")
            if nm in ROOTS:
                return nm
            tr = ft
            g += 1
        return go_name.get(cur, "")

    # ---------- 分类索引 ----------
    grader = {}          # go -> CollisionGradeType
    tex_setter = {}      # go -> (sprite_id, material_id)
    cover_owner = {}     # go -> Cover1..5
    single_map = None

    for sn, tt in mb:
        g = pid(tt.get("m_GameObject"))
        if "CollisionGradeType" in tt:
            grader[g] = tt["CollisionGradeType"]
        if sn == "RuntimeTextureInstanceSetter":
            tex_setter[g] = (pid(tt.get("_sprite")), pid(tt.get("_material")))
        elif sn in ("NKSpotCover", "NKSpotCoverObject") and "CoverIndex" in tt:
            cover_owner[g] = tt["CoverIndex"]
        elif sn == "SpotSingleMap":
            single_map = tt

    # 分层视差
    layers = {}
    if single_map:
        for lname in ("Near", "Mid", "Far", "End"):
            grp = single_map.get(lname) or {}
            ids = [pid(x) for x in (grp.get("_objectList") or [])]
            layers[lname] = dict(scrollWidth=grp.get("_scrollWidth"), roots=ids)
        for k in ("NearSpeed", "MidSpeed", "FarSpeed", "EndSpeed", "IsOnScroll",
                  "BeginSpeed", "ScrollSpeed", "LensSettings"):
            layers[k] = single_map.get(k)

    # 分层根 -> 归属（_objectList 里可能是 Transform 或 GameObject 的 PathID，统一成 GO）
    root2layer = {}
    for lname in ("Near", "Mid", "Far", "End"):
        for r in (layers.get(lname, {}).get("roots") or []):
            r = r or 0
            goid = trs_map[r]["go"] if r in trs_map else r
            root2layer[goid] = lname

    def walk_layer(gid):
        cur = gid
        g = 0
        while cur and g < 80:
            if cur in root2layer:
                return root2layer[cur]
            tr = trs_map.get(go_tr.get(cur, 0))
            if not tr or not tr["father"]:
                break
            ft = trs_map.get(tr["father"])
            if not ft:
                break
            cur = ft["go"]
            g += 1
        return None

    # Mesh 绑定：MeshFilter.m_Mesh 运行时为 0（由 RuntimeTextureInstanceSetter 注入），
    # 因此优先取 MeshCollider.m_Mesh，兜底按「物体名 == mesh 名」匹配。
    meshfilter = {}
    for o in objs:
        if o.type.name == "MeshFilter":
            tt = o.read_typetree()
            meshfilter[pid(tt.get("m_GameObject"))] = pid(tt.get("m_Mesh"))
    for o in objs:
        if o.type.name == "MeshCollider":
            tt = o.read_typetree()
            g = pid(tt.get("m_GameObject"))
            m = pid(tt.get("m_Mesh"))
            if m and not meshfilter.get(g):
                meshfilter[g] = m

    mesh_by_name = {}
    for mid, m in mesh_raw.items():
        if m["pts"]:
            mesh_by_name.setdefault(m["name"], mid)

    props, anchors = [], collections.defaultdict(list)

    for gid in go_comp:
        name = go_name.get(gid, "")
        tid = go_tr.get(gid)
        if tid is None:
            continue
        m = world(tid)
        wx, wy, wz = apply(m, (0, 0, 0))
        base = name.split(" (")[0]

        if base in ANCHOR_KEYS or name in ANCHOR_KEYS:
            anchors[base].append([round(wx, 3), round(wy, 3), round(wz, 3)])
            continue

        mid = meshfilter.get(gid)
        if not mid or mid not in mesh_raw or not mesh_raw[mid]["pts"]:
            mid = mesh_by_name.get(base) or mesh_by_name.get(name) or mid
        r = rend.get(gid)
        if (not mid or mid not in mesh_raw) and r is None:
            continue

        # 地形碰撞网格（ground_col 一类）不是可视美术，混进来会糊住画面，
        # 也会让射线在第一米就撞上「隐形地板」，段数全归零。
        if base.endswith("_col") or "_col_" in base:
            continue

        sid, matid = tex_setter.get(gid, (0, 0))
        # 贴图名：sprite -> texture
        tex_name = ""
        if sid in spr:
            tex_name = tex.get(spr[sid]["tex"], spr[sid]["name"])
        if not tex_name and matid in mat:
            t0 = mat[matid]["props"]["tex"].get("_MainTex", 0)
            tex_name = tex.get(t0, "")

        mesh = mesh_raw.get(mid) if mid else None
        entry = dict(
            n=base,
            g=root_group(gid),
            q=grader.get(gid, -1),
            cover=cover_owner.get(gid),
            layer=walk_layer(gid),
            tex=tex_name,
            m=[round(wx, 3), round(wy, 3), round(wz, 3)],
        )
        if mesh and mesh["pts"]:
            # —— 2026-10-26 修订：默认全取三角形 ——
            # 原实现「只导出 z 最小那一层」是给单面平板设的减半优化，注释还写着
            # 「侧壁厚度对屏幕面积影响 < 1%」。这对渲染成立，对射线求交不成立：
            # 0.5 厚盒状件的侧壁三角形是跨两层的，只取一层会整片丢掉。
            #
            # 实测 sbg_cityforest_c_desk06_03（298 顶点 / 588 三角形）：
            #   全在 z=0    144
            #   全在 z=0.5  144
            #   跨两层（侧壁）300   ← 51%
            # 只取 zmin 后只剩 144（24.5%），射线会从侧壁缺口漏过去，本该被截断的遮挡失效，段数系统性偏高。
            # 沼泽/母鲸八套以大片平面为主，侧壁占比低，所以这个 bug 一直没暴露。
            #
            # 需要减半数据量时设 SHEET_ONLY=1（只对纯平面件安全）。
            pts = mesh["pts"]
            if os.environ.get("SHEET_ONLY") == "1":
                zmin = min(p[2] for p in pts)
                keep = [k for k, p in enumerate(pts) if abs(p[2] - zmin) < 1e-3]
            else:
                keep = list(range(len(pts)))
            remap = {k: j for j, k in enumerate(keep)}
            fv = [pts[k] for k in keep]
            raw = index_buf.get(mid)
            tri = []
            if raw and fv:
                n16 = len(raw) // 2
                idxs = struct.unpack_from("<%dH" % n16, raw, 0)
                for t in range(0, n16 - 2, 3):
                    a, b, c = idxs[t], idxs[t + 1], idxs[t + 2]
                    if a in remap and b in remap and c in remap:
                        tri += [remap[a], remap[b], remap[c]]
            if not tri and fv:
                tri = list(range(len(fv)))
            entry["v"] = [list(round(c, 3) for c in apply(m, p)) for p in fv]
            entry["i"] = tri
            # 原生 mesh 不带 UV，贴图按正面局部包围盒归一化映射（已验证：
            # sm_building03 sprite 215×387/100 × scale8 == 原生 AABB 17.2×30.96）
            if fv:
                x0 = min(p[0] for p in fv); x1 = max(p[0] for p in fv)
                y0 = min(p[1] for p in fv); y1 = max(p[1] for p in fv)
                entry["lb"] = [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]
                dx = (x1 - x0) or 1.0
                dy = (y1 - y0) or 1.0
                uvs = []
                for p in fv:
                    uvs += [round((p[0] - x0) / dx, 4), round((p[1] - y0) / dy, 4)]
                entry["uv"] = uvs
        elif sid in spr and spr[sid]["w"] > 0:
            # 无 mesh 的无碰撞装饰：运行时按 Sprite 生成 billboard。
            # 规则已用 sm_building03 验证：sprite 宽高/100 × Transform 缩放 == 原生 AABB
            sp = spr[sid]
            wu = sp["w"] / sp["ptu"]
            hu = sp["h"] / sp["ptu"]
            x0, x1 = -sp["px"] * wu, (1.0 - sp["px"]) * wu
            y0, y1 = -sp["py"] * hu, (1.0 - sp["py"]) * hu
            quad = [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)]
            entry["v"] = [list(round(c, 3) for c in apply(m, p)) for p in quad]
            entry["i"] = [0, 1, 2, 0, 2, 3]
            # sprite 已带完整 rect，UV 直接铺满整图（不要再按 alpha bbox 收缩）
            entry["uv"] = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
            entry["quad"] = 1
            entry["sprite"] = [sp["w"], sp["h"], sp["px"], sp["py"]]
        else:
            entry["v"], entry["i"] = [], []
        props.append(entry)

    out = dict(
        arena=os.path.splitext(os.path.basename(path))[0],
        anchors=dict(anchors),
        layers=layers,
        props=props,
    )

    # 场景级参数（来自同区域其它 bundle 与 ConfigBattleTable 的实证值）
    out["camera"] = dict(fov=60.0, near=0.1, far=300.0, ortho=False,
                         clearFlags=1, hdr=True, msaa=True,
                         bgColor=[0.1922, 0.3020, 0.4745],
                         note="spotcameracontrol Camera 组件实测；position/pitch 由运行时 Cinemachine 驱动")
    out["postfx"] = dict(
        bloom=dict(threshold=0.9, intensity=0.7, scatter=0.0),
        vignette=dict(intensity=0.431, smoothness=0.39,
                      color=[0.29245, 0.24082, 0.18071], center=[0.5, 0.5]),
        colorAdjust=dict(postExposure=0.03, contrast=6.0, saturation=5.0,
                         colorFilter=[0.99057, 0.96604, 0.95786]),
        note="fieldetc-map_assets_pp_field_<region> 的 VolumeProfile 实测",
    )
    out["fog"] = dict(color=[0.4627, 0.4627, 0.4627], density=0.0, gradient=0.001,
                      note="NKMaterial_Background 的 _FogColor/_FogDensity/_FogGradient")

    # 材质汇总（去重）
    out["materials"] = {m["name"]: m["props"] for m in mat.values()}

    # 硬断言：0 三角面 = 链路静默失败（网格存储形态不对 / index buffer 解析错），
    # 不要让它变成一份「这关没有可破坏物」的空装配。
    n_tri = sum(len(p["i"]) // 3 for p in props)
    if n_tri == 0:
        raise RuntimeError(
            f"{out['arena']}: 0 三角面 —— 网格没读出来。"
            "检查 m_VertexData.m_DataSize 是否为空、m_IndexBuffer 是否为 list[int]"
        )
    return out


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    data = parse(src)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    n_tri = sum(len(p["i"]) // 3 for p in data["props"])
    print("arena:", data["arena"], "props:", len(data["props"]), "tris:", n_tri)
    print("有顶点:", sum(1 for p in data["props"] if p["v"]),
          "/ 有贴图:", sum(1 for p in data["props"] if p["tex"]))
    print("根分组:", dict(collections.Counter(p["g"] for p in data["props"])))
    print("分层:", dict(collections.Counter(p["layer"] for p in data["props"])))
    print("锚点:", {k: len(v) for k, v in data["anchors"].items()})
    print("size:", round(os.path.getsize(dst) / 1e6, 2), "MB")
