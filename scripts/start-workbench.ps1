[CmdletBinding()]
param([string]$ProjectRoot, [switch]$NoBrowser)

$ErrorActionPreference = 'Stop'

function Test-PreparedRoot([string]$Root) {
    foreach ($item in @('.env', 'backend\app\main.py', 'backend\.venv\Scripts\python.exe',
        'frontend\node_modules\next\dist\bin\next', 'compose.yaml')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $item))) { return $false }
    }
    return $true
}

function Resolve-ProjectRoot([string]$ExplicitRoot, [string]$AdjacentRoot) {
    if ($ExplicitRoot) {
        $resolved = (Resolve-Path -LiteralPath $ExplicitRoot).ProviderPath
        if (-not (Test-PreparedRoot $resolved)) { throw 'ProjectRoot needs .env and installed backend/frontend dependencies.' }
        return $resolved
    }
    if (Test-PreparedRoot $AdjacentRoot) { return $AdjacentRoot }
    $common = & git -C $AdjacentRoot rev-parse --path-format=absolute --git-common-dir 2>$null
    if ($LASTEXITCODE -eq 0 -and $common) {
        $primary = Split-Path $common -Parent
        if (Test-PreparedRoot $primary) { return $primary }
    }
    throw 'No prepared checkout found. Complete the README local setup first, or supply -ProjectRoot.'
}

function Get-LocalResponse([string]$Url) {
    try { return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 } catch { return $null }
}

function Test-WorkbenchBackend {
    $health = Get-LocalResponse 'http://localhost:8000/health'
    $schema = Get-LocalResponse 'http://localhost:8000/openapi.json'
    try {
        return ($health.StatusCode -eq 200 -and ($health.Content | ConvertFrom-Json).status -eq 'ok' -and
            ($schema.Content | ConvertFrom-Json).info.title -eq 'Enterprise AI Workbench API')
    } catch { return $false }
}

function Test-WorkbenchFrontend {
    $page = Get-LocalResponse 'http://localhost:3000/app'
    $title = [regex]::Unescape('\u4f01\u4e1a AI \u5de5\u4f5c\u53f0')
    return ($null -ne $page -and $page.StatusCode -eq 200 -and
        $page.Content -match ('<title>(?:[^<]* \| )?' + [regex]::Escape($title) + '</title>'))
}

function Test-PortBusy([int]$Port) {
    return (@(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue).Count -gt 0)
}

function Wait-Ready([scriptblock]$Probe, [int]$Seconds, [string]$Description) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        if (& $Probe) { return }
        Write-Host ('Waiting for ' + $Description + ' ...')
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    throw ('Timed out waiting for ' + $Description + '. Check the logs or Docker Desktop; no automatic repair was attempted.')
}

function Invoke-Docker([string[]]$DockerArgs) {
    $id = [guid]::NewGuid().ToString('N')
    $outFile = Join-Path $script:LogDir ($id + '.docker.out.log')
    $errFile = Join-Path $script:LogDir ($id + '.docker.err.log')
    $cli = Start-Process -FilePath $script:Docker -ArgumentList $DockerArgs -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile
    # Windows PowerShell 5.1 must retain the handle before exit to read ExitCode.
    $processHandle = $cli.Handle
    if (-not $cli.WaitForExit(10000)) {
        # This is only our own hung CLI probe, never a server or container.
        $cli.Kill()
        throw 'Docker command timed out. Open Docker Desktop to check its status.'
    }
    $cli.WaitForExit()
    if ($cli.ExitCode -ne 0) { return $null }
    return (Get-Content -LiteralPath $outFile -Raw).Trim()
}

function Start-Workbench {
    $root = Resolve-ProjectRoot $ProjectRoot (Split-Path $PSScriptRoot -Parent)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $key = ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($root.ToLowerInvariant())))).Replace('-', '') }
    finally { $hash.Dispose() }
    $mutex = New-Object Threading.Mutex($false, ('Local\WorkbenchLauncher-' + $key))
    $locked = $false
    try {
        try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
        if (-not $locked) { throw 'Another launcher is running. Wait for it to finish.' }
        $script:LogDir = Join-Path $root ('.cache\dev-services\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
        New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null
        $script:Docker = (Get-Command docker.exe -ErrorAction Stop).Source
        $node = (Get-Command node.exe -ErrorAction Stop).Source
        $python = Join-Path $root 'backend\.venv\Scripts\python.exe'
        Write-Host ('Project: ' + $root)
        Write-Host ('Logs: ' + $script:LogDir)
        if (-not (Invoke-Docker @('info', '--format', '{{.ServerVersion}}'))) {
            $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
            if (-not (Test-Path -LiteralPath $desktop)) { throw 'Docker Desktop is not installed.' }
            Start-Process -FilePath $desktop -WindowStyle Hidden
            Wait-Ready { Invoke-Docker @('info', '--format', '{{.ServerVersion}}') } 120 'Docker engine'
        }
        # Find the existing container by Compose labels, never create a new volume.
        $containers = Invoke-Docker @('ps', '-a', '--filter', 'label=com.docker.compose.project=enterprise-ai-workbench',
            '--filter', 'label=com.docker.compose.service=postgres_pgvector', '--format', '{{.ID}}')
        if (-not $containers -or $containers -match '\s') { throw 'Expected exactly one existing postgres_pgvector container. Check Docker Desktop.' }
        $state = Invoke-Docker @('inspect', '--format', '{{.State.Running}}', $containers)
        if ($state -ne 'true') {
            if (-not (Invoke-Docker @('start', $containers))) { throw 'Cannot start the existing PostgreSQL container.' }
        }
        Wait-Ready { (Invoke-Docker @('inspect', '--format', '{{.State.Health.Status}}', $containers)) -eq 'healthy' } 60 'PostgreSQL'
        & $python (Join-Path $PSScriptRoot 'check-workbench.py') $root
        if ($LASTEXITCODE -ne 0) { throw 'Database/configuration preflight failed. See the message above; no migration was executed.' }

        if (-not (Test-WorkbenchBackend)) {
            if (Test-PortBusy 8000) { throw 'Port 8000 is occupied or its server is unhealthy. Close that server manually and retry.' }
            $arguments = @('-m', 'uvicorn', 'app.main:app', '--app-dir', ('"' + (Join-Path $root 'backend') + '"'),
                '--env-file', ('"' + (Join-Path $root '.env') + '"'), '--host', '127.0.0.1', '--port', '8000')
            Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory (Join-Path $root 'backend') `
                -WindowStyle Hidden -RedirectStandardOutput (Join-Path $script:LogDir 'backend.out.log') `
                -RedirectStandardError (Join-Path $script:LogDir 'backend.err.log')
            Wait-Ready { Test-WorkbenchBackend } 60 'backend'
        }
        if (-not (Test-WorkbenchFrontend)) {
            if (Test-PortBusy 3000) { throw 'Port 3000 is occupied or /app is unhealthy. Close that server manually and retry.' }
            $next = Join-Path $root 'frontend\node_modules\next\dist\bin\next'
            Start-Process -FilePath $node -ArgumentList @(('"' + $next + '"'), 'dev', '--hostname', '127.0.0.1', '--port', '3000') `
                -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $script:LogDir 'frontend.out.log') `
                -RedirectStandardError (Join-Path $script:LogDir 'frontend.err.log')
            Wait-Ready { Test-WorkbenchFrontend } 90 'frontend'
        }
        Write-Host 'Ready: http://localhost:3000/app'
        Write-Host 'API:   http://localhost:8000/docs'
        if (-not $NoBrowser) { Start-Process 'http://localhost:3000/app' }
    } finally {
        if ($locked) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Start-Workbench } catch { Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }
}
