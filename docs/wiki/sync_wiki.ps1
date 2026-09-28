# Push docs\wiki\ to the GitHub wiki (ucsb-amo/k-exp.wiki, branch master) in one command.
#   powershell -ExecutionPolicy Bypass -File docs\wiki\sync_wiki.ps1            # commit + push
#   powershell -ExecutionPolicy Bypass -File docs\wiki\sync_wiki.ps1 -DryRun    # show changes only
param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (git -C $here rev-parse --show-toplevel).Trim()
$src = Join-Path $repoRoot 'docs\wiki'
$wikiUrl = if ($env:WIKI_URL) { $env:WIKI_URL } else { 'https://github.com/ucsb-amo/k-exp.wiki.git' }
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("kexp-wiki-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    Write-Host "cloning $wikiUrl"
    git clone --quiet $wikiUrl (Join-Path $tmp 'wiki')
    $dst = Join-Path $tmp 'wiki'
    # Remove every page in the clone (not .git), then copy docs\wiki over it.
    Get-ChildItem -Path $dst -Force | Where-Object { $_.Name -ne '.git' } | Remove-Item -Recurse -Force
    Get-ChildItem -Path $src -Force | Where-Object {
        $_.Name -notin @('sync_wiki.sh', 'sync_wiki.ps1', 'README.md') -and $_.Extension -ne '.py'
    } | Copy-Item -Destination $dst -Recurse -Force
    Push-Location $dst
    try {
        $status = git status --porcelain
        if (-not $status) { Write-Host 'wiki already matches docs\wiki: nothing to push'; return }
        git add -A
        Write-Host 'changes:'; git status --short
        if ($DryRun) { Write-Host 'dry run: not committing'; return }
        $sha = (git -C $repoRoot rev-parse --short HEAD).Trim()
        git commit --quiet -m "Sync from k-exp docs/wiki @ $sha"
        git push origin HEAD:master
        Write-Host "pushed to $wikiUrl (master)"
    } finally { Pop-Location }
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
