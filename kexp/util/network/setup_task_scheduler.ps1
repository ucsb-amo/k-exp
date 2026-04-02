<#
    Creates a Task Scheduler task to run set_adapter_ip.ps1 on:
    1. System startup
    2. Network connection changes
    
    Requires Administrator privileges.
#>

#Requires -RunAsAdministrator

$scriptPath = Join-Path $PSScriptRoot 'set_adapter_ip.ps1'

if (-not (Test-Path $scriptPath)) {
    Write-Error "set_adapter_ip.ps1 not found in $PSScriptRoot"
    exit 1
}

$taskName = "Configure Ethernet IP Address"
$taskDescription = "Automatically configures Ethernet adapter IP based on MAC address from LAN_devices.csv"

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Task '$taskName' already exists. Removing it..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create the action
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$scriptPath`""

# Create trigger 1: At startup
$trigger1 = New-ScheduledTaskTrigger -AtStartup

# Create trigger 2: On network connection event
$trigger2CimInstance = Get-CimClass -ClassName MSFT_TaskEventTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
$trigger2 = New-CimInstance -CimClass $trigger2CimInstance -ClientOnly
$trigger2.Subscription = @"
<QueryList>
  <Query Id="0" Path="Microsoft-Windows-NetworkProfile/Operational">
    <Select Path="Microsoft-Windows-NetworkProfile/Operational">*[System[EventID=10000]]</Select>
  </Query>
</QueryList>
"@
$trigger2.Enabled = $true

# Create principal (run with highest privileges)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Create settings
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register the task with both triggers
$task = New-ScheduledTask -Action $action -Principal $principal -Settings $settings -Description $taskDescription
$task.Triggers.Add($trigger1)
$task.Triggers.Add($trigger2)

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null

Write-Host "`n✓ Task '$taskName' created successfully!" -ForegroundColor Green
Write-Host "`nTriggers configured:" -ForegroundColor Cyan
Write-Host "  1. At system startup"
Write-Host "  2. When network connection changes (Event ID 10000)"
Write-Host "`nScript path: $scriptPath" -ForegroundColor Cyan
Write-Host "`nTo view/edit the task, open Task Scheduler and look for '$taskName'" -ForegroundColor Yellow
