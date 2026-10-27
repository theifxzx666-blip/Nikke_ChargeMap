# 采集层（客户端 bundle → 场景库）

这一层只做一件事：**从客户端包里把某个战斗场景的 hd 主场景 bundle 与贴图捞出来**，
放进 `资源库/场景库/<章节>/<场景>/source/`（或先落 `资源库/共享依赖/原始bundle/`）。

跑完这一步，后面交给 `工具/还原/build_assembly.py` → `工具/还原/export_glb.py`。

## 脚本

| 脚本 | 职责 | 输入 | 输出（v14） |
|---|---|---|---|
| `extract_core.py` | 共用链路：读 cdb 索引 → 解 chunk → 落 bundle | `core_catalog.sqlite` + `core_store.cdb.idx` | 由调用方指定 |
| `extract_sbg_cf.py` | 按场景名批量提 `spotbackground(hd)_assets_sbg_<名字>_<NNN>_<hash>.bundle` | 场景名（`swamplandjungle` / `cityforestundercrystal`） | `资源库/共享依赖/原始bundle/sbg_<前两位>/` |
| `extract_spot_bg.py` | 按 file_id 提任意 spotbackground 系列 | 一串 file_id | `资源库/共享依赖/原始bundle/bg/` |
| `extract_camera.py` | 定点提相机相关 bundle（3 个固定 file_id） | — | `资源库/共享依赖/引擎件/camera/` |
| `dump_textures.py` | 从沼泽丛林 bundle 里导 Texture2D | `原始bundle/sbg/sbg_swamplandjungle_00N.bundle` | `资源库/共享依赖/素材/tex[_00N]/` |
| `dump_tex_cf.py` | 从晶化城市森林 bundle 里导 Texture2D | `原始bundle/sbg_cf/…` | `资源库/共享依赖/素材/tex_c00N/` |
| `dump_tex_mw.py` | 从母鲸 bundle 里导 Texture2D | `原始bundle/sbg_mw/…` | `资源库/共享依赖/素材/tex_mw00N/` |
| `build_slots.py` | 解 `cover_1..5` 的世界变换 + 相机位姿，**直接写进各场景 `mesh/slots.json`** | `原始bundle/sbg/…` | `资源库/场景库/H35_沼泽丛林/00N_*/mesh/slots.json` |
| `build_slots_mw.py` | 同上，任意区域/前缀 | bundle 目录 + key 前缀 | `<场景>/mesh/slots.json` |

## 三个必须知道的点

**① 索引文件是本地缓存，不在版本库里。**
`core_store.cdb.idx`（4.6 MB）被 `.gitignore` 的 `*.cdb.idx` 挡住，克隆后没有。
它由 `extract_core.py` 首次运行生成，或从旧作业目录 `_work/` 拿一份。

**② 中间物全部落在 `资源库/共享依赖/`，不在代码目录。**
v13 时这几个脚本用 `BASE = dirname(abspath(__file__))` 当项目根，
搬到 `工具/采集/` 之后这个表达式就指向代码目录了 —— 会往 `工具/采集/原始bundle/` 里写几百 MB。
v14 已统一改为 `PATH.ROOT`，中间物落 `资源库/共享依赖/`，整目录 gitignore。

**③ 提取出来的 bundle 要手工移进场景目录并登记 sha1。**
`extract_sbg_cf.py` 只能按名字批量捞，它不知道「这个 bundle 属于第几章、对应哪个 arena」。
落位与登记流程见 `docs/10-存储规范与场景库.md` §4，约束见 `PROMPT.md` §20.2（S1~S8）。

## 跑一遍的样子

```bash
PY=/c/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python
cd /f/Codex/Nikke/Nikke_Skills/地图充能计算

# 1) 捞 hd 主场景 bundle
$PY 工具/采集/extract_sbg_cf.py swamplandjungle

# 2) 装配（输出落该场景的 mesh/）
$PY 工具/还原/build_assembly.py 资源库/共享依赖/原始bundle/sbg/sbg_swamplandjungle_001.bundle

# 3) 贴图必须早于 glb —— glb 从贴图目录取图
$PY 工具/采集/dump_textures.py 001
$PY 工具/还原/export_glb.py 001

# 4) 阵位表
$PY 工具/采集/build_slots.py

# 5) 校验件是否齐
$PY 工具/paths.py --check
```

## 待办

- `dump_tex_*` 目前把贴图导到 `共享依赖/素材/`，再靠 `export_glb.py` 去找；
  更干净的做法是直接导进对应场景的 `tex/`（需要先解出「贴图 → 场景」的归属，暂未做）
- `extract_*` 依赖母体的 `core_catalog.sqlite` 绝对路径，换机器要改文件头部的 `CAT`
