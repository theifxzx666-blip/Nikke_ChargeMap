# -*- coding: utf-8 -*-
"""把页面里的图片内联成 base64，产出「单文件版」HTML。

为什么需要：WorkBuddy 的预览面板只托管 HTML 文件本身，
页面里 `../场景图/充能图/*.webp` 这类相对路径一律 404，打开就是一片破图。
单文件版不依赖服务、不依赖目录结构，发给别人也能直接看。

用法：
  python 工具/出页/inline_page.py 正式产物/页面/xxx.html [...]
  → 同目录生成 xxx_单文件.html
"""
import base64
import os
import re
import sys

MIME = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg",
        "jpeg": "image/jpeg", "gif": "image/gif", "svg": "image/svg+xml"}


def inline(html_path):
    base = os.path.dirname(os.path.abspath(html_path))
    html = open(html_path, encoding="utf-8").read()
    n = [0]
    miss = []

    def rep(m):
        rel = m.group(1)
        if rel.startswith(("data:", "http:", "https:", "#")):
            return m.group(0)
        p = os.path.normpath(os.path.join(base, rel))
        if not os.path.exists(p):
            miss.append(rel)
            return m.group(0)
        ext = os.path.splitext(p)[1].lstrip(".").lower()
        b = base64.b64encode(open(p, "rb").read()).decode("ascii")
        n[0] += 1
        return 'src="data:%s;base64,%s"' % (MIME.get(ext, "application/octet-stream"), b)

    html = re.sub(r'src="([^"]+)"', rep, html)
    stem = os.path.splitext(html_path)[0]
    out = stem + "_单文件.html"
    open(out, "w", encoding="utf-8").write(html)
    size = os.path.getsize(out) / 1048576
    print("%-46s 内联 %3d 张  %.1f MB  缺 %d"
          % (os.path.basename(out), n[0], size, len(miss)))
    for m in miss[:5]:
        print("   缺:", m)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("用法：python inline_page.py <页面.html> [...]")
    for a in args:
        if "_单文件" in os.path.basename(a):      # 已经是内联版，别再套一层
            continue
        inline(a)


if __name__ == "__main__":
    main()
