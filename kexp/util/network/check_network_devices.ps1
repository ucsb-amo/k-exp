<#
    Displays MAC addresses and IP addresses of all local network adapters
    and shows all devices detected on the network
#>

Write-Host "`n=== LOCAL NETWORK ADAPTERS ===" -ForegroundColor Cyan
Get-NetAdapter -Physical | ForEach-Object {
    $adapter = $_
    $ip = Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
    [PSCustomObject]@{
        Adapter = $adapter.Name
        Status = $adapter.Status
        MAC = $adapter.MacAddress
        IP = if ($ip) { $ip.IPAddress } else { "N/A" }
    }
} | Format-Table -AutoSize

Write-Host "`n=== DEVICES ON NETWORK ===" -ForegroundColor Cyan
Get-NetNeighbor | Where-Object State -ne "Unreachable" | Select-Object IPAddress, LinkLayerAddress, State | Format-Table -AutoSize

Write-Host "`n=== ARP TABLE ===" -ForegroundColor Cyan
arp -a

Write-Host "`nDone!" -ForegroundColor Green
