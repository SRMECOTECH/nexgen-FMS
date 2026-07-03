# =====================================================================
# nextGen-FMS — one-shot model downloader
#
# Drops the two local AI models the platform needs into the right folders.
# Safe to re-run: every file is checked first; nothing is re-downloaded.
#
#   models/insights/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf   (~1.0 GB)
#       Generative LLM used by route_intelligence/ai_insights.py.
#       Auto-detected by LlamaCppBackend on backend start.
#
#   models/embeddings/all-MiniLM-L6-v2/                 (~90 MB total)
#       Sentence-transformer used for insight de-dup / semantic search.
#       Auto-detected by route_intelligence/services/embeddings.py.
#
# Usage (from project root, venv activated):
#   .\scripts\download-models.ps1
# =====================================================================

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# Force TLS 1.2 — older PowerShell defaults to 1.0 which HF rejects.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Save-IfMissing([string]$url, [string]$dest) {
    if (Test-Path $dest) {
        $sizeMb = [math]::Round((Get-Item $dest).Length / 1MB, 1)
        Write-Host "    [skip] $dest already exists ($sizeMb MB)"
        return
    }
    $destDir = Split-Path -Parent $dest
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    Write-Host "    [pull] $url"
    Write-Host "       -> $dest"
    # Invoke-WebRequest streams the file. -UseBasicParsing avoids IE engine.
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    $sizeMb = [math]::Round((Get-Item $dest).Length / 1MB, 1)
    Write-Host "    [done] $sizeMb MB"
}

Write-Host "==> 1/2  Generative LLM (Qwen2.5-1.5B-Instruct, Q4_K_M GGUF)" -ForegroundColor Cyan
$ggufDir  = "models\insights"
$ggufFile = "$ggufDir\Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
Save-IfMissing `
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf" `
    $ggufFile

Write-Host ""
Write-Host "==> 2/2  Sentence-transformer (all-MiniLM-L6-v2)" -ForegroundColor Cyan
$emb = "models\embeddings\all-MiniLM-L6-v2"
$embFiles = @(
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "special_tokens_map.json",
    "sentence_bert_config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "1_Pooling/config.json",
    "pytorch_model.bin"
)
$base = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main"
foreach ($f in $embFiles) {
    Save-IfMissing "$base/$f" "$emb\$f"
}

Write-Host ""
Write-Host "Done. The backend will auto-detect both on its next start." -ForegroundColor Green
Write-Host ""
Write-Host "If you haven't yet, install the runtime libs once:" -ForegroundColor Yellow
Write-Host "    .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "    pip install llama-cpp-python sentence-transformers" -ForegroundColor Yellow
Write-Host ""
Write-Host "Then restart the backend:" -ForegroundColor Yellow
Write-Host "    python -m backend.app.main" -ForegroundColor Yellow
