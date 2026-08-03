param(
    [switch]$SkipE2E,
    [switch]$Coverage
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Set-Location (Join-Path $root "backend")
Write-Host "==> Backend pytest"
if ($Coverage) {
    python -m pytest --cov=app --cov-report=term-missing
} else {
    python -m pytest
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $root "frontend")
Write-Host "==> Frontend vitest"
if ($Coverage) {
    npm test -- --coverage
} else {
    npm test
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipE2E) {
    Write-Host "==> Playwright E2E"
    npm run e2e
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "All tests passed."
