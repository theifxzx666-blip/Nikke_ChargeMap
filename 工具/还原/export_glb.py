# -*- coding: utf-8 -*-
"""把 assembly_00N.json 转成 glTF 2.0 (.glb 单文件)。

设计原则：这里只做「格式转换」，不做任何渲染。
渲染交给开源 three.js（见 viewer.html）。

坐标：Unity 左手系 (x右 y上 z前) -> glTF 右手系 (x右 y上 z后)，即 z 取反，三角形绕序翻转。
UV：Unity v 向上，glTF v 向下 -> v' = 1 - v。
材质：游戏内无 Light 组件 + 贴图自带明暗 -> KHR_materials_unlit（不引入假光照）。
"""
import io, json, os, re, struct, sys
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE))
from paths import PATH                                     # noqa: E402
# v15：装配 JSON 与贴图都按场景解析（S6/S7），不再假设 BASE/导出 与 BASE/素材
TEXROOT = os.path.join(PATH.RES, "共享依赖", "素材")        # 仅作旧路径兜底
EX = None

FMT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
       5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
CT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


class Builder:
    def __init__(self):
        self.bin = bytearray()
        self.bvs = []
        self.accs = []

    def add_bv(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        off = len(self.bin)
        self.bin += data
        bv = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target:
            bv["target"] = target
        self.bvs.append(bv)
        return len(self.bvs) - 1

    def add_acc(self, arr, ctype, comp, target=None, minmax=True):
        n = CT[ctype]
        flat = []
        for it in arr:
            flat.extend(it if isinstance(it, (list, tuple)) else [it])
        fmt, size = FMT[comp]
        data = struct.pack("<%d%s" % (len(flat), fmt), *flat)
        bv = self.add_bv(data, target)
        acc = {"bufferView": bv, "componentType": comp,
               "count": len(arr), "type": ctype}
        if minmax and ctype in ("VEC3", "VEC2", "SCALAR") and flat:
            if ctype == "SCALAR":
                acc["min"] = [min(flat)]
                acc["max"] = [max(flat)]
            else:
                cols = list(zip(*[flat[i:i + n] for i in range(0, len(flat), n)]))
                acc["min"] = [round(min(c), 4) for c in cols]
                acc["max"] = [round(max(c), 4) for c in cols]
        self.accs.append(acc)
        return len(self.accs) - 1


def alpha_stats(path):
    """返回 (有 alpha, alpha 均值 0~1, 不透明像素占比 0~1)。

    区分两种 alpha 用法：
      硬裁切（树叶/栅栏）：大部分像素 alpha=1，只有轮廓外是 0 -> 用 MASK
      软透明（雾片/光斑）：整体 alpha 都低，均值远小于 1      -> 用 BLEND
    之前一律 MASK(cutoff 0.5)，雾片 `*_fog01` 就被切成一整块灰矩形，把画面糊白。
    """
    try:
        im = Image.open(path)
        if im.mode not in ("RGBA", "LA", "P"):
            return (False, 1.0, 1.0)
        if im.mode == "P":
            im = im.convert("RGBA")
        a = im.getchannel("A")
        ext = a.getextrema()
        if ext[1] >= 250 and ext[0] >= 250:
            return (False, 1.0, 1.0)
        hist = a.histogram()
        tot = sum(hist) or 1
        mean = sum(i * h for i, h in enumerate(hist)) / (255.0 * tot)
        opaque = sum(hist[200:]) / float(tot)
        return (True, mean, opaque)
    except Exception:
        return (False, 1.0, 1.0)


_BB = {}


def alpha_bbox(path):
    """贴图中实际不透明区域的包围盒（PIL 左上原点）。
    mesh 是按 alpha 轮廓切的，局部包围盒只对应这块区域，UV 必须映射到这里，
    映射到整张贴图会导致图案缩小并偏移。"""
    if path in _BB:
        return _BB[path]
    try:
        im = Image.open(path).convert("RGBA")
        a = im.getchannel("A")
        bb = a.getbbox()
        if bb is None:
            bb = (0, 0, im.width, im.height)
        box = (bb[0] / im.width, bb[1] / im.height, bb[2] / im.width, bb[3] / im.height,
               im.width, im.height)
    except Exception:
        box = (0.0, 0.0, 1.0, 1.0, 1, 1)
    _BB[path] = box
    return box


def build_ground(asm, B, img_tex_idx):
    """按实测地形生成分段地面带（不猜平面）。

    场景本身没有可用的 ground mesh（ground_* 只是材质引用），但每个物体的底边 y
    就是它所在位置的地面高度。按 z 分桶取 p10 得到地形剖面，再拉成条带。
    返回 (mesh_dict, node_name) 或 None。
    """
    buckets = {}
    for p in asm["props"]:
        if not p.get("v"):
            continue
        zc = sum(v[2] for v in p["v"]) / len(p["v"])
        ymin = min(v[1] for v in p["v"])
        buckets.setdefault(int(zc // 8) * 8, []).append(ymin)
    pts = []
    for k in sorted(buckets):
        v = sorted(buckets[k])
        if len(v) < 3:
            continue
        pts.append((k + 4.0, v[max(0, int(len(v) * 0.10))]))
    # 只保留主战场段（样本 >=3 的连续区），去掉远处零星样本
    pts = [p for p in pts if p[0] <= 80]
    if len(pts) < 2:
        # boss/变体场景的物件常全挤在一个 8m 桶里（gd001 的 z 只有 3~5），剖面退化成 1 个点。
        # 这类场地本身是平的，用全体底边的 p10 造一条平带，比没有地面强。
        ys = sorted(min(v[1] for v in p["v"]) for p in asm["props"] if p.get("v"))
        if not ys:
            return None
        y0 = ys[max(0, int(len(ys) * 0.10))]
        pts = [(20.0, round(y0, 3)), (60.0, round(y0, 3))]
    # 单调化：沼泽向远处缓升，局部凹陷会让地面穿插物体
    for i in range(1, len(pts)):
        if pts[i][1] < pts[i - 1][1]:
            pts[i] = (pts[i][0], pts[i - 1][1])
    # 平滑：按 8m 分桶取分位数会形成台阶，3 点滑动平均消掉棱
    for _ in range(2):
        sm = list(pts)
        for i in range(1, len(pts) - 1):
            sm[i] = (pts[i][0], round((pts[i - 1][1] + 2 * pts[i][1] + pts[i + 1][1]) / 4.0, 3))
        pts = sm
    # 向相机后方补一段，否则镜头脚下是空的（露出背景色）
    pts.insert(0, (-24.0, round(pts[0][1] - 1.2, 3)))

    HALF = 160.0
    pos, uv, idx = [], [], []
    n = len(pts)
    z0, z1 = pts[0][0], pts[-1][0]
    zr = (z1 - z0) or 1.0
    for i, (z, y) in enumerate(pts):
        # v 按实际纵深比例分配（不能用索引，否则疏密不均的段会被拉伸成条带）
        v = (z - z0) / zr
        for sx in (-HALF, HALF):
            pos.append([sx, round(y, 3), -z])      # glTF: z 取反
            uv.append([0.0 if sx < 0 else 1.0, round(v, 4)])
    for i in range(n - 1):
        a = i * 2
        idx += [a, a + 1, a + 3, a, a + 3, a + 2]
    return pos, uv, idx, pts


def ground_tile(texdir):
    """地面贴图是「一张图纵向分 4 段不同远近」的透视地面图，直接平铺到 3D 平面会拉出横条。
    取其中最靠近相机的一段（底部区）作为可平铺纹理。

    贴图编号不固定：主战场多为 `_ground01_c`，但 boss/变体场景用 `_ground02_c` / `_ground03_c`，
    沙漠、塔、迷失地区等干脆只有 `_ground_c`。早期只匹配 ground01，
    导致 **53 个场景的地面被静默丢弃**（2026-10-28 查出，全貌预览图里场景「飘在空中」就是这个原因）。
    """
    cands = [f for f in os.listdir(texdir)
             if re.search(r"_ground(\d+)?_c\.png$", f, re.I)]

    def rank(f):
        m = re.search(r"_ground(\d+)?_c\.png$", f, re.I)
        return (int(m.group(1)) if m.group(1) else 99, f)

    if not cands:
        return None
    src = os.path.join(texdir, sorted(cands, key=rank)[0])
    if not os.path.exists(src):
        return None
    im = Image.open(src).convert("RGB")
    w, h = im.size
    crop = im.crop((0, int(h * 0.78), w, int(h * 0.97)))   # 近处泥地段，避开地平线硬边
    # 裁掉左右边缘以免接缝
    crop = crop.crop((int(w * 0.02), 0, int(w * 0.98), crop.size[1]))
    # 垂直镜像拼接成上下无缝的 tile，否则平铺时会拉出等距横线
    cw, chh = crop.size
    tile = Image.new("RGB", (cw, chh * 2))
    tile.paste(crop, (0, 0))
    tile.paste(crop.transpose(Image.FLIP_TOP_BOTTOM), (0, chh))
    buf = io.BytesIO()
    tile.save(buf, format="PNG")
    return buf.getvalue()


def load_render_modes(arena):
    """从原始 bundle 读每个物体的**真实**渲染模式，返回 {物体名: "OPAQUE"|"MASK"|"BLEND"}。

    2026-11-14 定位：远景画片（_nf_）的贴图 alpha 只有 20~50%，旧逻辑按
    「alpha 不透明占比 < 50% → BLEND」判定，导出后渲染成半透明灰白 ——
    实测远景对比度只有实机的 42%（21.7 vs 51.6）、细节 40%，观感就是「上半屏一片空白」。
    真实材质 `NKMaterial_Background` 的 `_Blend=0` / `_AlphaClip=0`，**游戏里是不透明的**。
    规则：_Blend>0 → BLEND；_AlphaClip>0 → MASK；否则 OPAQUE。
    """
    try:
        import glob as _glob
        import UnityPy
    except Exception:
        return {}
    src = _glob.glob(os.path.join(PATH.scene_dir(arena), "source", "*.bundle"))
    if not src:
        return {}
    env = UnityPy.load(src[0])
    T, typ = {}, {}
    for o in env.objects:
        typ[o.path_id] = o.type.name
        try:
            T[o.path_id] = o.read_typetree()
        except Exception:
            T[o.path_id] = None
    go = {p: t.get("m_Name", "") for p, t in T.items() if t and typ[p] == "GameObject"}
    mat = {}
    for pid, t in T.items():
        if typ[pid] != "Material" or not t:
            continue
        sv = t.get("m_SavedProperties") or {}
        fl = {}
        for item in (sv.get("m_Floats") or []):
            if isinstance(item, dict):
                fl[(item.get("first") or {}).get("name")] = item.get("second")
            else:
                fl[str(item[0])] = item[1]
        blend = fl.get("_Blend")
        clip = fl.get("_AlphaClip")
        if blend is None and clip is None:
            mode = None
        elif (blend or 0) > 0:
            mode = "BLEND"
        elif (clip or 0) > 0:
            mode = "MASK"
        else:
            mode = "OPAQUE"
        mat[pid] = mode
    out = {}
    for pid, t in T.items():
        if typ[pid] != "MeshRenderer" or not t:
            continue
        nm = go.get((t.get("m_GameObject") or {}).get("m_PathID"), "")
        refs = [m for m in (t.get("m_Materials") or []) if m]
        modes = [mat.get((r or {}).get("m_PathID")) for r in refs]
        modes = [m for m in modes if m]
        if nm and modes:
            out[nm] = modes[0]
    return out


def build(arena, out_path=None):
    src = PATH.assembly(arena)
    asm = json.load(open(src, encoding="utf-8"))
    texdir = PATH.tex_dir(arena)
    if not os.path.isdir(texdir):
        texdir = os.path.join(TEXROOT, "tex_" + arena)
    if not os.path.isdir(texdir):
        texdir = os.path.join(TEXROOT, "tex")
    out_path = out_path or PATH.glb(arena)

    B = Builder()
    imgs, texs, mats = [], [], []
    tex_cache = {}          # name -> texture index
    mat_cache = {}          # (tex, alpha) -> material index
    meshes, nodes = [], []
    # 真实渲染模式（查原始材质的 _Blend / _AlphaClip），拿不到的物体回落到贴图 alpha 启发式
    # REAL_ALPHA=1 才按原始材质的 _Blend/_AlphaClip 判定。
    # 实测：nf_ 画片材质是 Opaque 但贴图带 alpha，按 Opaque 导出会变成实色白板（矩形外露），
    # 按 MASK 导出观感略实、整体对比度几乎不变（std 21.5 vs 21.7）。收益不明确，默认关。
    rmodes = load_render_modes(arena) if os.environ.get("REAL_ALPHA") == "1" else {}

    for p in asm["props"]:
        v, idx = p.get("v"), p.get("i")
        if not v or not idx:
            continue
        # 雾片 / 光斑卡片：游戏里走自定义 fog shader（软粒子+加色），
        # 转成 glTF 后只剩「一块低 alpha 的平灰矩形」，会把远景糊成硬边灰块。
        # 这里直接剔掉，雾感交给查看器的指数雾（FOG_SKIP=0 可保留）。
        if os.environ.get("FOG_SKIP", "1") == "1" and "fog" in (p.get("tex") or "").lower():
            continue
        # 近远景背景画片（_nf_ 前缀，都是给视差层用的整块贴图卡）：
        # 没有视差滚动重建时，它就是一堵画着树的墙，边缘会露硬边，故默认不导出。
        if os.environ.get("BG_SKIP", "0") == "1" and p["g"] == "noncol_object" \
                and "_nf_" in (p.get("n") or ""):
            continue
        # 原始场景的 ground_*_tex 只是**材质引用**（ground_* 是材质名，不是地形网格），
        # 没有配套贴图，导出后变成一块纯白平面，把整片地面糊白 —— c003 的「白色空洞」就是它
        # （射线拾取 pick=150,300 命中 sbg_cityforestunder_ground_n_tex d=31.0）。
        # 地形由下面的 build_ground() 按物体底边重建，所以这里直接剔掉。
        if p["g"] == "ground":
            continue
        # Unity -> glTF
        pos = [[round(c[0], 3), round(c[1], 3), round(-c[2], 3)] for c in v]
        uvs = p.get("uv") or []
        tname = p.get("tex") or ""
        texpath = os.path.join(texdir, tname + ".png")
        if tname and os.path.exists(texpath):
            bx0, by0, bx1, by1, _, _ = alpha_bbox(texpath)
        else:
            bx0, by0, bx1, by1 = 0.0, 0.0, 1.0, 1.0
        uv2 = []
        isquad = bool(p.get("quad"))
        for k in range(0, len(uvs), 2):
            if isquad:
                # sprite 自带完整 rect，UV 铺满整图
                uv2.append([round(uvs[k], 4), round(1.0 - uvs[k + 1], 4)])
                continue
            u = bx0 + uvs[k] * (bx1 - bx0)
            # Unity v 向上，PIL y 向下：alpha 区下边 = 1-by1
            vu = (1.0 - by1) + uvs[k + 1] * (by1 - by0)
            uv2.append([round(u, 4), round(1.0 - vu, 4)])
        if len(uv2) != len(pos):
            uv2 = [[0.5, 0.5]] * len(pos)
        # 绕序翻转（左手->右手）
        tri = []
        for t in range(0, len(idx) - 2, 3):
            tri += [idx[t], idx[t + 2], idx[t + 1]]

        a_pos = B.add_acc(pos, "VEC3", 5126, 34962)
        a_uv = B.add_acc(uv2, "VEC2", 5126, 34962)
        if len(idx) <= 65535:
            a_idx = B.add_acc(tri, "SCALAR", 5123, 34963)
        else:
            a_idx = B.add_acc(tri, "SCALAR", 5125, 34963)

        # 材质
        if not tname or not os.path.exists(texpath):
            if not mats:
                mats.append(dict(name="fallback",
                                 pbrMetallicRoughness={"baseColorFactor": [0.4, 0.45, 0.4, 1.0],
                                                       "metallicFactor": 0.0, "roughnessFactor": 1.0},
                                 doubleSided=True,
                                 extensions={"KHR_materials_unlit": {}}))
            mat_i = 0
        else:
            if tname not in tex_cache:
                data = open(texpath, "rb").read()
                bv = B.add_bv(data)
                imgs.append({"bufferView": bv, "mimeType": "image/png", "name": tname})
                texs.append({"sampler": 0, "source": len(imgs) - 1})
                tex_cache[tname] = len(texs) - 1
            a_has, a_mean, a_opaque = alpha_stats(texpath)
            # 优先用原始材质的真实模式；拿不到才按贴图 alpha 猜（旧逻辑）
            real = rmodes.get(p.get("n") or "")
            if real == "OPAQUE":
                # 材质是 Opaque 但贴图带 alpha：游戏里 alpha 用来**裁形**（cutout），
                # 不是半透明混合。直接 OPAQUE 会把 alpha=0 的区域也画成实色白板（矩形边界外露），
                # 所以有 alpha 就走 MASK。
                mode = "MASK" if a_has else None
            elif real == "MASK":
                mode = "MASK"
            elif real == "BLEND":
                mode = "BLEND"
            else:
                mode = "MASK" if (a_has and a_opaque >= 0.5) else ("BLEND" if a_has else None)
            mkey = (tname, mode)
            if mkey not in mat_cache:
                m = dict(name=tname,
                         pbrMetallicRoughness={
                             "baseColorTexture": {"index": tex_cache[tname]},
                             "metallicFactor": 0.0, "roughnessFactor": 1.0},
                         doubleSided=True,
                         extensions={"KHR_materials_unlit": {}})
                if mode == "MASK":
                    m["alphaMode"] = "MASK"
                    m["alphaCutoff"] = 0.5
                elif mode == "BLEND":
                    m["alphaMode"] = "BLEND"
                mats.append(m)
                mat_cache[mkey] = len(mats) - 1
            mat_i = mat_cache[mkey]

        meshes.append({"name": p["n"],
                       "primitives": [{"attributes": {"POSITION": a_pos, "TEXCOORD_0": a_uv},
                                       "indices": a_idx, "material": mat_i, "mode": 4}]})
        nodes.append({"mesh": len(meshes) - 1, "name": p["n"],
                      "_grp": p["g"], "_grade": p.get("q", -1)})

    nodes = [n for n in nodes]

    # ---- 地面条带（实测地形剖面）----
    gres = build_ground(asm, B, None)
    if gres:
        gp, guv, gidx, gpts = gres
        # 用可平铺的近景泥土段，重复采样
        guv2 = [[round(u * 6.0, 4), round(v * 5.0, 4)] for u, v in guv]
        a_pos = B.add_acc(gp, "VEC3", 5126, 34962)
        a_uv = B.add_acc(guv2, "VEC2", 5126, 34962)
        a_idx = B.add_acc(gidx, "SCALAR", 5123, 34963)
        gname = "ground_tile"
        gdata = ground_tile(texdir)
        if gdata:
            bv = B.add_bv(gdata)
            imgs.append({"bufferView": bv, "mimeType": "image/png", "name": gname})
            texs.append({"sampler": 0, "source": len(imgs) - 1})
            tex_cache[gname] = len(texs) - 1
            mats.append(dict(name="ground",
                             pbrMetallicRoughness={
                                 "baseColorTexture": {"index": tex_cache[gname]},
                                 "metallicFactor": 0.0, "roughnessFactor": 1.0},
                             doubleSided=False,
                             extensions={"KHR_materials_unlit": {}}))
            meshes.append({"name": "GROUND", "primitives": [
                {"attributes": {"POSITION": a_pos, "TEXCOORD_0": a_uv},
                 "indices": a_idx, "material": len(mats) - 1, "mode": 4}]})
            nodes.append({"mesh": len(meshes) - 1, "name": "GROUND", "_grp": "ground", "_grade": -1})

    doc = {
        "asset": {"version": "2.0", "generator": "nikke-assembly->gltf"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes))), "name": arena}],
        "nodes": [{k: v for k, v in n.items() if not k.startswith("_")} for n in nodes],
        "meshes": meshes,
        "materials": mats,
        "textures": texs,
        "images": imgs,
        "samplers": [{"magFilter": 9729, "minFilter": 9987,
                      "wrapS": 10497, "wrapT": 10497}],
        "accessors": accs if False else B.accs,
        "bufferViews": B.bvs,
        "buffers": [{"byteLength": 0}],
        "extensionsUsed": ["KHR_materials_unlit"],
    }

    # ---- 写 GLB ----
    while len(B.bin) % 4:
        B.bin.append(0)
    doc["buffers"][0]["byteLength"] = len(B.bin)
    js = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    while len(js) % 4:
        js += b" "

    total = 12 + 8 + len(js) + 8 + len(B.bin)
    with open(out_path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(B.bin), b"BIN\x00"))
        f.write(B.bin)

    # 元数据（给 viewer 用）
    meta = dict(arena=asm["arena"], anchors=asm["anchors"], camera=asm["camera"],
                postfx=asm["postfx"], fog=asm["fog"],
                nodes=[{"name": n["name"], "grp": n["_grp"], "grade": n["_grade"]} for n in nodes])
    json.dump(meta, open(out_path.replace(".glb", "_meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("%s: props=%d meshes=%d mats=%d tex=%d  %.2f MB"
          % (arena, len(nodes), len(meshes), len(mats), len(texs),
             os.path.getsize(out_path) / 1e6))


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:]]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        print("用法: python export_glb.py <arena> [更多 arena…]   输出走 PATH.glb(arena)")
        sys.exit(0)
    for a in (argv or ["001", "002", "003", "004", "005"]):
        build(a)
