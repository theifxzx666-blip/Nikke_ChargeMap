# -*- coding: utf-8 -*-
"""定位「场景里一整块空白」的真因（PROMPT §24）。

前一个 audit_mesh_tex.py 只回答「文件在不在」，这个脚本回答「贴图能不能看见」。
对每个场景的 arena_*.glb 逐个 primitive 汇总三角面，按材质归类成四类：

    T 有 baseColorTexture 且贴图亮度正常        -> 正常
    D 有 baseColorTexture 但贴图近黑（mean<25） -> unlit 下必然死黑
    W 材质无任何贴图且 baseColorFactor≈白       -> 纯白板
    F 材质无任何贴图且 baseColorFactor 有颜色    -> 纯色板（正常，如地面积水）

输出按「D+W 覆盖的三角面占比」降序，直接点名是哪个材质、哪张图、多暗。

用法：
    python 工具/校验/audit_blank.py                 # 全部场景，只打印可疑
    python 工具/校验/audit_blank.py gd001 ac001     # 指定场景
    python 工具/校验/audit_blank.py --check         # D+W 占比 >15% 即有问题是退出码 1
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

DARK_MEAN = 25.0      # 平均亮度低于此判为「近黑贴图」
WHITE_MIN = 0.9       # baseColorFactor 三通道都 > 0.9 判为白板
SUSPECT = 0.15        # D+W 三角面占比超过此值判为可疑


def read_glb(path):
    """返回 (gltf_json, bin_chunk)"""
    raw = open(path, "rb").read()
    off, js, binc = 12, None, b""
    while off < len(raw):
        clen, ctype = struct.unpack("<II", raw[off:off + 8])
        off += 8
        if ctype == 0x4E4F534A:
            js = json.loads(raw[off:off + clen].decode("utf-8"))
        elif ctype == 0x004E4942:
            binc = raw[off:off + clen]
        off += clen
    return js, binc


def tri_count(js, prim):
    if "indices" in prim:
        return js["accessors"][prim["indices"]]["count"] // 3
    return js["accessors"][prim["attributes"]["POSITION"]]["count"] // 3


def img_mean(js, binc, tex_index):
    """解 textures[tex_index] 指向的图，返回 (name, mean_luma) 或 None"""
    try:
        src = js["textures"][tex_index]["source"]
        im = js["images"][src]
    except Exception:
        return None
    if "bufferView" not in im:
        return (im.get("name") or "-", None)
    bv = js["bufferViews"][im["bufferView"]]
    o = bv.get("byteOffset", 0)
    data = binc[o:o + bv["byteLength"]]
    try:
        from PIL import Image
        pic = Image.open(io.BytesIO(data)).convert("L")
        pic.thumbnail((64, 64))
        buf = pic.tobytes()                      # 比 getdata() 快且不触发 Pillow 弃用警告
        return (im.get("name") or "-", sum(buf) / len(buf))
    except Exception:
        return (im.get("name") or "-", None)


def classify(js, binc, mat_index, cache):
    """返回 (类别, 说明)"""
    if mat_index is None:
        return "W", "无材质"
    m = js["materials"][mat_index]
    pbr = m.get("pbrMetallicRoughness", {}) or {}
    bct = pbr.get("baseColorTexture")
    if bct is not None:
        ti = bct.get("index")
        if ti in cache:
            got = cache[ti]
        else:
            got = img_mean(js, binc, ti)
            cache[ti] = got
        if got is None:
            return "D", "texture 索引坏"
        name, mean = got
        if mean is None:
            return "T", "%s (未解码)" % name
        if mean < DARK_MEAN:
            return "D", "%s mean=%.0f" % (name, mean)
        return "T", "%s mean=%.0f" % (name, mean)
    bcf = pbr.get("baseColorFactor", [1, 1, 1, 1])
    if min(bcf[:3]) > WHITE_MIN:
        return "W", "baseColor=%.2f,%.2f,%.2f" % tuple(bcf[:3])
    return "F", "baseColor=%.2f,%.2f,%.2f" % tuple(bcf[:3])


def audit_one(glb):
    js, binc = read_glb(glb)
    cache = {}
    stat = {"T": 0, "D": 0, "W": 0, "F": 0}
    detail = []
    for mi, m in enumerate(js.get("materials", [])):
        pass
    seen = set()
    for mesh in js.get("meshes", []):
        for prim in mesh.get("primitives", []):
            n = tri_count(js, prim)
            mi = prim.get("material")
            cls, why = classify(js, binc, mi, cache)
            stat[cls] += n
            key = (mi, cls)
            if cls in ("D", "W") and key not in seen:
                seen.add(key)
                detail.append((n, cls, js["materials"][mi].get("name") if mi is not None else "-", why))
    total = sum(stat.values()) or 1
    return stat, total, sorted(detail, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arenas", nargs="*")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--strict", action="store_true", help="有告警就返回 1（默认只告警不阻断）")
    a = ap.parse_args()

    glbs = sorted(glob.glob(os.path.join(ROOT, "资源库", "场景库", "*", "*", "mesh", "arena_*.glb")))
    if a.arenas:
        want = set(a.arenas)
        glbs = [g for g in glbs if os.path.basename(g)[6:-4] in want]

    rows = []
    for g in glbs:
        arena = os.path.basename(g)[6:-4]
        try:
            stat, total, detail = audit_one(g)
        except Exception as e:
            print("ERR %-16s %s" % (arena, e))
            continue
        bad = (stat["D"] + stat["W"]) / total
        rows.append((bad, arena, stat, total, detail))

    rows.sort(reverse=True)
    print("场景数 %d｜判据：近黑贴图(mean<%.0f) + 无贴图白板 的三角面占比" % (len(rows), DARK_MEAN))
    print()
    print("%-6s %-16s %7s %7s %7s %7s %8s" % ("坏占比", "场景", "T正常", "D近黑", "W白板", "F色板", "总三角"))
    flagged = 0
    for bad, arena, stat, total, detail in rows:
        mark = " !" if bad > SUSPECT else "  "
        if bad > SUSPECT or a.arenas:
            print("%.3f%s %-16s %7d %7d %7d %7d %8d"
                  % (bad, mark, arena, stat["T"], stat["D"], stat["W"], stat["F"], total))
        if bad > SUSPECT:
            flagged += 1
            for n, cls, mname, why in detail[:4]:
                print("        %s %-28s %5d 面  %s" % (cls, mname, n, why))
    print()
    print("超过 %.0f%% 的场景：%d / %d" % (SUSPECT * 100, flagged, len(rows)))
    if a.check and flagged:
        # 默认只告警：DARK_MEAN=25 会把 mean 22~25 的合法远景剪影板也算进来（PROMPT §24.4）
        print("告警：%d 个场景 D+W 占比 >%.0f%%，需人工确认是否为合法暗剪影板"
              % (flagged, SUSPECT * 100))
        return 1 if a.strict else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
