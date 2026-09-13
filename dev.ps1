# Start the API, the worker and the interface on Windows. Run from the repository root:
#
#   powershell -ExecutionPolicy Bypass -File dev.ps1
#
# The API takes the first free port from 8000 up, so another project already on
# 8000 does not get in the way; the interface is pointed at whichever port it got.
# The API and worker open in their own windows; close them (or Ctrl-C) to stop.
param([int]$ApiPort = 8000)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) { throw "No backend\.venv. See docs\development.md (Setup)." }
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) { throw "No frontend\node_modules. Run: cd frontend; npm install" }
if (-not (Test-Path (Join-Path $root 'demo\seed'))) {
    Write-Host 'Generating the demo roster...'
    node (Join-Path $root 'demo\gen_seed.js') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Generating the demo roster failed. Is Node installed?' }
}
if (-not (Test-Path (Join-Path $backend '.env'))) {
    Copy-Item (Join-Path $backend '.env.example') (Join-Path $backend '.env')
    Write-Host 'Created backend\.env from .env.example.'
}

# The demo data is built for this date; backend\.env or the environment can override it.
if (-not $env:HR_TODAY) { $env:HR_TODAY = '2026-09-12' }
if ($null -eq $env:HR_MODULES) { $env:HR_MODULES = 'all' }

while (Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue) { $ApiPort++ }
$env:HR_API_URL = "http://127.0.0.1:$ApiPort"

# Windows PowerShell turns anything a program writes to stderr (Alembic's progress
# messages, for one) into an error, so native commands are judged by exit code only.
function Invoke-Native([string]$What) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $args[0] $args[1..($args.Count - 1)] 2>$null | Out-Null } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

Push-Location $backend
try {
    if (-not (Test-Path 'halverson.db')) { Write-Host 'No database yet: seeding the demo...'; Invoke-Native 'Seeding the demo' $python seed.py }
    Invoke-Native 'Database migration (backend\.venv\Scripts\alembic upgrade head)' $python -m alembic upgrade head
} finally { Pop-Location }

# The agents need Ollama and a tool-capable model. Not fatal: everything else works without it.
$model = (Select-String -Path (Join-Path $backend '.env') -Pattern '^HR_OLLAMA_MODEL=(.+)$' |
          Select-Object -First 1).Matches.Groups[1].Value
try {
    $installed = (Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 2).models.name
    if ($model -and $installed -notcontains $model) {
        Write-Host "  note: Ollama does not have $model. Pull it, or set HR_OLLAMA_MODEL in backend\.env to one of: $($installed -join ', ')" -ForegroundColor Yellow
    }
} catch {
    Write-Host '  note: Ollama is not running, so the AI agents are unavailable. Everything else works.' -ForegroundColor Yellow
}

$envLine = "`$env:HR_TODAY='$env:HR_TODAY'; `$env:HR_MODULES='$env:HR_MODULES'"
Start-Process powershell -WorkingDirectory $backend -ArgumentList '-NoExit', '-Command',
    "$envLine; `$host.UI.RawUI.WindowTitle='API port $ApiPort'; & '$python' -m uvicorn app.main:app --reload --port $ApiPort"
Start-Process powershell -WorkingDirectory $backend -ArgumentList '-NoExit', '-Command',
    "$envLine; `$host.UI.RawUI.WindowTitle='Worker'; & '$python' -m app.worker"

Write-Host ''
Write-Host "  API        http://localhost:$ApiPort/api/health   (docs: /docs)"
Write-Host '  Interface  the Local address Vite prints below (normally http://localhost:5174)'
Write-Host '  Sign in    counselor@halverson.example.edu / halverson-demo-2026'
Write-Host ''
Push-Location $frontend
try { npm run dev } finally { Pop-Location }
