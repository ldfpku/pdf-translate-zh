# pdf-translate-zh 一键环境配置（Windows）：找到或装好 Python 3.9+，然后交给 bootstrap.py 全自动完成。
#   powershell -ExecutionPolicy Bypass -File setup.ps1          核心依赖 + 中文字体 + 自检
#   powershell -ExecutionPolicy Bypass -File setup.ps1 --sr     另外装插图超分后端（NVIDIA 显卡装 CUDA 版）并下载权重
$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Py {
    $cands = @()
    if ($env:PDF_ZH_PYTHON) { $cands += ,@($env:PDF_ZH_PYTHON) }
    $cands += ,@("py", "-3"); $cands += ,@("python"); $cands += ,@("python3")
    foreach ($c in $cands) {
        $exe = $c[0]; $pre = @($c | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            & $exe @pre -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return ,$c }
        } catch { }
    }
    return $null
}

$py = Find-Py
if (-not $py) {
    Write-Host "[setup] 没找到 Python 3.9+，用 winget 自动安装 Python 3.12 …"
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $py = Find-Py
    if (-not $py) { Write-Host "[setup] 安装后仍找不到 Python，请从 https://www.python.org/downloads/windows/ 安装后重跑"; exit 1 }
}
$exe = $py[0]; $pre = @($py | Select-Object -Skip 1)
& $exe @pre (Join-Path $Dir "scripts\bootstrap.py") @args
exit $LASTEXITCODE
