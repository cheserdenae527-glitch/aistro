$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Set-Location (Join-Path $root "backend")
Write-Host "==> ruff"
python -m ruff check app tests scripts benchmarks alembic/env.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> mypy"
python -m mypy --config-file mypy.ini
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> bandit"
bandit -r app -q -ll
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> pip-audit"
python -m pip_audit -r requirements.txt --progress-spinner off --ignore-vuln PYSEC-2026-1325
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $root "frontend")
Write-Host "==> eslint"
npm run lint
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> typecheck"
npm run typecheck
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "All static checks passed."
