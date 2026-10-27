# 地图充能点计算 · 项目契约

> 上位契约：`F:\Codex\Nikke\AGENTS.md`（本项目 `资源库/` 对应母体 §6 的「单一资源父目录」约定）
> 消费母体：母体 B `Nikke_Skills\拆包\`（客户端 bundle）+ 少量 `CampaignChapterTable` / `CampaignStageTable` 数据表
> 状态：🟡 迭代中 —— **存储已按 v14 规范化**；第 35 章 5 阵位齐全，第 34 章仍单阵位，母鲸三套待补
> 最后更新：2026-10-27

---

## 边界

**只做**：把 NIKKE 战斗场景从客户端 bundle 还原成世界坐标三角面集合，在此几何上算出「玩家站在掩体后，
准星指向哪一像素能连续穿透几件可破坏物」—— 输出**充能点位表**与**可交互页面**。

**不做**：不碰游戏进程、不做内存修改、不做伤害模拟、不预测敌人行为、不做爆裂循环计算。
充能公式只认已在 `docs/02-充能点算法.md` 实证过的那一套。

**不依赖**：任何在线接口、账号体系、后端服务。产物是静态 HTML + JSON，双击 `启动战场查看器.bat` 即可跑。

---

## 目录职责

**v14 起为四层物理分离**：`资源库/`（输入·不可再生） → `分析/`（中间·可重算） →
`正式产物/`（交付） → `工具/`（代码）。v13 的 `数据/` 目录已整体拆除。

| 目录/文件 | 层 | 用途 |
|---|---|---|
| `资源库/场景库/` | 输入 | 一场景一目录，见下节约束 |
| `资源库/共享依赖/` | 输入 | 跨场景共用的 bundle 与数据表（`章节组/` `引擎件/` `其他/` + 5 个 json） |
| `资源库/共享依赖/采集索引/` | 输入 | `core_catalog.sqlite`(27M) + `core_store.cdb.idx`(4.6M) + `场景全集.csv`。**入库**（要连手机才能重建），见 `docs/11` §2 |
| `分析/<章节>/<arena>/` | 中间 | `px_cover_N.json` / `audit_cover_N.json` / `_run_cover_N.json`，**可整目录删掉重算** |
| `分析/_共享/` | 中间 | 跨场景共用中间量（`yaw_bands*.json`） |
| `正式产物/页面/` | 交付 | 三张 HTML（35 章 / 34 章 / 母鲸） |
| `正式产物/场景图/` | 交付 | `fp_<arena>_cover_<N>.webp` 43 张**纯场景图**（点位由页面 DOM 叠加层实时画） |
| `正式产物/清单/` | 交付 | 三张表单：`点位总表.md/.csv/.xlsx`、`覆盖率.md`、`对比/` |
| `工具/paths.py` | 代码 | **唯一路径真源**。任何脚本不许自己拼路径，一律 `import paths as PATH` |
| `工具/viewer/` | 代码 | three.js 查看器；`fp.html` 支持 `?arena= &view= &dots=0 &hud=0 &nodata=1` |
| `工具/{采集,还原,分析,出图,出页,校验}/` | 代码 | 按阶段分目录，见「核心脚本」|
| `工具/历史脚本/` | 代码 | 已退场的早期脚本，只作参考，**不得再被引用** |
| `启动战场查看器.bat` | 入口 | 起 8899 静态服务（服务根 = 工位根）并打开页面（三维视图必须走 http） |
| `PROMPT.md` | 文档 | 完整迭代记录（§10 装配 / §15 选点 / §16 可信度 / §17 轮换 / §18 审计 / §19 跨章节 / **§20 存储规范**） |
| `docs/` | 文档 | 十一份（01~04 方法论 / 05 34 章 / 06 35 章 / 07 阵位 / 08 单日归档 / 09 数据源勘察 / 10 存储规范 / **11 安卓全量采集**）+ 索引 |
| `交付包/另一台设备采集/` | 文档 | **换设备作业入口**：`README.md`（三步走）+ `PROMPT-全量采集.md`（完整指令，离线可用） |
| `临时车间/` · `回收站/` · `log/` · `_work/` | 杂项 | **不进 git**。迁移脚本、校验截图、旧版备份放这里 |
| `02_Skills/` | 技能 | 本项目技能包（正式副本），见下节 |

### 场景库约束（摘要，全文见 `PROMPT.md` §20.2）

`资源库/场景库/` 下三层：`<章节目录>/<场景目录>/{场景卡.json, source/, mesh/, tex/}`

- 章节目录名 = `H<章节号>_<中文名>`，**章节号只认 `CampaignChapterTable.chapter`**（`H34_晶化城市森林` / `H35_沼泽丛林` / `H39_母鲸领域`）
- 场景目录名 = `<短名>_<区域英文名>`（`001_swamplandjungle_001` / `bbg008_swamplandjunglebbg008`）
  - **v15 起新采集的短名统一为** `<区域缩写><变体><3位编号>`：`ac001` / `sjbbg008` / `cfsky001a`
  - 缩写表在 `工具/采集/collect_all.py` 的 `REGION_ABBR`；新增区域要补一条，否则退化成前两字母
  - 历史 16 个短名（`001` / `c001` / `mw001` / `mwbmf`）**不改**，避免连锁改页面与清单
- `source/` 只放 bundle 原件；`mesh/` 只放 `assembly_*.json` / `*_meta.json` / `*.glb` / `slots.json`；`tex/` 只放贴图 + `index.json`
- `场景卡.json` 的 `source[].sha1_16` 是「这场景采过」的唯一证据（`source/` 本身被 gitignore，新克隆必然为空）
- `mesh.hitbox` = `g ∈ {hard,medium,soft}` 的数量（**不是** props 上的字段；sj001 实测 35+28+80=143）
- **未登记 `registry.json` 的场景，`paths.py` 直接抛 `UnknownScene`** —— 这是双门禁的第二道（第一道是缺 `场景卡.json`）
- 场景卡 `mesh.tris` 会被 `analyze.py --schema` 拿去和 `_run_cover_N.json` 的指纹比对，几何改了没重算会被报出来

### 核心脚本

| 脚本 | 职责 |
|---|---|
| `工具/paths.py` | 路径真源 + registry 门禁 + `--check`（16 场景件是否齐全） |
| `工具/分析/analyze.py` | **统一分析入口**：`scan → verify → audit → rotate` 四阶段，写 `_run_cover_N.json`（含几何指纹）；`--list` / `--schema` 只读校验 |
| `工具/分析/charge_core.py` | 几何内核（射线求交 / 命中计数 / 常量），从 `scan_best.py` 抽出，**名字与签名不变** |
| `工具/分析/scan_px.py` | 主算法：相机深度图 → 逐像素枪口角 → 段数 → 稳定半径 → 选点 |
| `工具/分析/verify_px.py` | 蒙特卡洛可信度（300 次扰动）；**会整份重写 `px_*.json`** |
| `工具/分析/audit_px.py` | 六项独立审计 + S/A/B/C/D 分级 + 容错锥 |
| `工具/分析/sim_charge.py` | 战场轮换模拟（池子 / 发数 / 贪心重排） |
| `工具/分析/batch_views.py` | 按阵位批量重算（组间并行 + 断点续跑） |
| `工具/还原/build_assembly.py` | 拆包 bundle → 原生装配 JSON（世界矩阵 / 压缩网格 / Sprite billboard） |
| `工具/还原/export_glb.py` | 装配 JSON → glTF（alpha 分流：MASK vs BLEND） |
| `工具/采集/collect_all.py` | **全量采集编排器（v15）**：枚举 catalog 全 174 个 hd 场景 → 分级 P1/P2/P3 → 跑 extract/装配/贴图/glb/阵位/回填，断点续跑。`--preflight` `--list` `--export` `--plan` `--run` |
| `工具/采集/extract_core.py` | 定点提取内核（catalog → cdb.idx → adb dd → zstd，双块自愈）。`preflight()` 查四项 |
| `工具/采集/decrypt_nkdb.py` | 设备版本变了时，用 `catalog.ndb` 现解一份 `core_catalog.sqlite` |
| `工具/采集/dump_tex.py` | **通用贴图导出（v15）**：直接落所属场景的 `tex/`，取代三个硬编码 `dump_tex_*` |
| `工具/采集/extract_*.py` · `build_slots*.py` | 按场景名批量提 bundle / 生成阵位 |
| `工具/出图/render_views.py` | 按阵位出纯场景图 → webp（`dots=0 & hud=0 & nodata=1`） |
| `工具/出页/gen_fp_page.py` · `gen_cf_page.py` · `gen_mw_page.py` · `audit_html.py` | 页面生成器 |
| `工具/校验/gen_catalog.py` | **三张表单生成器 + 闸门**（`--check` 不过就别提交） |
| `工具/校验/check_page_marks.mjs` | 无头 Chrome + CDP 真机验证「切换后图上的圆点真的变了」 |
| `工具/校验/probe_pixel.py` · `gen_views_table.py` | 反查某像素打到什么 / 生成阵位对照表 |

---

## 技能表

| 技能组 | 能力点 | status | 载体 |
|---|---|:-:|---|
| 场景还原 | 客户端 bundle → 世界坐标三角面 → glTF（含 7 项字段校验） | ready | `02_Skills/场景还原与充能点/` |
| 像素级选点 | 深度图 + 逐像素枪口反推 → 段数 / 稳定半径 / NMS | ready | 同上 |
| 阵位重算 | 5 个掩体机位各自选点、审计、可信度、出图（`--view`） | ready | `02_Skills/阵位重算与点位分层/` |
| 点位分层 | 场景图与点位标注分离（sprite → DOM 叠加层） | ready | 同上 |
| 真机验收 | CDP 点击 → 读 DOM → 断言圆点数与行数 | ready | 同上（`check_page_marks.mjs`） |
| 跨章节迁移 | 换区域前必查四条 + 角度主键与像素主键等价性 | ready | `docs/04-跨章节对照.md` |
| 页面生成 | 表 + 图 + 审计节 + 机位切换条 | ready | `gen_fp_page.py` |

---

## 常用命令

```bash
PY=/c/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python
cd /f/Codex/Nikke/Nikke_Skills/地图充能计算        # 一律在工位根执行，不 cd 进子目录

# 两道闸门（提交前必跑，任一非 0 就别提交）
$PY 工具/paths.py --check                 # 16 场景件齐不齐
$PY 工具/校验/gen_catalog.py --check      # 表与数据一致否 + 重生成三张表单

# 采集（连手机；换设备做全量见 docs/11）
$PY 工具/采集/collect_all.py --preflight              # catalog / cdb.idx / zstandard / adb 四项
$PY 工具/采集/collect_all.py --list --tier 1,2         # 全集 174 个，分 P1/P2/P3，标已采
$PY 工具/采集/collect_all.py --export                  # 重生成 场景全集.csv（含每场景预估 MB）
$PY 工具/采集/collect_all.py --run --tier 1,2          # 采集 P1+P2（adb 串行，别开并行）
$PY 工具/采集/collect_all.py --run --only gh001       # 单个场景
$PY 工具/采集/collect_all.py --run --stage tex --only gh001   # 只补一阶段

# 单场景全链路（四阶段，默认 cover_3 = 游戏进图位置）
$PY 工具/分析/analyze.py 001               # scan → verify → audit → rotate
$PY 工具/分析/analyze.py 001 --view 4      # 指定阵位（空格/等号两种写法都行）
$PY 工具/分析/analyze.py 001 --stage scan  # 只跑一阶段，调试用

# 全阵位重算（16 场景 × 5 阵位）
$PY 工具/分析/analyze.py --list            # 先看哪些场景在场
$PY 工具/分析/analyze.py --jobs 6          # 并行 6 路，已有 _run 且几何未变的会跳过
$PY 工具/分析/analyze.py --force --jobs 6  # 忽略指纹强制重算

# 出图 / 出页（读分析结果，写正式产物）
$PY 工具/出图/render_views.py --force
$PY 工具/出页/gen_fp_page.py && $PY 工具/出页/gen_cf_page.py && $PY 工具/出页/gen_mw_page.py

# 真机验收（需先双击 启动战场查看器.bat）
node 工具/校验/check_page_marks.mjs
```

> `python` 指向 workbuddy 内置环境（无 UnityPy）。**必须用上面这个绝对路径**，或任意装了 `UnityPy 1.25.4` 的解释器。
> 分析类脚本在工作目录上只依赖 `paths.py`，不再有 `cd 数据` 这一步。

---

## 红线

- **章节号只认 `CampaignChapterTable.chapter`**（= `chapter_id − 1`），`id` 是主键。
  2026-10-27 就是因为取了 `id`，把沼泽丛林标成 36 章、晶化森林标成 35 章，全部返工。
  改章节前用剧本名交叉验证：`chapter_id=36 → d_main_35_*`。
- **`build_assembly.py` 默认不许只取 z 最小一层顶点**。那是单面平板的减半优化；盒状件侧壁跨两层，
  会被整片丢掉（三角面只剩 24.5%，遮挡失效、段数虚高）。需要时用 `SHEET_ONLY=1` 显式开启。
- **`*_col` 碰撞网格必须过滤**。混进来射线会在第一米撞隐形地板，段数全归零。
- **alpha 必须按分布分流**，不能一律 MASK。雾片（`*_fog01`，alpha 均值 0.16）走 MASK 会被糊成不透明灰块。
- **点位标注不许画进图片**。图片只出纯场景（`dots=0`），点位由页面 DOM 画 ——
  sprite 渲进像素后，前端任何切换都改不了它。这是 2026-10-27 最贵的一课。
- **`slots.json` 的 `camera_position` 是嵌套数组** `[[x,y,z]]`，取 `C[0]` 会得到 NaN → 整图变灰但脚本报成功。
- **顺序固定**：`scan → verify → audit → sim`。`verify_px.py` 整份重写 `px_*.json`，
  跑在 `sim_charge.py` 之后会把轮换结果冲掉。
- **像素坐标只在 16:9 有效**。21:9 上边缘点会横向漂 100~250px，换宽高比前必须重算。
- **关卡 → 具体背景的映射客户端里没有**。`CampaignStageTable` 只有服务端下发的 `spot_id`，
  `campaignlevelmapgroup_*` 的 MonoBehaviour 只有 `_stageId` + 坐标。只能给「某章战场全集」，
  具体哪一关用哪张背景必须人工开背景认图。

### 存储类（v14 新增 R5~R10）

- **R5 禁止自己拼路径**。任何脚本读写文件一律经 `工具/paths.py`，不许出现 `"../数据/..."` / `os.path.join("导出", ...)`
  这类字面量。32 个脚本 ~90 处字面量是 v13 换目录时全部返工的直接原因。
- **R6 分析结果不得写回资源库**。`资源库/` 是只读输入层；`px_*` / `audit_*` / `_run_*` 只能落 `分析/`。
- **R7 点位不得画进图片**（同上一条旧红线，此处重申）。图片只出纯场景。
- **R8 三张表单必须脚本生成**。`场景库清单.md` / `点位总表.*` / `覆盖率.md` 不许手改 —— 手改过的值下一轮
  就会被 `gen_catalog.py` 覆盖，且 `--check` 会挡下来。
- **R9 未登记 registry 的场景不参与任何批量**。`analyze.py --jobs` 只遍历 `registry.json` 里的 arena，
  新增场景必须先写 `场景卡.json` + 登记，否则静默漏算。
- **R10 迁移/一次性脚本必须留在 `临时车间/`**。那是 gitignore 目录，不进正式产物 —— 迁移脚本
  只跑一次，留在 `工具/` 里会让人误以为要维护。

### 采集类（v15 新增 R11~R13）

- **R11 `store.cdb` 不许整份 pull**（4.99 GB）。只走 `adb exec-out dd` 按 offset 定点读。
  整份拉一次既慢又占盘，且没有任何一步需要它。
- **R12 不许并行 `adb`**。单设备串行通道，多进程只会互相拖慢并把连接踩断
  （症状是零星 `dd` 返回空）。点位分析（`analyze.py`）不碰 adb，那一步才可以开并发。
- **R13 采集索引入库，但只是快照**。`资源库/共享依赖/采集索引/` 的 catalog 与 cdb.idx
  是 2026-10-22 的国际服快照，`.gitignore` 对 `*.cdb.idx` 开了白名单。
  **手机版本变了必须重取**（`docs/11` §2），不要拿旧索引硬跑 —— 全失败不是零星失败。

---

## 已知限制（不要当成 bug 反复修）

| 限制 | 原因 |
|---|---|
| 段数与稳定性天然互斥 | 受击体排成 45~55m 细长队列，共线走廊投到屏幕只有 1~2px 宽。改算法消不掉 |
| `_nf_*` 背景卡静态放置会露硬边 | 它在游戏里走视差滚动。`BG_SKIP=1` 可跳过但画面变空，**已选择保留** |
| 光照 / 阴影 / bloom / vignette 未重建 | 颜色是「贴图原色 + 均匀增益」，不等于游戏最终成像 |
| 天空盒极点拉伸 | 客户端只有 side / upper / under 三张 |
| 敌人 / 队友 / 残骸遮挡未计入 | 只算场景静态几何 |
| 母鲸三套是旧几何 | 本地无原始 bundle，无法重跑；数字与 35/34 章不可比（registry 里 `status: 待补`） |
| `001~005` 各有一份重复 bundle | 场景目录里的 `sbg_*` 与共享的 `spotbackground(hd)_*` 同 sha1；**未删原件**，去重可省约 36 MB |
| 34 章只有 `cover_3` | `c001~c005` 缺 4 个阵位，补齐要跑一遍 `analyze.py`（约 15 分钟） |

---

## 迭代日志

| 日期 | 内容 |
|---|---|
| 2026-10-27 | **v15 全量采集能力**：新增 `collect_all.py`（枚举 catalog 全 174 个 hd 场景 → 分级 P1/P2/P3 96/16/62 → 断点续跑批量采集）、`dump_tex.py`（通用贴图导出，取代三个硬编码脚本）、`decrypt_nkdb.py`（设备版本变了现解 catalog）；`extract_core.py` 去硬编码绝对路径 + `preflight()`；采集索引 32 MB 入库；`export_glb.py` 改走 `PATH`（修 v14 迁移漏改的 `BASE/导出`）；新增 `docs/11-安卓全量采集.md` 与 `交付包/另一台设备采集/` |
| 2026-10-27 | **v14 存储重构**：拆除 `数据/`，四层分离（`资源库/` `分析/` `正式产物/` `工具/`），3057 项移动；新增 `paths.py`（路径真源 + registry 双门禁）、`analyze.py`（四阶段统一入口 + 几何指纹）、`gen_catalog.py`（三张表单 + 闸门）；页面结构指纹与迁前全等。详见 `docs/10-存储规范与场景库.md` |
| 2026-10-27 | 35 章改标沼泽丛林（`chapter` 字段）、`z=zmin` 修复重算（63 点）、圣甲虫 boss 还原（`bbg008`/`bbg009`）、按 5 阵位重算 35 组、点位改 DOM 叠加层。详见 `docs/08-2026-10-27成果汇总.md` |
| 2026-10-26 | 跨章节对照（7 处要改）、`build_assembly.py` 上游修复合并 |
| 2026-10-23 | 母鲸领域三套还原 |

> 会话日志：`.workbuddy/memory/YYYY-MM-DD.md`（已纳入版本库）。
