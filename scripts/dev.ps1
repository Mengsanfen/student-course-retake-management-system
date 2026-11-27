param([ValidateSet('backend','frontend')][string]$Target = 'backend')
. (Join-Path $PSScriptRoot 'environment.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $projectRoot $Target)
try {
    if ($Target -eq 'backend') {
        Initialize-ProjectPython
        $env:DEMO_MODE = 'true'
        & uv run --locked python -m app.manage upgrade
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
        & uv run --locked python -m app.manage seed-demo
        if ($LASTEXITCODE -ne 0) { throw 'Demo data initialization failed.' }
        & uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8080
        if ($LASTEXITCODE -ne 0) { throw 'Backend failed. See the error above.' }
    } else {
        if (-not (Test-Path -LiteralPath 'node_modules')) {
            & npm ci --cache ../.runtime/npm-cache --no-fund --no-audit
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        }
        & npm run dev
        if ($LASTEXITCODE -ne 0) { throw 'Frontend failed. See the error above.' }
    }
} finally { Pop-Location }
