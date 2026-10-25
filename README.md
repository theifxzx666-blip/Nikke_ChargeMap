# NIKKE 地图充能点计算

从 NIKKE 客户端拆包，还原战场原生装配，按实机相机逐像素反推「一枪能穿几个可破坏物件」，
输出玩家视角的充能点标注页。

目前覆盖两张图：

| 图 | 战场数 | 页面 |
|---|---|---|
| H36-35 沼泽丛林 | 5（001~005） | `H36-35玩家视角充能点.html` |
| H39-40 母鲸领域 | 3（mw001~003） | `H39-40母鲸领域充能点.html` |

双击 `启动战场查看器.bat` 会在 8899 端口起本地服务并打开两个页面（三维视图需要 http 才能加载 glTF）。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/01-场景还原.md`](docs/01-场景还原.md) | 拆包 → Transform 世界矩阵 → 三角面集合 + 相机 + 锚点，含精度校验与已知近似 |
| [`docs/02-充能点算法.md`](docs/02-充能点算法.md) | 充能公式实证、像素级选点、稳定半径、掩体三层、遮挡截断、像素 NMS、可信度、轮换、六项审计 |
| [`docs/03-实例.md`](docs/03-实例.md) | 八图规模、Top1 全链路、案例拆解、分级分布、轮换发数、复核命令 |
| [`docs/README.md`](docs/README.md) | 索引与一句话流程 |

完整迭代记录（18 节）见 [`PROMPT.md`](PROMPT.md)。

## 结论摘要

- **130 个判定点**全部过了六项独立审计（代码往返自洽 ≤0.03px、容错锥、五阵位、俯角、宽高比、首击物尺寸）。
- 分级 **S 3 / A 15 / B 35 / C 36 / D 41**。A 级及以上（18 个）可以直接照着打。
- **只有 22% 的点在 5 个掩体下都能打 ≥2 段** —— 换掩体后被自家高掩体挡住是「不准」的最大原因。
- **像素坐标只在 16:9 有效**，21:9 上边缘点会横向漂 100~250px。

具体推导见 [`PROMPT.md`](PROMPT.md)（§15 像素级选点 / §16 可信度 / §17 战场轮换 / §18 独立审计）。

## 目录

```
数据/
  scan_px.py        主脚本：相机深度图 → 逐像素枪口角 → 段数 → 稳定半径 → 选点
  verify_px.py      蒙特卡洛可信度（随机误差进评分，系统性偏差做 OAT）
  audit_px.py       独立审计 A~F 六项 + 分级
  sim_charge.py     战场轮换模拟（池子 / 发数 / 贪心重排）
  scan_best.py      几何内核（射线求交、命中计数、常量）
  build_assembly.py 拆包 → 原生装配 JSON
  export_glb.py     装配 JSON → glTF
  gen_fp_page.py    生成沼泽丛林页
  gen_mw_page.py    生成母鲸领域页
  audit_html.py     把审计 JSON 渲染成页面一节
  probe_pixel.py    反查工具：某个像素打到什么
  viewer/           three.js 三维查看器（fp.html 是带点位标注的那个）
  导出/             assembly_*.json（场景装配）、px_*.json（点位）、audit_*.json（审计）
  render/           fp_*.png 无 HUD 机位出图（页面引用）
```

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

依赖：`numpy`、`UnityPy`（拆包）、`Pillow`（出图）。

## 未纳入版本库的内容

体积大且完全可再生的部分已写进 `.gitignore`，克隆后需自行生成：

| 路径 | 体积 | 生成方式 |
|---|---|---|
| `数据/原始bundle/` | ~107 MB | 从客户端提取 |
| `数据/素材/` | ~92 MB | `dump_textures.py` |
| `数据/导出/*.glb` | ~82 MB | `export_glb.py` |
| `数据/render/` 里除 `fp_*.png` 外的截图 | ~200 MB | 重新截图 |

没有这些也能读页面和所有 JSON，只是三维视图打不开、场景贴图缺失。

## 已知未解决

- 相机俯角 / FOV 未标定 → 像素坐标带 ±27px 系统性不确定
- `hpdamage_limit=30` 语义未定 → 轮换模型 A/B 假设差 1 倍
- 敌人 / 队友 / 残骸的实体遮挡未计（不在场景装配里）
- 单发伤害未拆出，换弹未计
