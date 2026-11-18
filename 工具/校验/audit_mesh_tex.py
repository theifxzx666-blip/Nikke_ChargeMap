# -*- coding: utf-8 -*-
"""审计 112 个 glb 的贴图完整性（PROMPT §21.16）。

回答三个问题：
  1. 有没有「图片既无 uri 也无 bufferView」的坏引用 —— 必然渲染成空白；
  2. 有没有 uri 指向磁盘上不存在的文件；
  3. 有没有材质完全不带贴图（只有 baseColorFactor=白）—— 会渲染成一块纯色板。

用法：
    python 工具/校验/audit_mesh_tex.py            # 打印问题汇总
    python 工具/校验/audit_mesh_tex.py --check    # 有问题是退出码 1（供门禁用）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def gltf_json(path: str) -> dict:
    raw = open(path, "rb").read()
    off = 12
    while off < len(raw):
        clen, ctype = struct.unpack("<II", raw[off:off + 8])
        off += 8
        if ctype == 0x4E4F534A:
            return json.loads(raw[off:off + clen].decode("utf-8"))
        off += clen
    raise ValueError("no JSON chunk: " + path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    glbs = sorted(glob.glob(os.path.join(ROOT, "资源库", "场景库", "*", "*", "mesh", "arena_*.glb")))
    bad_ref, missing_uri, no_tex, unlit_tex = [], [], [], []
    tot_img = tot_uri = tot_bv = 0

    for g in glbs:
        arena = os.path.basename(g)[len("arena_"):-4]
        js = gltf_json(g)
        texdir = os.path.join(os.path.dirname(os.path.dirname(g)), "tex")
        for im in js.get("images", []):
            tot_img += 1
            uri = im.get("uri")
            if uri:
                tot_uri += 1
                # uri 可能是相对 tex/ 的文件名，也可能带子目录
                cand = os.path.join(texdir, uri.split("?")[0])
                if not os.path.isfile(cand):
                    missing_uri.append((arena, im.get("name") or "-", uri))
            elif "bufferView" in im:
                tot_bv += 1
            else:
                bad_ref.append((arena, im.get("name") or "-"))
        # 材质是否有任何贴图
        for m in js.get("materials", []):
            pbr = m.get("pbrMetallicRoughness", {})
            has = any(k in pbr for k in ("baseColorTexture", "metallicRoughnessTexture")) \
                or "normalTexture" in m or "emissiveTexture" in m
            if not has:
                no_tex.append((arena, m.get("name") or "-"))
                bcf = pbr.get("baseColorFactor", [1, 1, 1, 1])
                if min(bcf[:3]) > 0.9:
                    unlit_tex.append((arena, m.get("name") or "-", bcf))

    print("glb 总数        %d" % len(glbs))
    print("图片引用        %d（外部 uri %d / 内嵌 bufferView %d）" % (tot_img, tot_uri, tot_bv))
    print()
    print("[1] 坏引用（既无 uri 也无 bufferView）  %d" % len(bad_ref))
    for r in bad_ref[:20]:
        print("    %s  %s" % r)
    print("[2] uri 指向不存在的文件                %d" % len(missing_uri))
    for r in missing_uri[:20]:
        print("    %s  %s -> %s" % r)
    print("[3] 无任何贴图的材质                    %d（其中 baseColor≈白 %d）"
          % (len(no_tex), len(unlit_tex)))
    for r in unlit_tex[:20]:
        print("    %s  %s  %s" % r)

    if a.check and (bad_ref or missing_uri):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
