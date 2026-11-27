$ErrorActionPreference = 'Stop'
function Initialize-ProjectPython {
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $env:UV_CACHE_DIR = Join-Path $projectRoot '.runtime\uv-cache'
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/'
    }
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if ($env:PROJECT_PYTHON) {
        & uv sync --locked --python $env:PROJECT_PYTHON
    } elseif (Test-Path -LiteralPath '.venv\Scripts\python.exe') {
        & uv sync --locked
    } elseif (Test-Path -LiteralPath $bundledPython) {
        & uv sync --locked --python $bundledPython
    } else {
        & uv sync --locked --python 3.12
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency setup failed.' }
}
