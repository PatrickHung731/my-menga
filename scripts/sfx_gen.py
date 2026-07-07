# -*- coding: utf-8 -*-
r"""本機 AI 生音效（在 D:\LocalAI\sfx_venv 跑）。用 AudioLDM2 依英文描述生音效 wav。

讀 job.json = {"sfx": ["rain sound", "alarm siren", ...], "out_dir": "...", "len": 4.0}
→ out_dir\0000.wav, 0001.wav ...（16kHz 單聲道）

由 narrate.py 透過 subprocess 呼叫。第一次會下載 AudioLDM2 模型（約 1.5GB）。
"""
import json
import os
import sys

os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import torch
import soundfile as sf
from diffusers import AudioLDM2Pipeline


def main():
    job = json.loads(open(sys.argv[1], encoding="utf-8").read())
    sfx = job["sfx"]
    out_dir = job["out_dir"]
    length = float(job.get("len", 4.0))
    steps = int(job.get("steps", 120))
    os.makedirs(out_dir, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    print("[SFX] 載入 AudioLDM2（%s）..." % device, flush=True)
    pipe = AudioLDM2Pipeline.from_pretrained("cvssp/audioldm2", torch_dtype=dtype)
    pipe = pipe.to(device)
    try:
        pipe.enable_attention_slicing()
    except Exception:
        pass

    neg = "low quality, noise, distortion, music, speech, talking"
    gen = torch.Generator(device).manual_seed(0)
    for i, prompt in enumerate(sfx):
        try:
            audio = pipe(prompt, negative_prompt=neg, num_inference_steps=steps,
                         audio_length_in_s=length, generator=gen).audios[0]
            sf.write(os.path.join(out_dir, "%04d.wav" % i), audio, 16000)
            print("[SFX] %d/%d ok：%s" % (i + 1, len(sfx), prompt[:40]), flush=True)
        except Exception as e:
            print("[SFX] %d FAILED: %s" % (i, str(e)[:200]), flush=True)
    print("[SFX] DONE", flush=True)


if __name__ == "__main__":
    main()
