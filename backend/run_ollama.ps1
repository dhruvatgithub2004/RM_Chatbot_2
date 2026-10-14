$ErrorActionPreference = "Stop"
$ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"

if (-not (Test-Path $ollama)) {
    throw "Ollama was not found at $ollama. Install Ollama, then run this script again."
}

$env:OLLAMA_HOST = "127.0.0.1:11435"
$env:OLLAMA_CONTEXT_LENGTH = "8192"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_KEEP_ALIVE = "30m"
$env:OLLAMA_MODELS = Join-Path $env:USERPROFILE ".ollama\models"

& $ollama serve
