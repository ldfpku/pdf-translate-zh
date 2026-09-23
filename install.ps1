# pdf-translate-zh installer (Windows PowerShell 5.1+ / PowerShell 7)
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less scripts in the
# system ANSI code page (e.g. GBK), and `irm ... | iex` must work on every locale.
#
# Usage (inside a clone of the repo):
#   powershell -ExecutionPolicy Bypass -File install.ps1                 auto-detect installed AI tools, install to all of them
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Agent claude   one tool: claude codex cursor copilot gemini antigravity opencode windsurf agents
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Agent all
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Project .      install into a project (.claude\skills and .agents\skills)
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Link           directory junction (edits in the repo take effect immediately)
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Bootstrap      also set up Python deps and CJK fonts now
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
# One-liner without cloning:
#   irm https://raw.githubusercontent.com/ldfpku/pdf-translate-zh/main/install.ps1 | iex
param(
    [string[]]$Agent = @(),
    [string]$Project = "",
    [switch]$Link,
    [switch]$Bootstrap,
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"
$Name = "pdf-translate-zh"
$Repo = "ldfpku/pdf-translate-zh"
$Ref = if ($env:PDF_ZH_REF) { $env:PDF_ZH_REF } else { "main" }
$HomeDir = [Environment]::GetFolderPath("UserProfile")

# ---- skill source: the repo this script lives in; when piped through iex, download the GitHub archive
$Src = $null
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "skills\$Name\SKILL.md"))) {
    $Src = Join-Path $PSScriptRoot "skills\$Name"
}
if (-not $Src -and -not $Uninstall) {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("pdfzh-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $zip = Join-Path $tmp "src.zip"
    Write-Host "[install] downloading $Repo@$Ref ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/$Repo/zip/$Ref" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $Src = Get-ChildItem -Path $tmp -Directory -Recurse -Filter $Name |
           Where-Object { Test-Path (Join-Path $_.FullName "SKILL.md") } | Select-Object -First 1 -ExpandProperty FullName
    if (-not $Src) { throw "[install] skills\$Name not found in the downloaded archive" }
    $Link = $false
}

# tool -> (home dir used for auto-detection, global skills dir)
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HomeDir ".codex" }
$Dirs = [ordered]@{
    claude   = @((Join-Path $HomeDir ".claude"), (Join-Path $HomeDir ".claude\skills"))
    codex    = @($CodexHome, (Join-Path $CodexHome "skills"))
    cursor   = @((Join-Path $HomeDir ".cursor"), (Join-Path $HomeDir ".cursor\skills"))
    copilot  = @((Join-Path $HomeDir ".copilot"), (Join-Path $HomeDir ".copilot\skills"))
    gemini   = @((Join-Path $HomeDir ".gemini"), (Join-Path $HomeDir ".gemini\skills"))
    antigravity = @((Join-Path $HomeDir ".gemini\config"), (Join-Path $HomeDir ".gemini\config\skills"))
    opencode = @((Join-Path $HomeDir ".config\opencode"), (Join-Path $HomeDir ".config\opencode\skills"))
    windsurf = @((Join-Path $HomeDir ".codeium\windsurf"), (Join-Path $HomeDir ".codeium\windsurf\skills"))
    agents   = @((Join-Path $HomeDir ".agents"), (Join-Path $HomeDir ".agents\skills"))
}

$Targets = @()
if ($Project) {
    $p = (Resolve-Path $Project).Path
    $Targets = @((Join-Path $p ".claude\skills"), (Join-Path $p ".agents\skills"))
} else {
    # accept "-Agent claude,cursor" both from PowerShell arrays and from `-File` (single string)
    $Agent = @($Agent | ForEach-Object { $_ -split '[,;\s]+' } | Where-Object { $_ } | ForEach-Object { $_.ToLower() })
    if ($Agent -contains "all") { $Agent = @($Dirs.Keys) }
    if ($Agent.Count -eq 0) {
        $Agent = @($Dirs.Keys | Where-Object { Test-Path $Dirs[$_][0] })
        if ($Agent.Count -eq 0) { $Agent = @("claude") }
    }
    foreach ($a in $Agent) {
        if (-not $Dirs.Contains($a)) { throw "[install] unknown tool: $a (choose from: $($Dirs.Keys -join ' ') all)" }
        $Targets += $Dirs[$a][1]
    }
}

function Remove-Skill($path) {
    $item = Get-Item $path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { $item.Delete() } else { Remove-Item $path -Recurse -Force }
}

foreach ($d in $Targets) {
    $dst = Join-Path $d $Name
    if ($Uninstall) {
        if (Test-Path $dst) { Remove-Skill $dst; Write-Host "[install] removed $dst" }
        continue
    }
    New-Item -ItemType Directory -Path $d -Force | Out-Null
    if (Test-Path $dst) { Remove-Skill $dst }
    if ($Link) {
        $lt = if ($IsLinux -or $IsMacOS) { "SymbolicLink" } else { "Junction" }
        New-Item -ItemType $lt -Path $dst -Target $Src | Out-Null
        if (-not (Test-Path (Join-Path $dst "SKILL.md"))) { throw "[install] failed to create link $dst" }
    } else {
        Copy-Item -Path $Src -Destination $dst -Recurse -Force
        Get-ChildItem -Path $dst -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
    }
    Write-Host "[install] installed -> $dst"
}

if (-not $Uninstall -and $Bootstrap) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path (Join-Path $Targets[0] $Name) "setup.ps1")
}
if (-not $Uninstall) {
    Write-Host "[install] done. Restart your AI tool, then ask it to translate a PDF into Chinese."
    Write-Host "          Python dependencies and fonts are configured automatically on first use."
}
