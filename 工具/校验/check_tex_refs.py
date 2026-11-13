# -*- coding: utf-8 -*-
"""glb → 贴图 的正向引用校验（回答「是不是还缺素材」）。

注意：本项目的 glb 把贴图**内嵌在 bufferView**（images[].bufferView + mimeType），
不写外部 uri。所以「glb 能否渲染」不依赖 tex/ 目录 —— tex/ 是给人核对的副本。
这里核对的是 images[].name 是否在 tex/ 下有同名 png，用来发现「导出了图但没打进 glb」
和「打进 glb 但没导出图」两类错位。

判据：
  缺图 = glb 引用但 tex/ 下不存在   → 副本缺失，核对/替换贴图时抓不到源
  孤儿 = tex/ 有但 glb 没引用       → 只是多导出，不影响画面

用法：
    python 工具/校验/check_tex_refs.py            # 摘要
    python 工具/校验/check_tex_refs.py --list     # 逐场景列缺失明细
"""
from __future__ import annotations

import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH, LIB                                  # noqa: E402


def glb_json(path):
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] != b"glTF":
        raise ValueError("不是 glb")
    n = struct.unpack("<I", d[12:16])[0]
    return json.loads(d[20:20 + n].decode("utf-8"))


def main():
    verbose = "--list" in sys.argv
    reg = PATH.registry()
    bad, tot_ref, tot_miss = [], 0, 0
    for arena in sorted(reg):
        r = reg[arena]
        gpath = os.path.join(LIB, r["chapter_dir"], r["dir"], "mesh", "arena_%s.glb" % arena)
        if not os.path.exists(gpath):
            bad.append((arena, ["<无 glb>"]))
            continue
        try:
            j = glb_json(gpath)
        except Exception as e:
            bad.append((arena, ["<glb 解析失败 %s>" % e]))
            continue
        texdir = os.path.join(os.path.dirname(os.path.dirname(gpath)), "tex")
        have = {f.lower() for f in os.listdir(texdir)} if os.path.isdir(texdir) else set()
        miss = []
        for im in j.get("images") or []:
            nm = (im.get("name") or "").strip()
            if not nm or nm == "ground_tile":
                # ground_tile 是 export_glb.py 用 *_groundNN_c.png 现场拼的合成图，
                # 本来就没有同名源文件，不算缺失（见 §21.7 的地面丢失坑）。
                continue
            tot_ref += 1
            if nm.lower() + ".png" not in have:
                miss.append(nm)
        tot_miss += len(miss)
        if miss:
            bad.append((arena, miss))

    print("场景 %d · 内嵌贴图 %d 张 · tex/ 缺副本 %d 张 · 有问题场景 %d 个"
          % (len(reg), tot_ref, tot_miss, len(bad)))
    if verbose:
        for arena, miss in bad:
            print("  %-10s 缺 %d: %s" % (arena, len(miss), ", ".join(miss[:8])
                                         + (" ..." if len(miss) > 8 else "")))
    elif bad:
        print("  受影响：%s" % " ".join(a for a, _ in bad[:20]))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
