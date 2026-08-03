$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Set-Location (Join-Path $root "backend")
Write-Host "==> ruff"
python -m ruff check app tests scripts benchmarks alembic/env.py

Write-Host "==> mypy"
python -m mypy --config-file mypy.ini

Write-Host "==> bandit"
bandit -r app -q -ll

Write-Host "==> pip-audit"
python -m pip_audit -r requirements.txt --progress-spinner off --ignore-vuln PYSEC-2026-1325

Set-Location (Join-Path $root "frontend")
Write-Host "==> eslint"
npm run lint

Write-Host "==> typecheck"
npm run typecheck

Write-Host "All static checks passed."
