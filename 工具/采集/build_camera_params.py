# -*- coding: utf-8 -*-
"""把 §23 的相机实证值汇总成唯一数据源 camera_params.json。

上游：extract_camera.py 导出的 资源库/共享依赖/引擎件/camera/*.json
      + 资源库/共享依赖/spot_setting.json（SpotSetting 的 m_Lens/瞄准参数）

下游：工具/viewer/fp.html、app.html 的默认姿态；PROMPT §23 的表格
      —— 任何一处改值都必须先跑本脚本，保证只有一份真相。

用法：
  python build_camera_params.py           # 重建
  python build_camera_params.py --check   # 只比对，不写
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CAM = os.path.join(ROOT, "资源库", "共享依赖", "引擎件")
OUT = os.path.join(CAM, "camera_params.json")
SPOT = os.path.join(ROOT, "资源库", "共享依赖", "spot_setting.json")

SKIP = {"m_GameObject", "m_Script", "m_ObjectHideFlags", "m_CorrespondingSourceObject",
        "m_PrefabInstance", "m_PrefabAsset", "m_EditorClassIdentifier", "m_Name",
        "m_Enabled", "m_ExcludedPropertiesInInspector", "m_LockStageInInspector"}


def find(files, script):
    """按脚本类名取第一个匹配项的 data。"""
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        for it in d.get("items", []):
            if it.get("script") == script:
                return it["data"], d["file"]
    return None, None


def clean(d):
    return {k: v for k, v in (d or {}).items() if k not in SKIP}


def build():
    files = sorted(glob.glob(os.path.join(CAM, "camera", "*.json")))
    if not files:
        raise SystemExit("没有 dump：先跑 工具/采集/extract_camera.py")

    out = {"说明": "战斗相机实证参数（客户端拆包）。唯一数据源，勿手改，改 extract_camera 后重跑本脚本。",
           "来源": {}, "参数": {}}

    # ---- 1. SpotCameraControl.Camera：FOV / 裁剪面 / 投影模式 / 传感器 ----
    cam, src = find(files, None)  # Camera 没有 script 字段
    cam = None
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        for it in d.get("items", []):
            if it.get("type") == "Camera":
                cam, src = it["data"], d["file"]
                break
        if cam:
            break
    if cam:
        out["来源"]["Camera 组件"] = src
        out["参数"].update({
            "fov_vertical_deg": cam.get("field of view"),
            "near_clip": cam.get("near clip plane"),
            "far_clip": cam.get("far clip plane"),
            "orthographic": cam.get("orthographic"),
            "sensor_size_mm": [cam.get("m_SensorSize", {}).get("x"),
                               cam.get("m_SensorSize", {}).get("y")],
            "focal_length_mm": cam.get("m_FocalLength"),
            "gate_fit": cam.get("m_GateFitMode"),          # 0 None 1 Vertical 2 Horizontal 3 Fill 4 Overscan
            "projection_matrix_mode": cam.get("m_projectionMatrixMode"),  # 0 Explicit 1 Implicit 2 Physical
            "lens_shift": cam.get("m_LensShift"),
            "clear_flags": cam.get("m_ClearFlags"),
            "background_color": cam.get("m_BackGroundColor"),
        })

    # ---- 2. 三个 prefab 的 vcam Lens（FOV 一致性交叉验证）----
    vcams = {}
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        for it in d.get("items", []):
            if it.get("script") == "CinemachineVirtualCamera":
                lens = it["data"].get("m_Lens") or {}
                vcams.setdefault(d["file"].split("_assets_")[1][:34], []).append({
                    "priority": it["data"].get("m_Priority"),
                    "fov": lens.get("FieldOfView"),
                    "near": lens.get("NearClipPlane"),
                    "far": lens.get("FarClipPlane"),
                    "gate_fit": lens.get("GateFit"),
                    "sensor": lens.get("m_SensorSize"),
                })
    out["参数"]["vcam_lens"] = vcams
    out["来源"]["vcam"] = "spotpresentationbase / arenacamera + automodecameracontrol"

    # ---- 3. AutoMode 的跟随偏移与构图（自动战斗机位）----
    tp, _ = find(files, "CinemachineTransposer")
    cp, _ = find(files, "CinemachineComposer")
    if tp:
        out["参数"]["automode_transposer"] = clean(tp)
    if cp:
        out["参数"]["automode_composer"] = clean(cp)

    # ---- 4. SpotSetting 里的瞄准 / 屏幕构图 ----
    if os.path.exists(SPOT):
        s = json.load(open(SPOT, encoding="utf-8"))
        keys = ["AimVerticalFov", "AimHorizontalFov", "AimPositionInitOffsetHeight",
                "AimToScreenCenterPositionTime", "AimSensitive", "AimCameraSensitive",
                "UseAutoModeCamera", "MaxMoveSpeed", "MinMoveSpeed",
                "DecelerationTime", "DecelerationDistance", "UnFocusCharacterAimSize",
                "SDCharacterCampaignOffset", "ScopeAimAddonMinAlpha"]
        out["参数"]["spot_setting"] = {k: s.get(k) for k in keys if k in s}
        out["参数"]["aim_start_position"] = {("cover_%d" % i): s.get("AimStartPosition%d" % i)
                                            for i in range(1, 6) if ("AimStartPosition%d" % i) in s}
        out["来源"]["SpotSetting"] = "资源库/共享依赖/spot_setting.json"

    # ---- 4b. CanvasScaler：画幅适配的唯一实证（§24.1）----
    scal, _ = find(files, "CanvasScaler")
    uispot, _ = find(files, "UISpotCanvas")
    if scal:
        out["参数"]["ui_scaler"] = clean(scal)
        out["来源"]["UI 画布"] = "spotpresentationbase / canvas(screenspace-camera)-one|two（两份完全一致）"
    if uispot:
        out["参数"]["uispot_canvas"] = clean(uispot)

    # ---- 5. 推导：俯角双源互证 ----
    fov = out["参数"].get("fov_vertical_deg") or 60.0
    off = out["参数"]["spot_setting"].get("AimPositionInitOffsetHeight") if out["参数"].get("spot_setting") else None
    derive = {"fov_vertical_deg": fov}
    if off:
        import math
        frac = off / 1080.0                                  # 1080p 归一化偏移
        derive["aim_offset_px"] = off
        derive["aim_offset_frac_of_1080"] = round(frac, 4)
        derive["pitch_from_aim_offset_deg"] = round(
            math.degrees(math.atan(math.tan(math.radians(fov / 2)) * 2 * frac)), 2)
    top = out["参数"].get("fov_vertical_deg") or 60
    # 横向 FOV 随画幅变化（纵向固定）
    ar_list = {"16:9": 16 / 9, "21:9": 21 / 9, "16:10": 1.6, "4:3": 4 / 3}
    derive["horizontal_fov_deg"] = {
        k: round(2 * __import__("math").degrees(
            __import__("math").atan(__import__("math").tan(
                __import__("math").radians(top / 2)) * ar)), 2)
        for k, ar in ar_list.items()}
    derive["chosen_pitch_deg"] = 12.3
    derive["chosen_yaw_deg"] = 0.0
    derive["yaw_note"] = ("cam_yaw(-135°) 是 aim_position 相对 camera_position 的 (-0.1,0,-0.1) 偏移方位，"
                          "只是准星指示器；用作相机朝向会背对战场（已实渲染验证，见 §23.4）。"
                          "prefab 的 -38.6/-31.4/-40.5 是编辑器摆放姿态，同样不可用。")

    # ---- 6. 画幅适配：Expand 模式的 scaleFactor（Unity CanvasScaler 库语义）----
    import math
    if scal:
        ref = scal.get("m_ReferenceResolution") or {}
        rw, rh = ref.get("x"), ref.get("y")
        mode = scal.get("m_ScreenMatchMode")          # 0 Match 1 Expand 2 Shrink
        if rw and rh:
            fit = {}
            for name, (W, H) in {"16:9": (1920, 1080), "21:9": (2520, 1080)}.items():
                if mode == 1:      # Expand: 取较小比，画布只扩不裁
                    sf = min(W / rw, H / rh)
                else:              # Match/Shrink: 取较大比
                    sf = max(W / rw, H / rh)
                fit[name] = {"screen": [W, H], "scale_factor": round(sf, 4),
                             "logical_canvas": [round(W / sf), round(H / sf)]}
            hfov = derive["horizontal_fov_deg"]
            derive["canvas_fit"] = {
                "reference_resolution": [rw, rh],
                "scale_mode": {0: "MatchWidthOrHeight", 1: "Expand", 2: "Shrink"}.get(mode, mode),
                "per_aspect": fit,
                "hfov_deg": hfov,
                "note": ("Expand = 画布只扩展不裁切，UI 元素尺寸恒定；两种横屏画幅的 scaleFactor 相同，"
                         "逻辑画布高度都锁 1920、宽度随画幅变宽 → HUD 不重排，只左右多出空间。"),
            }

    # ---- 7. 已定结论：每条都标证据强度，禁止把「库语义」写成「资源实证」----
    ss = out["参数"].get("spot_setting") or {}
    tp = out["参数"].get("automode_transposer") or {}
    binding_names = {0: "LockToTargetOnAssign", 1: "LockToTargetWithWorldUp", 2: "LockToTargetNoRoll",
                     3: "LockToTarget", 4: "WorldSpace", 5: "SimpleFollowWithWorldUp", 6: "Legacy"}
    bm = tp.get("m_BindingMode")
    out["结论"] = [
        {"项": "21:9 下 HUD / 准星是否重排",
         "结论": "不重排。UI 元素尺寸恒定，只左右多出逻辑空间；准星的屏幕归一化位置不变。",
         "证据": "CanvasScaler m_UiScaleMode=1(ScaleWithScreenSize) + m_ScreenMatchMode=1(Expand) "
                 "+ m_ReferenceResolution=(1080,1920)，两份 canvas 资产完全一致",
         "强度": "资源实证 + Unity 库语义", "影响": "无（出图关 HUD，查看器也不画准星）"},
        {"项": "自动战斗机位何时激活",
         "结论": "当前配置下不激活。手动战斗走 arenacamera(priority 8)。",
         "证据": "SpotSetting.UseAutoModeCamera=%s；automode vcam m_Priority=11 但 m_IsActive=false"
                 % ss.get("UseAutoModeCamera"),
         "强度": "资源实证", "影响": "无（出图与查看器都用手动机位）"},
        {"项": "m_FollowOffset (0,0,-10) 的方向语义",
         "结论": "在目标「仅含 yaw」的局部空间里后退 10 m，roll 锁世界 up。",
         "证据": "CinemachineTransposer m_BindingMode=%s → %s" % (bm, binding_names.get(bm, "?")),
         "强度": "Cinemachine 库语义（枚举定义），非二进制反编",
         "影响": "无（手动战斗不读它；仅供将来做自动机位时参考）"},
        {"项": "AimStartPosition1..5 的坐标系基准",
         "结论": "归一化偏移（值域 ±0.25 / ±0.125），但「相对全宽」还是「相对半宽」无证据区分，"
                 "故不推导世界角度。",
         "证据": "字段为 Vector2，量级不可能是像素；同文件的 AimPositionInitOffsetHeight=200 才是像素量级",
         "强度": "资源实证（量级）+ 未定（基准）",
         "影响": "无（HUD 已关；不影响机位）"},
        {"项": "运行时相机运动公式",
         "结论": "拿不到。global-metadata.dat 被剥离为 0 字节，SpotCameraControl 只有 _spotCamera/_shakes "
                 "两个序列化字段。",
         "证据": "il2cpp_data/Metadata/global-metadata.dat 大小 0",
         "强度": "已证伪（此路不通）", "影响": "俯角 12.3° 只能算「双源旁证」，不是已证事实"},
    ]
    out["参数"]["推导"] = derive
    return out


def main():
    data = build()
    txt = json.dumps(data, ensure_ascii=False, indent=1)
    if "--check" in sys.argv:
        if not os.path.exists(OUT):
            print("camera_params.json 不存在"); return 1
        old = open(OUT, encoding="utf-8").read().strip()
        if old != txt.strip():
            print("camera_params.json 与 bundle 不一致，请重跑（去掉 --check）"); return 2
        print("camera_params.json 一致 ✓"); return 0
    os.makedirs(CAM, exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(txt + "\n")
    p = data["参数"]
    print("→ %s" % OUT)
    print("  fov(纵向)=%s  near=%s  far=%s  gateFit=%s  projMode=%s"
          % (p.get("fov_vertical_deg"), p.get("near_clip"), p.get("far_clip"),
             p.get("gate_fit"), p.get("projection_matrix_mode")))
    d = p.get("推导", {})
    print("  俯角：aim 偏移反推 %s° / 选定 %s°；横向 FOV %s"
          % (d.get("pitch_from_aim_offset_deg"), d.get("chosen_pitch_deg"),
             d.get("horizontal_fov_deg")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
