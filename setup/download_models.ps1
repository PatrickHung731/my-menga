# MangaStudio model downloader (resume-capable, pure ASCII)
# Downloads manga-pipeline models into D:\LocalAI\ComfyUI\models
$ErrorActionPreference = 'Continue'
$M = 'D:\LocalAI\ComfyUI\models'
New-Item -ItemType Directory -Force "$M\ipadapter" | Out-Null

$files = @(
    @{ url = 'https://huggingface.co/cagliostrolab/animagine-xl-4.0/resolve/main/animagine-xl-4.0.safetensors';
       out = "$M\checkpoints\animagine-xl-4.0.safetensors" },
    @{ url = 'https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors';
       out = "$M\clip_vision\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors" },
    @{ url = 'https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors';
       out = "$M\ipadapter\ip-adapter-plus-face_sdxl_vit-h.safetensors" },
    @{ url = 'https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors';
       out = "$M\ipadapter\ip-adapter-plus_sdxl_vit-h.safetensors" },
    @{ url = 'https://huggingface.co/xinsir/controlnet-union-sdxl-1.0/resolve/main/diffusion_pytorch_model_promax.safetensors';
       out = "$M\controlnet\controlnet-union-sdxl-promax.safetensors" }
)

foreach ($f in $files) {
    $name = Split-Path $f.out -Leaf
    Write-Output "=== Downloading: $name"
    & curl.exe -L -C - --retry 5 --retry-delay 5 -o $f.out $f.url
    if ($LASTEXITCODE -ne 0) { Write-Output "FAILED: $name (exit $LASTEXITCODE)" }
    else { Write-Output "DONE: $name" }
}
Write-Output "=== ALL DOWNLOADS FINISHED ==="
