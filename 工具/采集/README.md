# 采集层（客户端 bundle → 场景库）

这一层只做一件事：**从客户端包里把某个战斗场景的 hd 主场景 bundle 与贴图捞出来**，
放进 `资源库/场景库/<章节>/<场景>/source/`。

跑完这一层，后面交给 `工具/还原/build_assembly.py` → `工具/还原/export_glb.py`。

> **换到另一台设备做全量采集，直接看 [`docs/11-安卓全量采集.md`](../../docs/11-安卓全量采集.md)。**
> 那份是完整作业指令（环境、版本核对、174 个场景的分级、验收、十个坑），本文只说明脚本职责。

## 脚本

| 脚本 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `collect_all.py` | **全量编排器**：枚举 catalog 全部 hd 场景 → 分级 P1/P2/P3 → 批量跑 extract/装配/贴图/glb/阵位/回填，断点续跑 | catalog | `资源库/场景库/<章节>/<短名>_<区域>/` |
| `extract_core.py` | 共用链路：读 cdb 索引 → adb dd → zstd → 落 bundle（双块自愈） | catalog + `cdb.idx` | 由调用方指定 |
| `extract_sbg_cf.py` | 按场景名批量提 `spotbackground(hd)_assets_sbg_<名字>_*` | 场景名 | `资源库/共享依赖/原始bundle/sbg_<前两位>/` |
| `extract_spot_bg.py` | 按 file_id 提任意 spotbackground 系列 | 一串 file_id | `资源库/共享依赖/原始bundle/bg/` |
| `extract_camera.py` | 定点提相机相关 bundle（3 个固定 file_id） | — | `资源库/共享依赖/引擎件/camera/` |
| `dump_tex.py` | **通用贴图导出**：从某场景 bundle 导 Texture2D 进该场景自己的 `tex/` | `arena` 短名 | `<场景>/tex/*.png` + `index.json` |
| `build_slots.py` | 解 `cover_1..5` 的世界变换 + 相机位姿 | 单个 bundle | `<场景>/mesh/slots.json` |
| `build_slots_mw.py` | 同上，按目录批量 + 指定 key 前缀 | bundle 目录 + 前缀 | 各场景 `mesh/slots.json` |
| `decrypt_nkdb.py` | 把设备上的 `catalog.ndb`（NKDB，AES-OFB + zlib 分段）解成可查询 sqlite | `.ndb` | `core_catalog.sqlite` |

### v15 退场的三个脚本

`dump_textures.py` / `dump_tex_cf.py` / `dump_tex_mw.py` 已被 `dump_tex.py` 取代。
它们把贴图导到 `资源库/共享依赖/素材/tex_<arena>/`，还各自硬编码一个区域名；
新版直接把贴图落**所属场景**的 `tex/`（符合 §20.2 S7），且不再需要「贴图 → 场景」的额外推断 ——
**从哪个 bundle 导出来的就属于哪个场景**。三个旧脚本保留在 `工具/历史脚本/` 备查。

## 四个必须知道的点

**① 索引文件现在入库了（v15）。**
`core_catalog.sqlite`（27 MB）与 `core_store.cdb.idx`（4.6 MB）放在
`资源库/共享依赖/采集索引/`，`.gitignore` 里给 `*.cdb.idx` 开了白名单 ——
它们是「输入·不可再生」（要连手机才能重建），不进去的话另一台设备 clone 下来跑不了采集。
**但它们只是 2026-10-22 的快照**：手机版本变了要重取，见 docs/11 §2。

**② `extract_core` 不再有硬编码绝对路径（v15）。**
默认读 `资源库/共享依赖/采集索引/`，可用环境变量覆盖：
`NIKKE_CATALOG` / `NIKKE_CDB_IDX` / `NIKKE_STORE`。
模块带 `preflight()`，一次性检查 catalog / cdb.idx / zstandard / adb 四项。

**③ 采集中间物落 `资源库/共享依赖/`，不在代码目录。**
`BASE = dirname(abspath(__file__))` 这种写法在搬迁后会指向代码目录，会往
`工具/采集/原始bundle/` 里写几百 MB。已统一改为 `PATH.ROOT`。

**④ 不要并行 `adb`。**
单设备串行通道，开多进程只会互相拖慢，还可能把连接踩断。点位分析（`analyze.py`）不碰 adb，
那一步才适合开并发。

## 跑一遍的样子

```bash
PY=/c/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python

# 全量（推荐）：P1 主战场 + P2 boss
$PY 工具/采集/collect_all.py --preflight
$PY 工具/采集/collect_all.py --run --tier 1,2

# 或者只采单个场景的全链路
$PY 工具/采集/collect_all.py --run --only gh001 --chapter H36_某某

# 手工分步（调试用）
$PY 工具/采集/extract_sbg_cf.py swamplandjungle
$PY 工具/还原/build_assembly.py <bundle> <输出 assembly.json>
$PY 工具/采集/dump_tex.py 001
$PY 工具/还原/export_glb.py 001
$PY 工具/采集/build_slots.py
$PY 工具/paths.py --check
```
