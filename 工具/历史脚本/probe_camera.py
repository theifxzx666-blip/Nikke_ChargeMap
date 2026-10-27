# -*- coding: utf-8 -*-
"""读取战场相机装配：Camera 组件 + Transform + 相机控制脚本字段"""
import UnityPy, json, glob, math

def dump_camera(path):
    env = UnityPy.load(path)
    objs = list(env.objects)
    sn = {}
    for o in objs:
        if o.type.name == "MonoScript":
            d = o.read()
            sn[o.path_id] = getattr(d, "m_ClassName", None) or "?"
    print("=" * 78)
    print("### " + path.split("\\")[-1][:78])
    print("脚本:", sorted(set(sn.values())))

    for o in objs:
        if o.type.name == "Camera":
            tt = o.read_typetree()
            print("\n--- Camera 组件 ---")
            keys = ["orthographic", "orthographic size", "field of view", "near clip plane",
                    "far clip plane", "depth", "culling mask", "clear flags",
                    "background color", "projection matrix mode", "allow HDR", "allow MSAA"]
            for k, v in tt.items():
                lk = k.lower()
                if any(t in lk for t in ("field of view", "clip", "orthographic", "depth",
                                         "culling", "clear", "background", "projection",
                                         "hdr", "msaa", "aspect")):
                    print("   %-28s %s" % (k, json.dumps(v, ensure_ascii=False)[:160]))

    for o in objs:
        if o.type.name == "Transform":
            tt = o.read_typetree()
            print("\n--- Transform ---")
            for k in ("m_LocalPosition", "m_LocalRotation", "m_LocalScale", "m_LocalEulerAnglesHint"):
                if k in tt:
                    print("   %-24s %s" % (k, json.dumps(tt[k], ensure_ascii=False)))

    for o in objs:
        if o.type.name != "MonoBehaviour":
            continue
        tt = o.read_typetree()
        nm = sn.get(tt.get("m_Script", {}).get("m_PathID", 0), "?")
        fields = {k: v for k, v in tt.items()
                  if not k.startswith("m_") or k in ("m_Name",)}
        if not fields:
            continue
        print("\n--- %s ---" % nm)
        for k, v in fields.items():
            s = json.dumps(v, ensure_ascii=False)
            print("   %-26s %s" % (k, s[:220] + ("…" if len(s) > 220 else "")))

for p in glob.glob(r"原始bundle\camera\spotpresentation*.bundle"):
    dump_camera(p)
for p in glob.glob(r"原始bundle\camera\fieldetc-camera*.bundle"):
    dump_camera(p)
