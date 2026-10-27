# 地图充能点计算 · 项目契约

> 上位契约：`F:\Codex\Nikke\AGENTS.md`
> 消费母体：母体 B `Nikke_Skills\拆包\`（客户端 bundle）+ 少量 `CampaignChapterTable` / `CampaignStageTable` 数据表
> 状态：🟡 迭代中 —— 第 35 章已按 5 阵位完成，第 34 章仍单阵位，母鲸三套为旧几何
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

| 目录/文件 | 用途 |
|---|---|
| `H35沼泽丛林玩家视角充能点.html` | 第 35 章主页面（5 阵位切换 + 圣甲虫 boss 对照） |
| `H34晶化城市森林玩家视角充能点.html` | 第 34 章页面（单阵位） |
| `H39-40母鲸领域充能点.html` | 母鲸三套（旧几何，未回归） |
| `启动战场查看器.bat` | 起 8899 静态服务并打开页面（三维视图必须走 http） |
| `docs/` | 八份文档（01~04 方法论 / 05 34 章 / 06 35 章 / 07 阵位 / 08 单日归档）+ 索引 |
| `PROMPT.md` | 完整迭代记录（§10 原生装配 / §15 像素级选点 / §16 可信度 / §17 轮换 / §18 审计 / §19 跨章节） |
| `数据/*.py` | 全链路脚本（拆包 → 装配 → 选点 → 审计 → 出页），见下表 |
| `数据/viewer/` | three.js 查看器；`fp.html` 是第一人称那个，支持 `?arena= &view= &dots=0 &hud=0 &nodata=1` |
| `数据/导出/` | `assembly_*.json`（装配）、`px_*.json`（点位）、`audit_*.json`（审计）、`slots.json`（阵位坐标） |
| `数据/render/` | `fp_<arena>_cover_<N>.webp` 35 张**纯场景图**（点位由页面 DOM 叠加层实时画） |
| `数据/原始bundle/` · `数据/素材/` | 拆包中间物（**已被 gitignore，可重生成**） |
| `02_Skills/` | 本项目技能包（正式副本），见下节 |

### 核心脚本

| 脚本 | 职责 |
|---|---|
| `build_assembly.py` | 拆包 bundle → 原生装配 JSON（世界矩阵 / 压缩网格 / Sprite billboard） |
| `export_glb.py` | 装配 JSON → glTF（alpha 分流：MASK vs BLEND） |
| `scan_px.py` | 主脚本：相机深度图 → 逐像素枪口角 → 段数 → 稳定半径 → 选点 |
| `verify_px.py` | 蒙特卡洛可信度（300 次扰动）；**会整份重写 `px_*.json`** |
| `audit_px.py` | 六项独立审计 + S/A/B/C/D 分级 + 容错锥 |
| `sim_charge.py` | 战场轮换模拟（池子 / 发数 / 贪心重排） |
| `batch_views.py` | 按阵位批量重算（组间并行 6 路 + 断点续跑） |
| `render_views.py` | 按阵位出纯场景图 → webp（`dots=0 & hud=0 & nodata=1`） |
| `check_page_marks.mjs` | 无头 Chrome + CDP 真机验证「切换后图上的圆点真的变了」 |
| `gen_fp_page.py` / `gen_cf_page.py` / `gen_mw_page.py` | 三个页面生成器 |

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
cd 数据

# 全链路（单阵位，默认 cover_3 = 游戏进图位置）
$PY scan_px.py 001            # 选点
$PY verify_px.py 001          # 可信度（会重写 px_001.json）
$PY audit_px.py 001           # 六项审计
$PY sim_charge.py 001         # 轮换 ← 必须排在 verify 之后
$PY gen_fp_page.py            # 出页面

# 全阵位（35 章 7 战场 × 5 阵位，约 16 分钟）
$PY batch_views.py --jobs=6
$PY render_views.py --force
$PY gen_fp_page.py

# 真机验收（需先跑 启动战场查看器.bat）
node check_page_marks.mjs
```

> `python` 指向 workbuddy 内置环境（无 UnityPy）。**必须用上面这个绝对路径**，或任意装了 `UnityPy 1.25.4` 的解释器。

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

---

## 已知限制（不要当成 bug 反复修）

| 限制 | 原因 |
|---|---|
| 段数与稳定性天然互斥 | 受击体排成 45~55m 细长队列，共线走廊投到屏幕只有 1~2px 宽。改算法消不掉 |
| `_nf_*` 背景卡静态放置会露硬边 | 它在游戏里走视差滚动。`BG_SKIP=1` 可跳过但画面变空，**已选择保留** |
| 光照 / 阴影 / bloom / vignette 未重建 | 颜色是「贴图原色 + 均匀增益」，不等于游戏最终成像 |
| 天空盒极点拉伸 | 客户端只有 side / upper / under 三张 |
| 敌人 / 队友 / 残骸遮挡未计入 | 只算场景静态几何 |
| 母鲸三套是旧几何 | 本地无原始 bundle，无法重跑；数字与 35/34 章不可比 |

---

## 迭代日志

| 日期 | 内容 |
|---|---|
| 2026-10-27 | 35 章改标沼泽丛林（`chapter` 字段）、`z=zmin` 修复重算（63 点）、圣甲虫 boss 还原（`bbg008`/`bbg009`）、按 5 阵位重算 35 组、点位改 DOM 叠加层。详见 `docs/08-2026-10-27成果汇总.md` |
| 2026-10-26 | 跨章节对照（7 处要改）、`build_assembly.py` 上游修复合并 |
| 2026-10-23 | 母鲸领域三套还原 |

> 会话日志：`.workbuddy/memory/YYYY-MM-DD.md`（已纳入版本库）。
