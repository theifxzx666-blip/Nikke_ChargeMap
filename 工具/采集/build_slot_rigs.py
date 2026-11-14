# -*- coding: utf-8 -*-
"""把「真实相机机位」写进每个场景的 mesh/slots.json。

背景（2026-11-14 实测）：
  场景里的 cover_N.camera_position 只是美术摆的**机架锚点**，不是相机。
  真实相机来自 spotcharactermap 包的 SpotCharacterMap 模板：

    SpotCharacterMap
      └─ CoverPostion
           └─ Cover_N            local 与场景 cover_N 世界坐标同值（108/112 场景一致）
                └─ CameraN      local 各不相同 + ±2°/±4° 偏航（朝画面中心收敛）
                     └─ ShakeTransform
                          ├─ AimCamera   local ( 0.5,   -0.3,   0    )
                          └─ HideCamera  local ( 0.0,   -0.164, -0.477)

  所以  camera_aim  = cover.root + (CameraN.local + AimCamera.local)  * cover.scale
        camera_hide = cover.root + (CameraN.local + HideCamera.local) * cover.scale
        yaw         = cover.root_yaw + CameraN.yaw        （pitch 恒 0）
        FOV 60 / near 0.1 / far 250（vcam m_Lens，10 台一致）

  参数全部读 工具/参数真源.json，本脚本不写死任何数值。

用法：
  python build_slot_rigs.py            # 重建全部场景
  python build_slot_rigs.py --check    # 只比对，不写盘
  python build_slot_rigs.py 001 tw003  # 只处理指定场景
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH                                       # noqa: E402

PARAM = os.path.join(ROOT, "工具", "参数真源.json")
RIG_KEY = ("camera_aim", "camera_hide")


def load_rig():
    d = json.load(open(PARAM, encoding="utf-8"))
    rig = (d.get("camera") or {}).get("rig") or {}
    slots = rig.get("slot_cameras") or {}
    aim = rig.get("aim_camera_local")
    hide = rig.get("hide_camera_local")
    if not slots or aim is None or hide is None:
        raise SystemExit("参数真源缺 camera.rig.slot_cameras / aim_camera_local / hide_camera_local")
    missing = [k for k in ("cover_1", "cover_2", "cover_3", "cover_4", "cover_5") if k not in slots]
    if missing:
        raise SystemExit("参数真源缺阵位：%s" % missing)
    return slots, aim, hide, rig.get("pitch_deg", 0.0)


def rig_for(entry, cam_local, cam_yaw, off, pitch, k):
    """算出该阵位某一台相机（aim 或 hide）的世界位姿。

    local 偏移要乘 cover 根的 scale —— Unity 里父级缩放会作用到子物体的 localPosition。
    """
    root = entry.get("root") or [0, 0, 0]
    sc = entry.get("root_scale") or [1, 1, 1]
    s = sc[0] if sc else 1.0
    yaw0 = entry.get("root_yaw", 0.0) or 0.0
    pos = [round(root[i] + (cam_local[i] + off[i]) * s, 4) for i in range(3)]
    yaw = round((yaw0 + cam_yaw + 180.0) % 360.0 - 180.0, 3)
    return {"pos": pos, "yaw": yaw, "pitch": round(pitch, 3), "scale": round(s, 4), "slot": k}


def main(argv):
    check = "--check" in argv
    only = [a for a in argv if not a.startswith("-")]

    slot_cams, aim_off, hide_off, pitch = load_rig()
    reg = json.load(open(os.path.join(ROOT, "资源库", "场景库", "registry.json"), encoding="utf-8"))["scenes"]

    changed = same = skipped = 0
    drift = []
    for arena in sorted(reg):
        if only and arena not in only:
            continue
        r = reg[arena]
        path = PATH.slots_path(arena)
        if not os.path.exists(path):
            skipped += 1
            continue
        raw = json.load(open(path, encoding="utf-8"))
        block = raw.get(arena) or {}
        if not block:
            skipped += 1
            continue

        touched = False
        for k in sorted(block):
            if k not in slot_cams:
                continue
            e = block[k]
            caml = slot_cams[k]["local"]
            camy = slot_cams[k]["yaw"]
            aim = rig_for(e, caml, camy, aim_off, pitch, k)
            hide = rig_for(e, caml, camy, hide_off, pitch, k)
            if e.get("camera_aim") != aim or e.get("camera_hide") != hide:
                e["camera_aim"] = aim
                e["camera_hide"] = hide
                touched = True
            # 旧锚点保留但标记，避免后人再拿它当相机
            if e.get("camera_position") and e.get("anchor_note") != "机架锚点，非相机；相机见 camera_aim":
                e["anchor_note"] = "机架锚点，非相机；相机见 camera_aim"
                touched = True
            # 记差异，便于人工核对
            old = e.get("cam")
            if old:
                d = [round(aim["pos"][i] - old[i], 3) for i in range(3)]
                if max(abs(x) for x in d) > 0.2:
                    drift.append((arena, k, tuple(d)))
        if touched:
            changed += 1
            if not check:
                PATH.write_json(raw, path)
        else:
            same += 1

    print("场景 %d｜写入 %d｜已是最新 %d｜无 slots 跳过 %d%s"
          % (len(reg), changed, same, skipped, "（--check 未写盘）" if check else ""))
    if drift:
        print("与旧锚点相差 >0.2m 的阵位 %d 个（前 10）：" % len(drift))
        for a, k, d in drift[:10]:
            print("  %-14s %-8s Δ=%s" % (a, k, d))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
