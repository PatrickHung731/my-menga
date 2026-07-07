# -*- coding: utf-8 -*-
r"""F5-TTS 批次克隆配音（在 D:\LocalAI\f5tts_venv 跑，不是 ComfyUI venv）。

讀 job.json = {"ref_audio": "...", "ref_text": "", "sentences": [...], "out_dir": "..."}
→ 載入模型一次 → 逐句克隆 → out_dir\0000.wav, 0001.wav ...

由 narrate.py --engine f5 透過 subprocess 呼叫。
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

from f5_tts.api import F5TTS
from f5_tts.infer.utils_infer import preprocess_ref_audio_text


def main():
    job = json.loads(open(sys.argv[1], encoding="utf-8").read())
    ref_audio = job["ref_audio"]
    ref_text = job.get("ref_text", "") or ""
    sentences = job["sentences"]
    out_dir = job["out_dir"]
    speed = float(job.get("speed", 1.0))
    nfe = int(job.get("nfe_step", 32))
    os.makedirs(out_dir, exist_ok=True)

    print("[F5] 載入模型 ...", flush=True)
    f5 = F5TTS(model="F5TTS_v1_Base")

    # 參考音檔轉錄一次（之後每句沿用，省時間）
    ref_audio, ref_text = preprocess_ref_audio_text(ref_audio, ref_text)
    print("[F5] 參考文字：%s" % ref_text[:60], flush=True)

    for i, s in enumerate(sentences):
        out = os.path.join(out_dir, "%04d.wav" % i)
        try:
            f5.infer(ref_file=ref_audio, ref_text=ref_text, gen_text=s,
                     file_wave=out, speed=speed, nfe_step=nfe,
                     remove_silence=False, show_info=lambda *a, **k: None)
            print("[F5] %d/%d ok" % (i + 1, len(sentences)), flush=True)
        except Exception as e:
            print("[F5] %d FAILED: %s" % (i, str(e)[:200]), flush=True)
    print("[F5] DONE", flush=True)


if __name__ == "__main__":
    main()
