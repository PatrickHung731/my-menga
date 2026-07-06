# -*- coding: utf-8 -*-
"""組 ComfyUI API-format 節點圖：SDXL(Animagine) + 可選 IP-Adapter 鎖臉 + 可選 ControlNet 姿勢。"""
import math

CKPT = "animagine-xl-4.0.safetensors"
IPADAPTER_FACE = "ip-adapter-plus-face_sdxl_vit-h.safetensors"
IPADAPTER_FULL = "ip-adapter-plus_sdxl_vit-h.safetensors"
CLIP_VISION = "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
CONTROLNET_UNION = "controlnet-union-sdxl-promax.safetensors"

# Animagine XL 4.0 官方建議
QUALITY_TAGS = "masterpiece, high score, great score, absurdres"
NEG_DEFAULT = ("lowres, bad anatomy, bad hands, text, error, missing fingers, "
               "extra digit, fewer digits, cropped, worst quality, low quality, "
               "low score, bad score, average score, signature, watermark, "
               "username, blurry")
BW_TAGS = "monochrome, greyscale, screentone"

# 內容分級 → 追加負面詞（safe=全擋；r15=允許血腥/輕度性感，仍擋裸露與性行為）
RATING_NEG = {
    "safe": "nude, blood, gore",
    "r15": "sex, pussy, penis",
}

# 風格預設（storyboard 的 "style" 欄位）
STYLE_PRESETS = {
    # ── 經典少年漫畫 ──
    "shonen_90s":    "1990s (style), retro artstyle",                          # 通用九零年代少年漫
    "dragon_ball":   "toriyama akira (style), 1980s (style), retro artstyle",  # 七龍珠
    "one_piece":     "oda eiichirou (style)",                                  # 海賊王
    "yuyu_hakusho":  "togashi yoshihiro (style), 1990s (style), retro artstyle",  # 幽遊白書
    "slam_dunk":     "inoue takehiko (style), 1990s (style), retro artstyle",  # 灌籃高手
    "naruto":        "kishimoto masashi (style)",                              # 火影忍者
    "video_girl_ai": "katsura masakazu (style), 1990s (style), retro artstyle",  # 電影少女
    "kungfu_boy":    "1980s (style), retro artstyle, martial arts",            # 鐵拳對鋼拳
    # ── 經典作家風 ──
    "jojo":          "araki hirohiko (style), jojo no kimyou na bouken, muscular, dramatic pose",  # JOJO
    "clamp":         "clamp (style), detailed lineart, flowing clothes, elegant",  # CLAMP
    "rumiko":        "takahashi rumiko (style), 1980s (style), retro artstyle",  # 高橋留美子
    "bleach":        "kubo tite (style), sharp lines, high contrast",          # BLEACH 死神
    "aot":           "isayama hajime (style), dark atmosphere, intense shading",  # 進擊的巨人
    "chainsaw":      "fujimoto tatsuki (style), dark, dynamic angle",          # 鏈鋸人
    # ── 少女漫畫 ──
    "shoujo":        "shoujo manga, sparkle, flower background, large eyes, screentone",  # 少女漫畫
    # ── 現代動畫/電影風 ──
    "modern_anime":  "",                                                       # 現代動畫（Animagine 預設）
    "shinkai":       "shinkai makoto (style), lens flare, sunlight, detailed sky, scenery",  # 新海誠
    "ghibli":        "ghibli (style), studio ghibli, miyazaki hayao, watercolor, soft lighting",  # 吉卜力
    # ── 海外風格 ──
    "marvel":        "marvel comics, american comics (style), muscular, realistic, dark colors, cel shading",  # 美漫
    "webtoon":       "korean webtoon, clean lines, soft shading, modern",      # 韓漫 Webtoon
    "disney_3d":     "3d, pixar (style), cartoon, cute, colorful, soft lighting, round features",  # 迪士尼/皮克斯
}


# SDXL 友善解析度（w, h）
SDXL_SIZES = [(1024, 1024), (896, 1152), (832, 1216), (768, 1344),
              (1152, 896), (1216, 832), (1344, 768)]


def pick_size(aspect_ratio):
    """挑最接近目標長寬比的 SDXL 解析度。"""
    return min(SDXL_SIZES, key=lambda s: abs(math.log((s[0] / float(s[1])) / aspect_ratio)))


def build_positive(panel_prompt, char_tag_list, style_key, extra_style_tags, color):
    parts = []
    for t in char_tag_list:
        t = t.strip().strip(",")
        if t:
            parts.append(t)
    parts.append(panel_prompt.strip().strip(","))
    style = STYLE_PRESETS.get(style_key, "")
    if style:
        parts.append(style)
    if extra_style_tags:
        parts.append(extra_style_tags.strip().strip(","))
    if not color:
        parts.append(BW_TAGS)
    parts.append(QUALITY_TAGS)
    return ", ".join(p for p in parts if p)


def build_graph(positive, negative, width, height, seed,
                char_refs=None, ref_weight=0.75, face_only=True,
                pose_image=None, pose_is_skeleton=False, pose_strength=0.85,
                steps=26, cfg=5.5, filename_prefix="mangastudio"):
    """回傳 ComfyUI /prompt 用的 graph dict。

    char_refs: ComfyUI input 內的參考圖檔名 list（先用 comfy_client.upload_image 上傳）。
    pose_image: ComfyUI input 內的姿勢參考圖檔名；pose_is_skeleton=True 表示已是骨架圖。
    """
    g = {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": positive, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
    }
    model = ["1", 0]
    pos = ["2", 0]
    neg = ["3", 0]

    # --- IP-Adapter：每個角色參考圖串一層 ---
    if char_refs:
        ipa_model = IPADAPTER_FACE if face_only else IPADAPTER_FULL
        g["10"] = {"class_type": "IPAdapterModelLoader",
                   "inputs": {"ipadapter_file": ipa_model}}
        g["11"] = {"class_type": "CLIPVisionLoader",
                   "inputs": {"clip_name": CLIP_VISION}}
        # 多角色同格時各自權重打折，避免互相污染
        w = ref_weight if len(char_refs) == 1 else min(ref_weight, 0.55)
        for i, ref in enumerate(char_refs):
            load_id = str(20 + i * 2)
            apply_id = str(21 + i * 2)
            g[load_id] = {"class_type": "LoadImage", "inputs": {"image": ref}}
            g[apply_id] = {"class_type": "IPAdapterAdvanced",
                           "inputs": {
                               "model": model,
                               "ipadapter": ["10", 0],
                               "image": [load_id, 0],
                               "clip_vision": ["11", 0],
                               "weight": w,
                               "weight_type": "linear",
                               "combine_embeds": "concat",
                               "start_at": 0.0,
                               "end_at": 1.0,
                               "embeds_scaling": "V only",
                           }}
            model = [apply_id, 0]

    # --- ControlNet(Union) OpenPose：鎖動作 ---
    if pose_image:
        g["40"] = {"class_type": "ControlNetLoader",
                   "inputs": {"control_net_name": CONTROLNET_UNION}}
        g["41"] = {"class_type": "SetUnionControlNetType",
                   "inputs": {"control_net": ["40", 0], "type": "openpose"}}
        g["42"] = {"class_type": "LoadImage", "inputs": {"image": pose_image}}
        cn_image = ["42", 0]
        if not pose_is_skeleton:
            g["43"] = {"class_type": "OpenposePreprocessor",
                       "inputs": {"image": ["42", 0],
                                  "detect_hand": "enable",
                                  "detect_body": "enable",
                                  "detect_face": "enable",
                                  "resolution": 512,
                                  "scale_stick_for_xinsir_cn": "disable"}}
            cn_image = ["43", 0]
        g["44"] = {"class_type": "ControlNetApplyAdvanced",
                   "inputs": {"positive": pos, "negative": neg,
                              "control_net": ["41", 0], "image": cn_image,
                              "strength": pose_strength,
                              "start_percent": 0.0, "end_percent": 0.85,
                              "vae": ["1", 2]}}
        pos = ["44", 0]
        neg = ["44", 1]

    g["50"] = {"class_type": "KSampler",
               "inputs": {"model": model, "positive": pos, "negative": neg,
                          "latent_image": ["4", 0], "seed": seed,
                          "steps": steps, "cfg": cfg,
                          "sampler_name": "euler_ancestral",
                          "scheduler": "normal", "denoise": 1.0}}
    g["51"] = {"class_type": "VAEDecode",
               "inputs": {"samples": ["50", 0], "vae": ["1", 2]}}
    g["52"] = {"class_type": "SaveImage",
               "inputs": {"images": ["51", 0], "filename_prefix": filename_prefix}}
    return g
