param(
    [string]$BenchmarkJson = "reports/benchmark.json",
    [string]$ProfileOutput = "reports/profile.out"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$reports = Join-Path $root "reports"
New-Item -ItemType Directory -Force -Path $reports | Out-Null

Set-Location (Join-Path $root "backend")
Write-Host "==> pytest-benchmark micro benchmarks"
python -m pytest benchmarks/test_benchmark.py --benchmark-only --benchmark-json (Join-Path $root $BenchmarkJson)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> cProfile sampling"
python -m cProfile -o (Join-Path $root $ProfileOutput) scripts/profile_sanitize.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Benchmark JSON: $(Join-Path $root $BenchmarkJson)"
Write-Host "cProfile file: $(Join-Path $root $ProfileOutput)"
Write-Host "View profile with: python -m pstats $(Join-Path $root $ProfileOutput)"
