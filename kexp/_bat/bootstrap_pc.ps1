<#
    First step on a new K machine-control PC. Installs Git, clones the private `code` repo into
    your code folder (you sign in to GitHub once), then starts code\setup\setup.ps1, which does
    the rest: programs, the other repos, environment variables, the Python environment.

    Paste this one line into a terminal (Command Prompt or PowerShell), as yourself -- not "as
    administrator"; it asks for admin rights when it needs them:

      powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/ucsb-amo/k-exp/main/kexp/_bat/bootstrap_pc.ps1 | iex"

    On a PC set up before 2026-09-26, whose code folder is not yet a clone of `code`, it turns the
    folder into one in place: it lists the files that would be replaced and asks first. Only files
    `code` tracks are replaced; the other repos, .venv and everything else stay as they are.

    This file is public because k-exp is. It holds no lab details: the setup itself lives in the
    private `code` repo. Run as a file, it also takes:
      -CodeDir <path>   the code folder (default: %code% if it is set, otherwise it asks)
      -NoSetup          stop after the clone instead of starting setup.ps1
      -Yes              don't ask: default folder, convert, start the setup
#>
[CmdletBinding()]
param([string]$CodeDir, [switch]$NoSetup, [switch]$Yes)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$CodeRepo = 'https://github.com/ucsb-amo/code.git'
# Keep in step with Git.Git in code\setup\pc_setup.json.
$GitOverride = '/VERYSILENT /NORESTART /NOCANCEL /SP- /COMPONENTS=gitlfs,assoc,assoc_sh,windowsterminal /o:EditorOption=VisualStudioCode'

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }
function Update-SessionPath {
    $env:Path = (@([Environment]::GetEnvironmentVariable('Path', 'Machine'),
                   [Environment]::GetEnvironmentVariable('Path', 'User')) | Where-Object { $_ }) -join ';'
}
function Invoke-Git([string[]]$GitArgs) {
    & git @GitArgs
    if ($LASTEXITCODE) { throw "git $($GitArgs -join ' ') exited $LASTEXITCODE" }
}
function Format-UrlKey([string]$Url) { ($Url.Trim().TrimEnd('/') -replace '\.git$', '').ToLowerInvariant() }

$me = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($me.IsSystem) { throw 'This is running as SYSTEM. Run it as the lab user, in a normal terminal.' }
Say ''
Say "K machine-control PC bootstrap (running as $($me.Name))" White

# 1. Git
Update-SessionPath
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'winget is missing: install "App Installer" from the Microsoft Store (or update Windows), then run this again.'
    }
    Say 'Installing Git (you may get an administrator prompt) ...' Yellow
    & winget install --id Git.Git -e --source winget --scope machine --accept-package-agreements `
        --accept-source-agreements --disable-interactivity --override $GitOverride
    Update-SessionPath
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git did not install (winget exited $LASTEXITCODE). Install it from https://git-scm.com, then run this again."
    }
}
Say "Git: $(git --version)"

# 2. The code folder: %code% if this PC has one, otherwise ask (the suggestion is your own folder).
if (-not $CodeDir) { $CodeDir = [Environment]::GetEnvironmentVariable('code', 'Machine') }
if (-not $CodeDir) {
    $default = Join-Path $HOME 'code'
    if ($Yes) { $CodeDir = $default }
    else {
        $answer = Read-Host "Code folder [$default]"
        $CodeDir = if ($answer) { $answer.Trim().Trim('"') } else { $default }
    }
}
$CodeDir = [IO.Path]::GetFullPath($CodeDir)
Say "Code folder: $CodeDir"

$gitDir = Join-Path $CodeDir '.git'
$isEmpty = -not (Test-Path -LiteralPath $CodeDir) -or -not (Get-ChildItem -LiteralPath $CodeDir -Force | Select-Object -First 1)
if ($isEmpty) {
    New-Item -ItemType Directory -Force -Path $CodeDir | Out-Null
    Say "Cloning $CodeRepo (sign in to GitHub if a window asks) ..." Yellow
    Invoke-Git @('clone', $CodeRepo, $CodeDir)
} else {
    $origin = $null
    if (Test-Path -LiteralPath $gitDir) {
        $origin = & git -C $CodeDir config --get remote.origin.url
    }
    if ($origin -and (Format-UrlKey $origin) -eq (Format-UrlKey $CodeRepo)) {
        Say 'The code folder is already a clone of code; updating it ...'
        & git -C $CodeDir pull --ff-only
        if ($LASTEXITCODE) { Say 'Could not fast-forward it (local changes, or another branch); left as it is.' Yellow }
    } elseif ($origin) {
        throw "$CodeDir is a clone of $origin, not of code. Choose another folder with -CodeDir, or sort it out by hand."
    } else {
        # An older PC: the folder holds the repos but is not a clone of code yet.
        Say "$CodeDir has files but is not a clone of code yet; fetching code to see what would change ..." Yellow
        if (-not (Test-Path -LiteralPath $gitDir)) { Invoke-Git @('-C', $CodeDir, 'init', '-q') }
        Invoke-Git @('-C', $CodeDir, 'remote', 'add', 'origin', $CodeRepo)
        Invoke-Git @('-C', $CodeDir, 'fetch', 'origin')
        $replaced = @(& git -C $CodeDir ls-tree -r --name-only origin/main |
                      Where-Object { Test-Path -LiteralPath (Join-Path $CodeDir $_) })
        Say ''
        if ($replaced.Count) {
            Say "Checking out code here replaces these $($replaced.Count) existing files with code's versions:" Yellow
            $replaced | Select-Object -First 25 | ForEach-Object { Say "    $_" Yellow }
            if ($replaced.Count -gt 25) { Say "    ... and $($replaced.Count - 25) more" Yellow }
        } else {
            Say 'Checking out code here replaces no existing files.' Yellow
        }
        Say 'Everything else (the other repos, .venv, your own files) stays as it is.' Yellow
        if (-not $Yes) {
            $answer = Read-Host 'Go ahead? [y/N]'
            if ($answer -notmatch '^(y|yes)$') {
                throw "Stopped before the checkout. The folder now has a .git with origin set; nothing else changed."
            }
        }
        Invoke-Git @('-C', $CodeDir, 'checkout', '-f', '-B', 'main', 'origin/main')
    }
}

# 3. The rest is setup.ps1's job.
$setup = Join-Path $CodeDir 'setup\setup.ps1'
if (-not (Test-Path -LiteralPath $setup)) {
    Say 'This version of code has no setup\setup.ps1 yet: follow the PC Setup page on the k-exp wiki.' Yellow
    return
}
if ($NoSetup) { Say "Done. Next: double-click $CodeDir\setup\setup.bat" Green; return }
if (-not $Yes) {
    $answer = Read-Host 'Start the full setup now? [Y/n]'
    if ($answer -match '^(n|no)$') { Say "Later: double-click $CodeDir\setup\setup.bat"; return }
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup
