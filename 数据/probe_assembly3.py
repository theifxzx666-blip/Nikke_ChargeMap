# -*- coding: utf-8 -*-
"""场景级装配参数: SpotBG / SpotSky / SpotSingleMap / 全部 Material / sprite 引用可解析性"""
import UnityPy, collections, json

P = r"原始bundle/sbg/sbg_swamplandjungle_001.bundle"
env = UnityPy.load(P)
objs = list(env.objects)

script_name = {}
for o in objs:
    if o.type.name == "MonoScript":
        d = o.read()
        script_name[o.path_id] = getattr(d, "m_ClassName", None) or "?"

SKIP = {"m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance",
        "m_PrefabAsset", "m_GameObject", "m_Enabled", "m_EditorHideFlags",
        "m_Script", "m_Name", "m_EditorClassIdentifier"}

def dump(tt, indent="    ", maxdepth=3, depth=0):
    for k, v in tt.items():
        if k in SKIP:
            continue
        s = json.dumps(v, ensure_ascii=False)
        if len(s) > 260:
            s = s[:260] + "…"
        print(indent + k + " = " + s)

for o in objs:
    if o.type.name != "MonoBehaviour":
        continue
    tt = o.read_typetree()
    sn = script_name.get(tt.get("m_Script", {}).get("m_PathID", 0), "?")
    if sn in ("SpotBG", "SpotSky", "SpotSingleMap", "NKSpotCoverManager", "SpotNotCombatZone"):
        print("=" * 70)
        print("### " + sn)
        dump(tt)

print()
print("=" * 70)
print("### 全部 Material")
tex_names = {}
for o in objs:
    if o.type.name == "Texture2D":
        tex_names[o.path_id] = o.read_typetree().get("m_Name", "")
spr = {}
for o in objs:
    if o.type.name == "Sprite":
        tt = o.read_typetree()
        spr[o.path_id] = (tt.get("m_Name", ""), tt.get("m_RD", {}).get("texture", {}).get("m_PathID", 0))

def pname(x):
    return (x.get("name") or x.get("Name")) if isinstance(x, dict) else x

for o in objs:
    if o.type.name != "Material":
        continue
    tt = o.read_typetree()
    sp = tt.get("m_SavedProperties", {}) or {}
    print(" - %-28s shader=%s" % (tt.get("m_Name"), tt.get("m_Shader", {}).get("m_PathID")))
    for key in ("m_TexEnvs", "m_Floats", "m_Colors", "m_Ints"):
        for it in (sp.get(key) or []):
            if isinstance(it, (list, tuple)) and len(it) == 2:
                k, v = it
            elif isinstance(it, dict):
                k, v = it.get("first"), it.get("second")
            else:
                continue
            k = pname(k)
            if key == "m_TexEnvs":
                tx = (v or {}).get("m_Texture", {}).get("m_PathID", 0)
                if tx:
                    print("     tex %-22s -> %-46s (%s)" % (k, tex_names.get(tx, tx),
                          spr.get(tx, ("",))[0]))
            elif key == "m_Colors":
                print("     col %-22s %s" % (k, {kk: round(vv, 4) for kk, vv in (v or {}).items() if isinstance(vv, float)}))
            elif key == "m_Floats":
                if k in ("_FogDensity", "_FogGradient", "_AlphaClip", "_Blend", "_Cull",
                         "_Cutoff", "_QueueOffset", "_QueueControl", "_ZWrite", "_ColorMask"):
                    print("     flt %-22s %s" % (k, v))

print()
print("=" * 70)
print("### RuntimeTextureInstanceSetter._sprite 可解析率")
spr_ids = set(spr.keys())
tex_ids = set(tex_names.keys())
tot = ok_s = ok_t = 0
for o in objs:
    if o.type.name != "MonoBehaviour":
        continue
    tt = o.read_typetree()
    if script_name.get(tt.get("m_Script", {}).get("m_PathID", 0)) != "RuntimeTextureInstanceSetter":
        continue
    tot += 1
    sid = tt.get("_sprite", {}).get("m_PathID", 0)
    if sid in spr_ids:
        ok_s += 1
        if spr[sid][1] in tex_ids:
            ok_t += 1
print("  setter 总数=%d  指向 Sprite=%d  再指向 Texture2D=%d" % (tot, ok_s, ok_t))
print("  Sprite 数=%d  Texture2D 数=%d" % (len(spr_ids), len(tex_ids)))

# 抽样 5 个 setter 的 sprite 名与 texture 名
n = 0
for o in objs:
    if o.type.name != "MonoBehaviour":
        continue
    tt = o.read_typetree()
    if script_name.get(tt.get("m_Script", {}).get("m_PathID", 0)) != "RuntimeTextureInstanceSetter":
        continue
    go = tt.get("m_GameObject", {}).get("m_PathID", 0)
    sid = tt.get("_sprite", {}).get("m_PathID", 0)
    sn, tid = spr.get(sid, ("?", 0))
    print("  GO=%-46s sprite=%-46s tex=%s" % (go, sn, tex_names.get(tid, tid)))
    n += 1
    if n >= 5:
        break
