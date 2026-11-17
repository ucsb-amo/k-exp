Set-Location -Path $env:code

Get-ChildItem -Directory -Recurse -Filter ".git" -Hidden | ForEach-Object { 
    Write-Host "`nPulling $($_.Parent.Name)..." -ForegroundColor Cyan
    git -C $_.Parent.FullName pull 
}

Read-Host -Prompt "`nDone! Press Enter to exit"
