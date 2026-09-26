<#
    Makes the lab shortcuts in kexp\_bat\shortcuts usable on this PC.

      1. PATH     adds %code%\k-exp\kexp\_bat\shortcuts to the system PATH, so `ar`, `art` and
                  the GUI shortcuts run from any terminal.
      2. PATHEXT  adds .LNK to the system PATHEXT, so typing `ar` runs ar.lnk.
      3. Search   adds the folder to the Windows Search index, so Start-menu search finds
                  "Server Dashboard", "LiveOD Server", ...

    Safe to re-run: every step checks first and leaves anything already in place alone.

    PATH and PATHEXT are edited in the registry directly, never with setx: setx cuts values at
    1024 characters, and the usual `setx PATH "%PATH%;..."` also bakes in expanded %vars% and
    copies the machine PATH into the user PATH. Here the raw (unexpanded) value is read, one
    entry is appended, and the result is written back. Before the first write the registry key
    is exported to %LOCALAPPDATA%\kexp\ (undo: double-click the .reg), and the index rules are
    listed to a .txt there (undo: Control Panel > Indexing Options > Modify).

    Needs an elevated PowerShell (PATH/PATHEXT are machine-wide) and %code% set machine-wide
    first (PC-Setup step 3). Open a new terminal afterwards; VS Code needs a full restart.

    Usage (elevated):
        powershell -NoProfile -ExecutionPolicy Bypass -File "%code%\k-exp\kexp\_bat\setup_shortcuts.ps1"
    Options:
        -ExcludeRestOfCode  also keep the rest of %code% (repos, .venv) out of the index, so only
                            the shortcuts folder is searchable
        -WhatIf             report what would change and change nothing (works unelevated)
#>
[CmdletBinding(SupportsShouldProcess)]
param([switch]$ExcludeRestOfCode)

$ErrorActionPreference = 'Stop'

$HKLM = [Microsoft.Win32.Registry]::LocalMachine
$HKCU = [Microsoft.Win32.Registry]::CurrentUser
$machineEnvKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
$userEnvKey = 'Environment'
$shortcutsEntry = '%code%\k-exp\kexp\_bat\shortcuts'
$backupDir = Join-Path $env:LOCALAPPDATA 'kexp'
$stamp = '{0:yyyy-MM-dd_HH-mm-ss}' -f (Get-Date)
$script:backedUp = @{}
$script:envChanged = $false

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $WhatIfPreference) {
    throw 'Run this from an elevated PowerShell (PATH and PATHEXT are machine-wide), or pass -WhatIf to preview.'
}

function Get-RawEnv([Microsoft.Win32.RegistryKey]$Hive, [string]$Key, [string]$Name) {
    # the value as stored, %vars% left unexpanded; $null if absent
    $k = $Hive.OpenSubKey($Key)
    if ($null -eq $k) { return $null }
    try {
        if ($k.GetValueNames() -notcontains $Name) { return $null }
        [pscustomobject]@{
            Value = [string]$k.GetValue($Name, '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
            Kind  = $k.GetValueKind($Name)
        }
    } finally { $k.Close() }
}

function Set-RawEnv([Microsoft.Win32.RegistryKey]$Hive, [string]$Key, [string]$Name, [string]$Value,
                    [Microsoft.Win32.RegistryValueKind]$Kind) {
    $regPath = $(if ($Hive -eq $HKLM) { 'HKLM' } else { 'HKCU' }) + '\' + $Key
    if (-not $script:backedUp[$regPath]) {
        New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
        $file = Join-Path $backupDir ('env_backup_{0}_{1}.reg' -f $regPath.Substring(0, 4), $stamp)
        & reg.exe export $regPath $file /y | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "reg export of $regPath failed ($LASTEXITCODE); nothing changed" }
        Write-Host "  backup: $file"
        $script:backedUp[$regPath] = $true
    }
    $k = $Hive.OpenSubKey($Key, $true)
    try { $k.SetValue($Name, $Value, $Kind) } finally { $k.Close() }
    $script:envChanged = $true
}

function ConvertTo-DirKey([string]$Entry) {
    [Environment]::ExpandEnvironmentVariables($Entry.Trim().Trim('"')).TrimEnd('\').ToLowerInvariant()
}

# --- %code% --------------------------------------------------------------------------------
$code = Get-RawEnv $HKLM $machineEnvKey 'code'
if ($null -eq $code) {
    throw ('%code% is not set machine-wide; set it first (PC-Setup step 3), e.g. ' +
           '[Environment]::SetEnvironmentVariable(''code'', ''C:\Users\<you>\code'', ''Machine'')')
}
# this process only, so %code% expands below even if this shell started before it was set
$env:code = [Environment]::ExpandEnvironmentVariables($code.Value).TrimEnd('\')
$shortcutsDir = [Environment]::ExpandEnvironmentVariables($shortcutsEntry)
if (-not (Test-Path -LiteralPath $shortcutsDir -PathType Container)) {
    throw "Shortcuts folder not found: $shortcutsDir (is %code% = $env:code right?)"
}
Write-Host "shortcuts folder: $shortcutsDir"

# --- 1. PATH -------------------------------------------------------------------------------
Write-Host '[1/3] PATH'
$machinePath = Get-RawEnv $HKLM $machineEnvKey 'Path'
$userPath = Get-RawEnv $HKCU $userEnvKey 'Path'
$onPath = @($machinePath, $userPath) | Where-Object { $_ } |
    ForEach-Object { $_.Value -split ';' } | Where-Object { $_.Trim() } |
    ForEach-Object { ConvertTo-DirKey $_ }
if ($onPath -contains (ConvertTo-DirKey $shortcutsEntry)) {
    Write-Host '  already on PATH'
} else {
    $old = $(if ($machinePath) { $machinePath.Value.TrimEnd(';') } else { '' })
    $new = $(if ($old) { "$old;$shortcutsEntry" } else { $shortcutsEntry })
    if ($PSCmdlet.ShouldProcess('system PATH', "append $shortcutsEntry")) {
        # REG_EXPAND_SZ so %code% (and the %SystemRoot%-style entries already there) expand
        Set-RawEnv $HKLM $machineEnvKey 'Path' $new ([Microsoft.Win32.RegistryValueKind]::ExpandString)
        Write-Host "  appended $shortcutsEntry (system PATH now $($new.Length) chars unexpanded)"
    }
}

# --- 2. PATHEXT ----------------------------------------------------------------------------
# A user-level PATHEXT replaces the system one outright (it is not merged like PATH), so if the
# account running this has one, it needs .LNK too. Elevating as a different admin account
# means HKCU is that account's, not the lab user's.
Write-Host '[2/3] PATHEXT'
foreach ($scope in @(
        @{ Label = 'system'; Hive = $HKLM; Key = $machineEnvKey },
        @{ Label = 'user'; Hive = $HKCU; Key = $userEnvKey })) {
    $pathext = Get-RawEnv $scope.Hive $scope.Key 'PATHEXT'
    if ($null -eq $pathext) {
        if ($scope.Label -eq 'system') { Write-Warning '  system PATHEXT is missing; not creating one, check this PC by hand' }
        continue
    }
    if (($pathext.Value -split ';') -contains '.LNK') {
        Write-Host "  $($scope.Label) PATHEXT already has .LNK"
    } elseif ($PSCmdlet.ShouldProcess("$($scope.Label) PATHEXT", 'append .LNK')) {
        Set-RawEnv $scope.Hive $scope.Key 'PATHEXT' ($pathext.Value.TrimEnd(';') + ';.LNK') $pathext.Kind
        Write-Host "  appended .LNK to $($scope.Label) PATHEXT"
    }
}

if ($script:envChanged) {
    # what setx does after writing: tell Explorer (and so every new terminal) to reload
    if (-not ('KexpSetup.Native' -as [type])) {
        Add-Type -Namespace KexpSetup -Name Native -MemberDefinition @'
[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam,
                                               uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
'@
    }
    $result = [UIntPtr]::Zero
    # HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG, 5 s
    [void][KexpSetup.Native]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$result)
    Write-Host '  environment change broadcast; open a new terminal (VS Code: restart the app)'
}

# --- 3. Windows Search index -----------------------------------------------------------------
# There is no cmdlet or CLI for indexed locations; this is the crawl-scope COM API that
# Indexing Options uses (SearchAPI.h). Interfaces are declared in vtable order.
Write-Host '[3/3] Windows Search index'
if (-not ('KexpSetup.SearchScope' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace KexpSetup {
    [ComImport, Guid("AB310581-AC80-11D1-8DF3-00C04FB6EF69"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ISearchManager {
        void GetIndexerVersionStr(out IntPtr a);
        void GetIndexerVersion(out uint a, out uint b);
        void GetParameter(IntPtr a, out IntPtr b);
        void SetParameter(IntPtr a, IntPtr b);
        void get_ProxyName(out IntPtr a);
        void get_BypassList(out IntPtr a);
        void SetProxy(int a, int b, uint c, IntPtr d, IntPtr e);
        ISearchCatalogManager GetCatalog([MarshalAs(UnmanagedType.LPWStr)] string catalog);
    }

    [ComImport, Guid("AB310581-AC80-11D1-8DF3-00C04FB6EF50"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ISearchCatalogManager {
        void get_Name(out IntPtr a);
        void GetParameter(IntPtr a, out IntPtr b);
        void SetParameter(IntPtr a, IntPtr b);
        void GetCatalogStatus(out int a, out int b);
        void Reset();
        void Reindex();
        void ReindexMatchingURLs(IntPtr a);
        void ReindexSearchRoot(IntPtr a);
        void put_ConnectTimeout(uint a);
        void get_ConnectTimeout(out uint a);
        void put_DataTimeout(uint a);
        void get_DataTimeout(out uint a);
        void NumberOfItems(out int a);
        void NumberOfItemsToIndex(out int a, out int b, out int c);
        void URLBeingIndexed(out IntPtr a);
        void GetURLIndexingState(IntPtr a, out uint b);
        void GetPersistentItemsChangedSink(out IntPtr a);
        void RegisterViewForNotification(IntPtr a, IntPtr b, out uint c);
        void GetItemsChangedSink(IntPtr a, ref Guid b, out IntPtr c, out Guid d, out Guid e, out uint f);
        void UnregisterViewForNotification(uint a);
        void SetExtensionClusion(IntPtr a, int b);
        void EnumerateExcludedExtensions(out IntPtr a);
        void GetQueryHelper(out IntPtr a);
        void put_DiacriticSensitivity(int a);
        void get_DiacriticSensitivity(out int a);
        ISearchCrawlScopeManager GetCrawlScopeManager();
    }

    [ComImport, Guid("AB310581-AC80-11D1-8DF3-00C04FB6EF55"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ISearchCrawlScopeManager {
        void AddDefaultScopeRule(IntPtr a, int b, uint c);
        void AddRoot(IntPtr a);
        void RemoveRoot(IntPtr a);
        void EnumerateRoots(out IntPtr a);
        void AddHierarchicalScope(IntPtr a, int b, int c, int d);
        void AddUserScopeRule([MarshalAs(UnmanagedType.LPWStr)] string url, int include, int overrideChildren, uint followFlags);
        void RemoveScopeRule(IntPtr a);
        IEnumSearchScopeRules EnumerateScopeRules();
        void HasParentScopeRule(IntPtr a, out int b);
        void HasChildScopeRule(IntPtr a, out int b);
        void IncludedInCrawlScope([MarshalAs(UnmanagedType.LPWStr)] string url, out int included);
        void IncludedInCrawlScopeEx(IntPtr a, out int b, out int c);
        void RevertToDefaultScopes();
        void SaveAll();
    }

    [ComImport, Guid("AB310581-AC80-11D1-8DF3-00C04FB6EF54"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IEnumSearchScopeRules {
        [PreserveSig] int Next(uint celt, out ISearchScopeRule rule, out uint fetched);
    }

    [ComImport, Guid("AB310581-AC80-11D1-8DF3-00C04FB6EF53"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ISearchScopeRule {
        void get_PatternOrURL([MarshalAs(UnmanagedType.LPWStr)] out string url);
        void get_IsIncluded(out int included);
        void get_IsDefault(out int isDefault);
    }

    public static class SearchScope {
        const uint FF_INDEXCOMPLEXURLS = 1;
        static ISearchCrawlScopeManager csm;

        // one manager for the whole script: added rules only persist via SaveAll on the same one
        static ISearchCrawlScopeManager Csm() {
            if (csm == null) {
                Type t = Type.GetTypeFromCLSID(new Guid("7D096C5F-AC08-4F1F-BEB7-5C22C517CE39"));
                csm = ((ISearchManager)Activator.CreateInstance(t)).GetCatalog("SystemIndex").GetCrawlScopeManager();
            }
            return csm;
        }

        // user-added rules as "include|<url>" / "exclude|<url>"
        public static string[] UserRules() {
            var rules = new List<string>();
            IEnumSearchScopeRules e = Csm().EnumerateScopeRules();
            ISearchScopeRule r; uint n;
            while (e.Next(1, out r, out n) == 0 && n == 1) {
                string url; int inc, def;
                r.get_PatternOrURL(out url); r.get_IsIncluded(out inc); r.get_IsDefault(out def);
                if (def == 0) rules.Add((inc != 0 ? "include|" : "exclude|") + url);
            }
            return rules.ToArray();
        }

        public static void AddUserRule(string url, bool include) {
            Csm().AddUserScopeRule(url, include ? 1 : 0, 0, FF_INDEXCOMPLEXURLS);
        }

        public static void Save() { Csm().SaveAll(); }

        public static bool IsIncluded(string url) {
            int included; Csm().IncludedInCrawlScope(url, out included); return included != 0;
        }
    }
}
'@
}

$shortcutsUrl = "file:///$shortcutsDir\"
$codeUrl = "file:///$env:code\"
try {
    $rules = [KexpSetup.SearchScope]::UserRules()
} catch {
    Write-Warning "  Windows Search unavailable, skipped ($($_.Exception.Message)). Is the WSearch service running?"
    return
}

# the exclude goes first; it does not override child rules, so the more specific include wins
$wanted = @()
if ($ExcludeRestOfCode) { $wanted += , @('exclude', $codeUrl) }
$wanted += , @('include', $shortcutsUrl)

$added = $false
foreach ($w in $wanted) {
    $tag, $url = $w
    if ($rules -contains "$tag|$url") {
        Write-Host "  already has $tag rule for $url"
    } elseif ($PSCmdlet.ShouldProcess('Windows Search index', "add $tag rule for $url")) {
        [KexpSetup.SearchScope]::AddUserRule($url, $tag -eq 'include')
        Write-Host "  added $tag rule for $url"
        $added = $true
    }
}

if ($added) {
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $file = Join-Path $backupDir "search_rules_backup_$stamp.txt"
    Set-Content -LiteralPath $file -Encoding UTF8 -Value (
        @('# Windows Search user-added scope rules before setup_shortcuts.ps1 changed them') + $rules)
    Write-Host "  backup: $file"
    [KexpSetup.SearchScope]::Save()
}

try {
    if ([KexpSetup.SearchScope]::IsIncluded($shortcutsUrl)) {
        Write-Host '  shortcuts folder is in the index scope (the indexer picks up new locations within a few minutes)'
    } else {
        Write-Warning '  shortcuts folder is still not in the index scope; add it by hand in Control Panel > Indexing Options > Modify'
    }
} catch {
    # e.g. a drive with no crawl root yet; Indexing Options adds the root itself
    Write-Warning "  could not check the index scope ($($_.Exception.Message)); add the folder by hand in Control Panel > Indexing Options > Modify"
}
