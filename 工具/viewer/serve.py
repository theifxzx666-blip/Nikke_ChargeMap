# -*- coding: utf-8 -*-
"""场景查看器的本地服务（PROMPT §21.12）。

为什么必须起服务：app.html 用 ES module + fetch 读 registry / scene_list / glb，
`file://` 协议下会被 CORS 全挡死（模块跨源、fetch 同源策略），双击 HTML 打不开。

用法：
    python 工具/viewer/serve.py                 # 起服务并自动开浏览器
    python 工具/viewer/serve.py --port 9000
    python 工具/viewer/serve.py --no-open       # 只起服务

端口被占会自动往后挪，直到找到空的。
"""
from __future__ import annotations

import argparse
import functools
import http.server
import os
import socket
import socketserver
import sys
import threading
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # 仓库根：静态服务的目录
PAGE = "/%s/viewer/app.html" % os.path.basename(os.path.dirname(HERE))
DEFAULT_PORT = 8920


class Handler(http.server.SimpleHTTPRequestHandler):
    """静音版：只汇报错误，别把每个 200 请求都刷到控制台"""

    def log_message(self, fmt, *args):
        code = args[1] if len(args) > 1 else ""
        if str(code).startswith(("4", "5")):
            sys.stderr.write("  %s %s\n" % (self.requestline, code))

    def end_headers(self):
        # 场景文件体积大、内容不变，允许缓存，切场景来回时不重复下载
        if self.path.endswith((".glb", ".png", ".json")):
            self.send_header("Cache-Control", "public, max-age=3600")
        super().end_headers()


def free_port(start):
    for p in range(start, start + 40):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise SystemExit("8920~8960 全被占用")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    port = free_port(a.port)
    url = "http://127.0.0.1:%d%s" % (port, PAGE)

    socketserver.TCPServer.allow_reuse_address = True
    handler = functools.partial(Handler, directory=ROOT)
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), handler) as httpd:
        print("NIKKE 场景查看器")
        print("  根目录  %s" % ROOT)
        print("  地址    %s" % url)
        print("  Ctrl+C 停止\n")
        if not a.no_open:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")


if __name__ == "__main__":
    main()
