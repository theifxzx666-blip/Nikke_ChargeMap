@echo off
chcp 65001 >nul
title NIKKE 玩家视角充能点 / 战场查看器
cd /d "%~dp0数据"
echo.
echo   ── 汇总页 ───────────────────────────────────────────────
echo   H36-35 沼泽丛林  H36-35玩家视角充能点.html   （5 战场，默认 5 个点 / 可切到全部）
echo   H39-40 母鲸领域  H39-40母鲸领域充能点.html   （3 战场，默认 5 个点 / 可切到全部）
echo   第 35 章 晶化城市森林  H35玩家视角充能点.html （5 战场，默认 5 个点 / 可切到全部）
echo.
echo   ── 三维视图（arena 可换）────────────────────────────────
echo   沼泽丛林 001~005   http://127.0.0.1:8899/viewer/fp.html?arena=001
echo   母鲸领域 mw001~003 http://127.0.0.1:8899/viewer/fp.html?arena=mw001
echo   第 35 章 c001~c005 http://127.0.0.1:8899/viewer/fp.html?arena=c001
echo   无 HUD 出图模式    ^&hud=0
echo   战场自由查看       http://127.0.0.1:8899/viewer/index.html?arena=001
echo.
echo   fp.html 默认取 cover_3 机位；右上角可切 5/8/12/全部（快捷键 1/2/3/4），?n= 指定。
echo   关闭本窗口即停止服务。
echo.
rem 依次尝试：项目自带 venv → py 启动器 → PATH 里的 python
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo   [×] 没找到 Python，请装 Python 3 或把解释器路径填到本文件的 PY 变量里。
  pause
  exit /b 1
)
start "NIKKE 本地服务" /min %PY% -m http.server 8899 --bind 127.0.0.1
timeout /t 2 >nul
start "" "%~dp0H36-35玩家视角充能点.html"
start "" "%~dp0H39-40母鲸领域充能点.html"
start "" "%~dp0H35玩家视角充能点.html"
start "" "http://127.0.0.1:8899/viewer/fp.html?arena=mw001"
echo   服务已启动，窗口可最小化；关闭「NIKKE 本地服务」窗口即停止。
pause >nul
