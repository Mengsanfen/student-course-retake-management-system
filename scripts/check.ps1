param([ValidateSet('sqlite','mysql','both')][string]$Database = 'sqlite')
. (Join-Path $PSScriptRoot 'environment.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $projectRoot 'backend')
try {
    Initialize-ProjectPython
    $testTemp = [IO.Path]::GetFullPath((Join-Path $projectRoot '.runtime\pytest-fastapi-tmp'))
    $testCache = [IO.Path]::GetFullPath((Join-Path $projectRoot '.runtime\pytest-cache'))
    if (-not $testTemp.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Test temporary directory escaped the project.'
    }
    $databases = if ($Database -eq 'both') { @('sqlite','mysql') } else { @($Database) }
    foreach ($databaseName in $databases) {
        $reportName = if ($databaseName -eq 'sqlite') { 'pytest-fastapi.xml' } else { 'pytest-mysql.xml' }
        & uv run --locked pytest -q --database $databaseName "--junitxml=../.runtime/$reportName" -o "cache_dir=$testCache" "--basetemp=$testTemp"
        if ($LASTEXITCODE -ne 0) { throw "Backend tests failed on $databaseName." }
    }
} finally { Pop-Location }
Push-Location (Join-Path $projectRoot 'frontend')
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        & npm ci --cache ../.runtime/npm-cache --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend type check or build failed.' }
} finally { Pop-Location }
