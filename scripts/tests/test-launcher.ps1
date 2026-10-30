$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'start-workbench.ps1')

function Assert([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$parseErrors = $null
$tokens = $null
[void][Management.Automation.Language.Parser]::ParseFile(
    (Join-Path (Split-Path $PSScriptRoot -Parent) 'start-workbench.ps1'), [ref]$tokens, [ref]$parseErrors)
Assert ($parseErrors.Count -eq 0) 'PowerShell parser errors'

$tempRoot = Join-Path $env:TEMP ('Workbench test ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot | Out-Null
try {
    Assert (-not (Test-PreparedRoot $tempRoot)) 'An empty directory must not be considered prepared'
    $rejected = $false
    try { Resolve-ProjectRoot $tempRoot $tempRoot } catch { $rejected = $true }
    Assert $rejected 'An explicit unprepared root must fail'
    foreach ($file in @('.env', 'backend\app\main.py', 'backend\.venv\Scripts\python.exe',
        'frontend\node_modules\next\dist\bin\next', 'compose.yaml')) {
        $path = Join-Path $tempRoot $file
        New-Item -ItemType Directory -Path (Split-Path $path -Parent) -Force | Out-Null
        New-Item -ItemType File -Path $path | Out-Null
    }
    Assert ((Resolve-ProjectRoot $tempRoot $tempRoot) -eq $tempRoot) 'Root paths with spaces must resolve'

    function Get-LocalResponse([string]$Url) { return $null }
    Assert (-not (Test-WorkbenchBackend)) 'An unavailable API must fail'
    Assert (-not (Test-WorkbenchFrontend)) 'An unavailable frontend must fail'
    function Get-LocalResponse([string]$Url) {
        if ($Url -like '*/health') { return @{ StatusCode = 200; Content = '{"status":"ok"}' } }
        return @{ StatusCode = 200; Content = '{"info":{"title":"Other API"}}' }
    }
    Assert (-not (Test-WorkbenchBackend)) 'A different API must not be reused'
    function Get-LocalResponse([string]$Url) {
        if ($Url -like '*/health') { return @{ StatusCode = 200; Content = '{"status":"ok"}' } }
        return @{ StatusCode = 200; Content = '{"info":{"title":"Enterprise AI Workbench API"}}' }
    }
    Assert (Test-WorkbenchBackend) 'Healthy Workbench API must be reusable'
    function Get-LocalResponse([string]$Url) {
        return @{ StatusCode = 200; Content = ('<title>prefix | ' + [regex]::Unescape('\u4f01\u4e1a AI \u5de5\u4f5c\u53f0') + '</title>') }
    }
    Assert (Test-WorkbenchFrontend) 'Workbench title with route prefix must be reusable'
    function Get-LocalResponse([string]$Url) { return @{ StatusCode = 200; Content = '<title>Another site</title>' } }
    Assert (-not (Test-WorkbenchFrontend)) 'Another website must not be reused'
    function Get-NetTCPConnection { return @(@{LocalPort = 3000}) }
    Assert (Test-PortBusy 3000) 'Occupied ports must be detected'
    function Get-NetTCPConnection { return @() }
    Assert (-not (Test-PortBusy 3000)) 'Free ports must be detected'
    $timedOut = $false
    try { Wait-Ready { $false } 0 'test' } catch { $timedOut = $true }
    Assert $timedOut 'An unready probe must time out'
    Write-Host 'Launcher focused checks passed.'
} finally {
    # Delete only the unique synthetic test tree beneath TEMP.
    $resolved = (Resolve-Path -LiteralPath $tempRoot).ProviderPath
    if ($resolved -ne $tempRoot -or -not $resolved.StartsWith([IO.Path]::GetFullPath($env:TEMP), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Unexpected test cleanup path'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
