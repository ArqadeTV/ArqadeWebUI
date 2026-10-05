# Arqade one-line installer (Windows PowerShell 5.1+ / PowerShell 7).
#   irm https://__OWNER__.github.io/__REPO_NAME__/install.ps1 | iex
# Options via environment variables (set before running):
#   $env:ARQADE_PROFILE = 'lite' | 'standard' | 'full'     (default: standard)
#   $env:ARQADE_DIR     = 'C:\path\to\install'             (default: ~\ArqadeWebUI)
$ErrorActionPreference = 'Stop'
$Repo   = '__REPO__'
$Branch = if ($env:ARQADE_BRANCH) { $env:ARQADE_BRANCH } else { 'main' }
$Dir    = if ($env:ARQADE_DIR) { $env:ARQADE_DIR } else { Join-Path $HOME 'ArqadeWebUI' }

function Say($m) { Write-Host "> $m" -ForegroundColor Magenta }

if ($Repo -notmatch '^[^_/][^/]*/[^/]+$') { throw "This copy of install.ps1 hasn't been published through GitHub Pages yet (placeholder repo)." }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.ServicePointManager]::SecurityProtocol

$hasGit = [bool](Get-Command git -ErrorAction SilentlyContinue)
if ((Test-Path (Join-Path $Dir '.git')) -and $hasGit) {
    Say "Updating existing install in $Dir"
    git -C $Dir pull --ff-only
} elseif (Test-Path (Join-Path $Dir 'setup.bat')) {
    Say "Found an existing install in $Dir"
} elseif ($hasGit) {
    Say "Cloning https://github.com/$Repo into $Dir"
    git clone --depth 1 --branch $Branch "https://github.com/$Repo.git" $Dir
} else {
    Say "Downloading https://github.com/$Repo ($Branch)"
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("arqade-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $zip = Join-Path $tmp 'src.zip'
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    Copy-Item -Path (Join-Path $inner.FullName '*') -Destination $Dir -Recurse -Force
    Remove-Item $tmp -Recurse -Force
}

Set-Location $Dir
$flag = if ($env:ARQADE_PROFILE -in 'lite', 'standard', 'full') { "--$($env:ARQADE_PROFILE)" } else { '--standard' }
& .\setup.bat $flag
