# -*- coding: utf-8 -*-
"""战场示意图（静态 HTML 版）启动入口（ASCII 文件名，供 .bat 调用）。

在仓库根起一个静态服务（默认 8899），再依次打开「正式产物/页面」下的三张图。
带中文的路径全部写在这里，.bat 只做 ASCII 调用，避免批处理乱码。
"""
from __future__ import annotations

import functools
import http.server
import os
import socket
import socketserver
import sys
import threading
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES = [
    ("H35 沼泽丛林", "正式产物/页面/H35沼泽丛林玩家视角充能点.html"),
    ("H34 晶化城市森林", "正式产物/页面/H34晶化城市森林玩家视角充能点.html"),
    ("H39-40 母鲸领域", "正式产物/页面/H39-40母鲸领域充能点.html"),
]
DEFAULT_PORT = 8899


def free_port(start: int) -> int:
    for p in range(start, start + 40):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise SystemExit("%d~%d 全被占用" % (start, start + 39))


def main() -> None:
    port = free_port(DEFAULT_PORT)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            code = args[1] if len(args) > 1 else ""
            if str(code).startswith(("4", "5")):
                sys.stderr.write("  %s %s\n" % (self.requestline, code))

    socketserver.TCPServer.allow_reuse_address = True
    handler = functools.partial(Handler, directory=HERE)
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), handler) as httpd:
        print("NIKKE 战场示意图（静态页）")
        print("  根目录  %s" % HERE)
        print("  地址    http://127.0.0.1:%d/" % port)
        print("  Ctrl+C 停止\n")

        opened = []
        for label, rel in PAGES:
            if os.path.isfile(os.path.join(HERE, rel)):
                opened.append("http://127.0.0.1:%d/%s" % (port, rel))
            else:
                print("  [x] 缺失：%s" % rel)
        for i, url in enumerate(opened):
            threading.Timer(0.8 + i * 0.4, lambda u=url: webbrowser.open(u)).start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")


if __name__ == "__main__":
    main()
