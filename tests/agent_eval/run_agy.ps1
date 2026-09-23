# Validate pdf-translate-zh with Antigravity CLI (agy) + Gemini 3.8 Flash (medium). ASCII-only on purpose.
# Other model: set $env:AGY_MODEL (e.g. gemini-3.8-flash-high) before running.
# Usage (inside a workspace made by make_workspace.py):  powershell -ExecutionPolicy Bypass -File .\run_agy.ps1
$ErrorActionPreference = "Continue"
$W = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $W
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
Remove-Item -ErrorAction SilentlyContinue DONE, NO_AGY, run.log
function Log($m) { $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m; Write-Host $line; Add-Content -Path run.log -Value $line -Encoding UTF8 }

$agy = Get-Command agy -ErrorAction SilentlyContinue
if (-not $agy) {
    Log "agy (Antigravity CLI) not found on PATH."
    Log "Fallback: open this folder in the Antigravity IDE, pick 'Gemini 3.8 Flash' with Medium thinking,"
    Log "paste the content of PROMPT.md into the agent panel, wait until it finishes, then run:  py -3 grade.py"
    Set-Content -Path NO_AGY -Value "no agy"
    exit 2
}
Log ("agy: " + $agy.Source)
Log ("version: " + ((& agy --version 2>&1) | Out-String).Trim())
$models = (& agy models 2>&1 | Out-String)
Set-Content -Path models.txt -Value $models -Encoding UTF8
$cands = @([regex]::Matches($models, 'gemini-3\.8-flash[\w\.\-]*') | ForEach-Object { $_.Value } | Select-Object -Unique)
Log ("flash candidates: " + ($cands -join ", "))
$slug = if ($env:AGY_MODEL) { $env:AGY_MODEL } else { $cands | Where-Object { $_ -match 'medium' } | Select-Object -First 1 }
$effort = @()
if (-not $slug) {
    $slug = $cands | Where-Object { $_ -eq 'gemini-3.8-flash' } | Select-Object -First 1
    if (-not $slug -and $cands.Count -gt 0) { $slug = $cands[0] }
    if (-not $slug) { $slug = "gemini-3.8-flash" }
    $effort = @("--effort", "medium")
}
Log ("model: $slug  " + ($effort -join " "))
Set-Content -Path model_used.txt -Value ("$slug " + ($effort -join " ")) -Encoding UTF8

$prompt = Get-Content -Path PROMPT.md -Raw -Encoding UTF8
$t0 = Get-Date
Log "running agy headless (this can take 10-40 minutes)..."
# no pipe/redirect: agy -p is known to hang or drop stdout without a real console (non-TTY)
& agy -p $prompt --model $slug @effort --dangerously-skip-permissions --print-timeout 120m
Log ("agy exit=$LASTEXITCODE  minutes=" + [math]::Round(((Get-Date) - $t0).TotalMinutes, 1))

Log "grading..."
& py -3 grade.py 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath grade_console.log
Log "grade exit=$LASTEXITCODE"
Set-Content -Path DONE -Value "done"
