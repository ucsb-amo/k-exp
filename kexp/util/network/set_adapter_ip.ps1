<#
    Configures local Ethernet adapter IPv4 settings based on MAC address
    mappings in LAN_devices.csv.

    - Network=LAN: set static IP/SubnetMask/DefaultGateway
    - Network=Broida: enable DHCP (Obtain an IP address automatically)

    Requires Administrator privileges to modify network settings.
#>

#Requires -RunAsAdministrator

function Normalize-Mac {
    param([string]$Mac)

    if ([string]::IsNullOrWhiteSpace($Mac)) { return $null }

    $parts = $Mac -split '[:-]'
    if ($parts.Count -ne 6) { return $null }

    $normalized = $parts | ForEach-Object {
        if ($_ -match '^[0-9A-Fa-f]{1,2}$') {
            $_.ToUpper().PadLeft(2, '0')
        } else {
            $null
        }
    }

    if ($normalized -contains $null) { return $null }
    return ($normalized -join '-')
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$csvPath = Join-Path $scriptDir 'LAN_devices.csv'
$googleSheetId = '1gRtfU0dBBsubY693K4iGCGTIeKWF_l-jR2FA3E3Ch34'
$googleSheetLanUrl = "https://docs.google.com/spreadsheets/d/$googleSheetId/export?format=csv&gid=0"
$googleSheetBroidaUrl = "https://docs.google.com/spreadsheets/d/$googleSheetId/export?format=csv&gid=207651269"

function Merge-GoogleSheetsTabs {
    param(
        [string]$LanUrl,
        [string]$BroidaUrl
    )
    
    $mergedRecords = @()
    $subnetMask = $null
    $defaultGateway = $null
    
    try {
        # Fetch LAN tab
        Write-Host "  Downloading LAN tab..." -ForegroundColor Cyan
        $lanResponse = Invoke-WebRequest -Uri $LanUrl -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
        $lanLines = $lanResponse.Content -split "`n" | Where-Object { $_ -match '\S' }
        
        # Parse LAN tab
        $lanRecords = $lanLines | ConvertFrom-Csv
        
        # Process LAN records
        foreach ($row in $lanRecords) {
            if ($row.'Device name' -and $row.'Device name' -notmatch '^(Subnet mask|Default gateway|,$)' -and $row.IP) {
                $mergedRecords += [PSCustomObject]@{
                    Network = 'LAN'
                    DeviceName = $row.'Device name'
                    MAC = $row.'MAC address'
                    IP = $row.IP
                    SubnetMask = $subnetMask
                    DefaultGateway = $defaultGateway
                }
            }
        }
        
        # Fetch Broida Network tab
        Write-Host "  Downloading Broida Network tab..." -ForegroundColor Cyan
        $broidaResponse = Invoke-WebRequest -Uri $BroidaUrl -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
        $broidaLines = $broidaResponse.Content -split "`n" | Where-Object { $_ -match '\S' }
        
        # Parse Broida tab
        $broidaRecords = $broidaLines | ConvertFrom-Csv
        
        # Process Broida records
        foreach ($row in $broidaRecords) {
            if ($row.'Device name / station' -and $row.'MAC address') {
                $mergedRecords += [PSCustomObject]@{
                    Network = 'Broida'
                    DeviceName = $row.'Device name / station'
                    MAC = $row.'MAC address'
                    IP = $null
                    SubnetMask = $null
                    DefaultGateway = $null
                }
            }
        }
        
        return $mergedRecords
    }
    catch {
        Write-Host "  Error downloading/parsing tabs: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }
}

# Try to update CSV from Google Sheets
Write-Host "Attempting to update LAN_devices.csv from Google Sheets..." -ForegroundColor Cyan
$mergedData = Merge-GoogleSheetsTabs -LanUrl $googleSheetLanUrl -BroidaUrl $googleSheetBroidaUrl

if ($mergedData) {
    try {
        # Convert merged data to proper CSV format
        $mergedData | ConvertTo-Csv -NoTypeInformation | Out-File -FilePath $csvPath -Encoding UTF8 -ErrorAction Stop
        Write-Host "Successfully updated LAN_devices.csv from Google Sheets" -ForegroundColor Green
    }
    catch {
        Write-Host "Warning: Could not write merged data to file: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "Using local LAN_devices.csv instead" -ForegroundColor Yellow
    }
}
else {
    Write-Host "Warning: Could not update from Google Sheets (no internet or access issue)" -ForegroundColor Yellow
    Write-Host "Using local LAN_devices.csv instead" -ForegroundColor Yellow
}

if (-not (Test-Path $csvPath)) {
    Write-Error "LAN_devices.csv not found in $scriptDir"
    exit 1
}

# Read CSV content
$csvContent = Get-Content $csvPath | Where-Object { $_ -match '\S' }
if (-not $csvContent) {
    Write-Error "LAN_devices.csv is empty"
    exit 1
}

$csvRecords = $csvContent | ConvertFrom-Csv
if (-not $csvRecords) {
    Write-Error "Failed to parse LAN_devices.csv"
    exit 1
}

# Validate expected columns
$requiredColumns = @('Network','DeviceName','MAC','IP','SubnetMask','DefaultGateway')
$missingColumns = $requiredColumns | Where-Object { -not ($csvRecords[0].PSObject.Properties.Name -contains $_) }
if ($missingColumns.Count -gt 0) {
    Write-Error "Missing columns in LAN_devices.csv: $($missingColumns -join ', ')"
    exit 1
}

# Defaults for LAN rows (first non-empty values)
$lanDefaultSubnet = '255.255.255.0'
$lanDefaultGateway = '192.168.1.0'

# Build MAC -> row mapping
$macToRow = @{}
foreach ($row in $csvRecords) {
    $mac = Normalize-Mac $row.MAC
    if ($mac) {
        $macToRow[$mac] = $row
    }
}

# Get all active physical adapters
$adapters = Get-NetAdapter | Where-Object { 
    $_.Status -eq 'Up' -and $_.MacAddress -and $_.HardwareInterface -eq $true
}

if (-not $adapters) {
    Write-Error "No active physical adapters found"
    exit 1
}

Write-Host "`n=== Configuring Ethernet Adapter(s) ===`n" -ForegroundColor Cyan

foreach ($adapter in $adapters) {
    $mac = Normalize-Mac $adapter.MacAddress
    
    if (-not $mac) {
        Write-Host "Skipping $($adapter.Name): Invalid MAC format" -ForegroundColor Yellow
        continue
    }

    $row = $macToRow[$mac]

    if (-not $row) {
        Write-Host "Skipping $($adapter.Name) ($mac): No entry in CSV" -ForegroundColor Yellow
        continue
    }

    $networkType = ($row.Network | ForEach-Object { $_.Trim() })
    $deviceName = $row.DeviceName

    Write-Host "Configuring: $($adapter.Name)" -ForegroundColor Green
    Write-Host "  Device: $deviceName"
    Write-Host "  MAC: $mac"
    Write-Host "  Network: $networkType"

    try {
        if ($networkType -eq 'Broida') {
            Write-Host "  Action: Enable DHCP" -ForegroundColor Cyan

            Set-NetIPInterface -InterfaceIndex $adapter.InterfaceIndex -Dhcp Enabled -ErrorAction Stop
            Set-DnsClientServerAddress -InterfaceIndex $adapter.InterfaceIndex -ResetServerAddresses -ErrorAction SilentlyContinue

            $existingManual = Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object { $_.PrefixOrigin -eq 'Manual' }
            foreach ($ip in $existingManual) {
                Remove-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -IPAddress $ip.IPAddress -Confirm:$false -ErrorAction SilentlyContinue
            }

            Remove-NetRoute -InterfaceIndex $adapter.InterfaceIndex -Confirm:$false -ErrorAction SilentlyContinue

            Write-Host "  Successfully configured (DHCP)" -ForegroundColor Green
        }
        elseif ($networkType -eq 'LAN') {
            $targetIp = $row.IP
            $subnetMask = if ($row.SubnetMask) { $row.SubnetMask } else { $lanDefaultSubnet }
            $defaultGateway = if ($row.DefaultGateway) { $row.DefaultGateway } else { $lanDefaultGateway }

            if (-not $targetIp) {
                Write-Host "  Skipping: No IP provided for LAN entry" -ForegroundColor Yellow
                continue
            }

            if (-not $subnetMask -or -not $defaultGateway) {
                Write-Host "  Skipping: Missing subnet mask or gateway for LAN entry" -ForegroundColor Yellow
                continue
            }

            Write-Host "  Action: Set static IP" -ForegroundColor Cyan
            Write-Host "  Target IP: $targetIp"
            Write-Host "  Subnet Mask: $subnetMask"
            Write-Host "  Default Gateway: $defaultGateway"

            Set-NetIPInterface -InterfaceIndex $adapter.InterfaceIndex -Dhcp Disabled -ErrorAction SilentlyContinue

            $existingIPs = Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
            foreach ($ip in $existingIPs) {
                Remove-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -IPAddress $ip.IPAddress -Confirm:$false -ErrorAction SilentlyContinue
            }

            Remove-NetRoute -InterfaceIndex $adapter.InterfaceIndex -Confirm:$false -ErrorAction SilentlyContinue

            $prefixLength = switch ($subnetMask) {
                '255.255.255.0' { 24 }
                '255.255.0.0' { 16 }
                '255.0.0.0' { 8 }
                '255.255.255.128' { 25 }
                '255.255.255.192' { 26 }
                '255.255.255.224' { 27 }
                '255.255.255.240' { 28 }
                '255.255.255.248' { 29 }
                '255.255.255.252' { 30 }
                default { 24 }
            }

            New-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex `
                             -IPAddress $targetIp `
                             -PrefixLength $prefixLength `
                             -DefaultGateway $defaultGateway `
                             -ErrorAction Stop | Out-Null

            Write-Host "  Successfully configured (Static)" -ForegroundColor Green
        }
        else {
            Write-Host "  Skipping: Unknown Network type '$networkType'" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    }

    Write-Host ""
}

Write-Host "Configuration complete!" -ForegroundColor Cyan
