# NIKKE 地图充能点计算

从 NIKKE 客户端拆包，还原战场原生装配，按实机相机逐像素反推「一枪能穿几个可破坏物件」，
输出玩家视角的充能点标注页。

目前覆盖 **三批共 16 套战场**：

| 区域 | 章节 | 战场 | 页面 | 精度 |
|---|---|---|---|---:|
| 沼泽丛林 `swamplandjungle` | 第 36 章（H36-35） | `sbg_001`~`005` | `H36-35玩家视角充能点.html` | ±1 px 级 |
| 晶化城市森林 `cityforestundercrystal` | 第 35 章 | `sbg_cityforestundercrystal_001`~`005`（`c001`~`c005`） | `H35玩家视角充能点.html` | ±1 px 级 |
| 母鲸领域 `motherwhalefield` | 第 39 章（H39-40） | `sbg_mw001`~`003` | `H39-40母鲸领域充能点.html` | ±1 px 级 |
| 城市林地 `cityforest` | 第 47 / 48 章 | `sbg_cityforest_001`~`003` | 见 `docs/04-跨章节对照.md` | ±1° 级 |

双击 `启动战场查看器.bat` 会在 8899 端口起本地服务并打开三个页面（三维视图需要 http 才能加载 glTF）。
三维查看器的战场下拉框已按区域分组，可直接切到 `c001~c005`。

> cityforest 三套走的是**反向枚举**（枚举枪口角 → 反投影像素），精度低一档但跨分辨率更稳。
> 两批数据的差异与修订见 [`docs/04-跨章节对照.md`](docs/04-跨章节对照.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/01-场景还原.md`](docs/01-场景还原.md) | 拆包 → Transform 世界矩阵 → 三角面集合 + 相机 + 锚点，含精度校验与已知近似 |
| [`docs/02-充能点算法.md`](docs/02-充能点算法.md) | 充能公式实证、像素级选点、稳定半径、掩体三层、遮挡截断、像素 NMS、可信度、轮换、六项审计 |
| [`docs/03-实例.md`](docs/03-实例.md) | 八图规模、Top1 全链路、案例拆解、分级分布、轮换发数、复核命令 |
| [`docs/04-跨章节对照.md`](docs/04-跨章节对照.md) | **两批 11 套的逐字段对照**：7 处必须修的地方（2 处会静默产出空几何）、两套稳定判据的换算、池子不能跨区域外推 |
| [`docs/05-第35章.md`](docs/05-第35章.md) | 第 35 章章节定位、还原命令、五图规模、段数与容错互斥、每图推荐点与穿透链、可信度/轮换/限制 |
| [`docs/README.md`](docs/README.md) | 索引与一句话流程 |

完整迭代记录（19 节）见 [`PROMPT.md`](PROMPT.md)。

## 结论摘要

以下分级**只对沼泽 + 母鲸八套成立**：

- **130 个判定点**全部过了六项独立审计（代码往返自洽 ≤0.03px、容错锥、五阵位、俯角、宽高比、首击物尺寸）。
- 分级 **S 3 / A 15 / B 35 / C 36 / D 41**。A 级及以上（18 个）可以直接照着打。
- **只有 22% 的点在 5 个掩体下都能打 ≥2 段** —— 换掩体后被自家高掩体挡住是「不准」的最大原因。
- **像素坐标只在 16:9 有效**，21:9 上边缘点会横向漂 100~250px（改用角度主键可消掉这条）。

<!-- H35_BLOCK_START -->
**晶化城市森林（35 章，120 点）**

- 分级 **S 10 / A 6 / B 24 / C 17 / D 63**；300 次扰动下的可信度 **A 14 / B 21 / C 29 / D 56**（D 占 47%）。
- 本批最硬的结论：**段数与稳定性互斥**。段数 ≥5 的 18 个点里 16 个容错锥 <3px（89%）；锥宽 ≥8px 的 18 个点段数全在 2~4。全 120 点锥宽中位 **2.5px**（沼泽丛林是 4.2px），54 个点不到 2px。
  原因是这五张图的受击体排成 45~55m 的细长队列，共线走廊投到屏幕上只有 1~2px 宽。
- 所以每图给了**双榜**：段数冠军（理论最优，多数不可按）与实战冠军（锥宽 ≥3px 前提下段数最高）。五个实战冠军分别是
  001 ④（4 段 / 锥 6.6px）、002 ⑭（4 段 / 8.4px）、003 ①（5 段 / 5.7px，性价比最高）、004 ⑥（3 段 / 20.5px）、005 ⑨（3 段 / 13.8px）。
- 五张图受击物池子 **123%~154%**，全部够充满 —— 35 章的瓶颈不是充能总量，而是「按不住」。
- 35 章的像素坐标同样只在 16:9 有效，实测 21:9 会横向漂 4~258px。
<!-- H35_BLOCK_END -->

cityforest 三套不能套用上面的分级：可破坏物只有 10~30 件（八套是 63~220 件）、
`hard` 各只有 1 件，池子/需求比大概率 < 30%，**充能点价值本来就低**。

具体推导见 [`PROMPT.md`](PROMPT.md)（§15 像素级选点 / §16 可信度 / §17 战场轮换 / §18 独立审计 / §19 跨章节对照）。

## 目录

```
数据/
  scan_px.py        主脚本：相机深度图 → 逐像素枪口角 → 段数 → 稳定半径 → 选点
  verify_px.py      蒙特卡洛可信度（随机误差进评分，系统性偏差做 OAT）
  audit_px.py       独立审计 A~F 六项 + 分级
  sim_charge.py     战场轮换模拟（池子 / 发数 / 贪心重排）
  scan_best.py      几何内核（射线求交、命中计数、常量）
  build_assembly.py 拆包 → 原生装配 JSON
  extract_sbg_cf.py 按场景名批量提取 hd 主场景 bundle（新区域用这个）
  dump_tex_cf.py    按场景名批量导出 Texture2D
  export_glb.py     装配 JSON → glTF
  gen_fp_page.py    生成沼泽丛林页
  gen_cf_page.py    生成晶化城市森林页（35 章）
  gen_mw_page.py    生成母鲸领域页
  audit_html.py     把审计 JSON 渲染成页面一节
  probe_pixel.py    反查工具：某个像素打到什么
  viewer/           three.js 三维查看器（fp.html 是带点位标注的那个）
  导出/             assembly_*.json（场景装配）、px_*.json（点位）、audit_*.json（审计）
  render/           fp_*.png 无 HUD 机位出图（页面引用）
```

> **cityforest 批次（第 47/48 章）的脚本不在本仓库** —— 那批是在另一个作业目录里内联跑的，
> 产物为 `asm_sbg_00X.json`（装配）+ `charge_multi_sbg_00X.json`（点位），字段名与 `导出/` 下的不同。
> 字段映射见 `docs/01-场景还原.md` §4.1，方法与差异见 `docs/04-跨章节对照.md`。

## 重新生成

```bash
cd 数据

# 1) 拆包 → 场景装配（需要游戏客户端，见 拆包数据源勘察.md）
python build_assembly.py 001
# 2) 装配 → glTF（三维视图用）
python export_glb.py 001
# 3) 像素级选点
python scan_px.py 001          # 或 all / mw
# 4) 可信度模拟
python verify_px.py 001 --sim=300
# 5) 独立审计
python audit_px.py 001
# 6) 出页面
python gen_fp_page.py && python gen_mw_page.py
```

35 章（晶化城市森林）用的是按场景名批量提取，不走 `build_assembly.py <编号>`：

```bash
cd 数据
# 按场景名抓 hd 主场景，排除 _rightclear / _midclear 变体与 (sd) 版本
python extract_sbg_cf.py cityforestundercrystal    # → 原始bundle/sbg_cf/sbg_cityforestundercrystal_00N.bundle

for n in 001 002 003 004 005; do
  a=c$n
  python build_assembly.py 原始bundle/sbg_cf/sbg_cityforestundercrystal_$n.bundle 导出/assembly_$a.json
  python dump_tex_cf.py $a          # 必须先于 export_glb：glb 从 素材/ 里取贴图
  python export_glb.py $a
  python scan_px.py $a
  python verify_px.py $a --sim=300
  python audit_px.py $a
  python sim_charge.py $a          # 必须在 verify_px 之后，verify 会重写 px json
done
python gen_cf_page.py
```

`sim_charge.py` 一定要排在 `verify_px.py` 后面 —— `verify_px.py` 会整份重写 `px_*.json`，跑到后面会把轮换结果冲掉（本轮 c005 就踩过一次）。

依赖：`numpy`、`UnityPy`（拆包）、`Pillow`（出图）。

**换章节前必查四条**（详见 `docs/04-跨章节对照.md` §3）：

```
① 三角面 / 顶点 比值 ≥ 1.5     → 实测全取 1.88、只取一层 0.91。低于 1.5 就是踩了 z=zmin 过滤
                                  （侧壁被丢，三角形只剩 24.5%）；2026-10-26 已默认关闭，
                                  需要时 SHEET_ONLY=1 才启用
② 有没有 *_col 地形碰撞网格     → 有就过滤，否则射线撞隐形地板，段数全归零
③ 包里有没有 Camera 对象         → 没有就用锚点位置 + fov 60，camera 字段写 null
④ 档位来源是不是 root 节点名     → 不是 CollisionGradeType，也不是文件名前后缀
```

第 ① 条是唯一会**算错数**的：cityforest 三套上它把三角形从 15,614 砍到 3,968（只剩 25.4%），
而日志一切正常。修复后与独立实现逐项一致。

## 未纳入版本库的内容

体积大且完全可再生的部分已写进 `.gitignore`，克隆后需自行生成：

| 路径 | 体积 | 生成方式 |
|---|---|---|
| `数据/原始bundle/` | ~165 MB | 从客户端提取（`extract_sbg_cf.py` / `extract_*.py`） |
| `数据/素材/` | ~144 MB | `dump_tex_cf.py` / `dump_textures.py` |
| `数据/导出/*.glb` | ~129 MB | `export_glb.py` |
| `数据/render/` 里除 `fp_*.png` 外的截图 | ~200 MB | 重新截图 |

没有这些也能读页面和所有 JSON，只是三维视图打不开、场景贴图缺失。

## 已知未解决

- **关卡 → 战斗场景的映射不在客户端**。`CampaignChapterTable` 只给章节所属区域（35 章 = `fcbg_cityforestcrystal_007`），
  `CampaignStageTable` 只有服务端下发的 `spot_id`，`campaignlevelmapgroup_*` 的 MonoBehaviour 里也只有 `_stageId` 和坐标。
  所以只能确定「35 章这五张图」，具体哪一关用哪张背景要开背景人工认。
- 相机俯角 / FOV 未标定 → 像素坐标带 ±27px 系统性不确定
- `hpdamage_limit=30` 语义未定 → 轮换模型 A/B 假设差 1 倍
- 敌人 / 队友 / 残骸的实体遮挡未计（不在场景装配里）
- 单发伤害未拆出，换弹未计
- 视差分层位移未验证（`layers.*.scrollWidth` 两批 11 套全部读成 0.0，疑似字段没读到）
- 同场景内同名的可破坏物会被误并成同一件（用 `name` 判同一性）
- 镜头能否左右拖未确认；若能拖，像素坐标系还要多一维自由度
- 八套沼泽/母鲸在 `z=zmin` 修复后未回归（本地无原始 bundle）→ 重跑时三角面会涨 3~4 倍，需抽查 Top1 是否与前值一致
- 35 章受击体排成 45~55m 细长队列，共线走廊在屏幕上只有 1~2px 宽 —— 这是「段数高的点按不住」的根因，靠算法消不掉，只能靠站点选择绕开
