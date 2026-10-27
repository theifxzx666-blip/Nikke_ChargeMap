# -*- coding: utf-8 -*-
"""把 assembly_00N.json 转成 glTF 2.0 (.glb 单文件)。

设计原则：这里只做「格式转换」，不做任何渲染。
渲染交给开源 three.js（见 viewer.html）。

坐标：Unity 左手系 (x右 y上 z前) -> glTF 右手系 (x右 y上 z后)，即 z 取反，三角形绕序翻转。
UV：Unity v 向上，glTF v 向下 -> v' = 1 - v。
材质：游戏内无 Light 组件 + 贴图自带明暗 -> KHR_materials_unlit（不引入假光照）。
"""
import json, os, struct, sys, io
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
        return None
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
    """ground01_c 是「远->近 4 段」的透视地面图，直接平铺到 3D 平面会拉出横条。
    取其中最靠近相机的一段（底部区）作为可平铺纹理。"""
    cands = [f for f in os.listdir(texdir) if f.endswith("_ground01_c.png")]
    if not cands:
        return None
    src = os.path.join(texdir, sorted(cands)[0])
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
