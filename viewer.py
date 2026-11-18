# -*- coding: utf-8 -*-
"""场景查看器启动入口（ASCII 文件名，供 .bat 调用）。

为什么需要这一层：
  .bat 里的中文路径（工具\\viewer\\serve.py）要求批处理文件本身按 GBK 存盘，
  一旦被编辑器改存成 UTF-8 就会整段乱码报「不是内部或外部命令」。
  所以把中文路径挪进 .py（Python 默认按 UTF-8 读源码，永远不出错），
  .bat 只保留 100% ASCII 的一行调用。
"""
from __future__ import annotations

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "工具", "viewer", "serve.py")

if not os.path.isfile(TARGET):
    sys.stderr.write("找不到 %s\n仓库结构可能被改动，请检查 工具/viewer/serve.py\n" % TARGET)
    raise SystemExit(2)

sys.argv[0] = TARGET
runpy.run_path(TARGET, run_name="__main__")
