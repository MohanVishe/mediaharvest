<#
MediaHarvest for Windows: opens it, closes it, and does what the Settings page
cannot do from inside Docker (pick folders, restart with them, close Docker).

  MediaHarvest.ps1          Start Docker Desktop and MediaHarvest, open it in the
                            browser, then stay in the background for Settings
                            and the Close button.
  MediaHarvest.ps1 -Close   Stop MediaHarvest, and Docker Desktop when no other
                            container is running (the page's power button does
                            the same).
  MediaHarvest.ps1 -Install Copy this helper to %LOCALAPPDATA%\MediaHarvest and
                            put a "MediaHarvest" shortcut on the desktop. Tell it
                            where docker compose runs:
        -ComposeDir <folder>                the folder with compose.yaml (the installer's), or
        -WslDistro <name> -WslDir <path>    a checkout inside WSL
        -Downloads <folder>                 first download folder (default Downloads\MediaHarvest)
        -Port <n>                           the port in .env (default 8081)

It talks to MediaHarvest through files in %LOCALAPPDATA%\MediaHarvest\state,
the folder MediaHarvest keeps its history in (app/app_settings.py). Its log is
%LOCALAPPDATA%\MediaHarvest\helper.log.
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Close,
    [string]$ComposeDir,
    [string]$WslDistro,
    [string]$WslDir,
    [string]$Downloads,
    [int]$Port = 0
)

$ErrorActionPreference = 'Continue'
$AppHome = Join-Path $env:LOCALAPPDATA 'MediaHarvest'
$ConfigPath = Join-Path $AppHome 'helper-config.json'
$StateDir = Join-Path $AppHome 'state'
$LogPath = Join-Path $AppHome 'helper.log'
$HeartbeatPath = Join-Path $StateDir 'helper.json'
$RequestPath = Join-Path $StateDir 'helper-request.json'
$ResponsePath = Join-Path $StateDir 'helper-response.json'
$Container = 'mediaharvest'
$DockerDesktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
$DockerBin = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'
if ((Test-Path $DockerBin) -and ($env:Path -notlike "*$DockerBin*")) { $env:Path = "$env:Path;$DockerBin" }
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$Message) {
    try {
        if ((Test-Path $LogPath) -and (Get-Item $LogPath).Length -gt 1MB) { Remove-Item $LogPath -Force }
        [System.IO.File]::AppendAllText($LogPath, ('{0:yyyy-MM-dd HH:mm:ss}  {1}{2}' -f (Get-Date), $Message, "`r`n"), $Utf8)
    } catch {}
}

function Show-Error([string]$Message) {
    Write-Log "ERROR $Message"
    Add-Type -AssemblyName PresentationFramework
    [void][System.Windows.MessageBox]::Show($Message, 'MediaHarvest', 'OK', 'Error')
}

function Read-Json([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    try { return [System.IO.File]::ReadAllText($Path) | ConvertFrom-Json } catch { return $null }
}

function Write-Json([string]$Path, $Data) {
    # Written beside, then moved over, so MediaHarvest never reads half a file.
    $tmp = "$Path.$PID.tmp"
    [System.IO.File]::WriteAllText($tmp, ($Data | ConvertTo-Json -Depth 5), $Utf8)
    Move-Item -Force $tmp $Path
}

function Get-Config {
    $config = Read-Json $ConfigPath
    if (-not $config) {
        Show-Error "MediaHarvest is not set up on this computer yet. Run its installer, or run this script with -Install."
        exit 1
    }
    return $config
}

function Save-Config($Config) { Write-Json $ConfigPath $Config }

function Get-Url($Config) { "http://localhost:$($Config.port)" }

function Test-Docker {
    docker info *> $null
    return $LASTEXITCODE -eq 0
}

function Test-Url([string]$Url) {
    try { Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}

function Test-AppRunning {
    $running = docker inspect -f '{{.State.Running}}' $Container 2>$null
    return $running -eq 'true'
}

function ConvertTo-WslPath([string]$Path) {
    if ($Path -match '^([A-Za-z]):[\\/]?(.*)$') {
        return '/mnt/' + $Matches[1].ToLower() + '/' + ($Matches[2] -replace '\\', '/')
    }
    return $Path
}

function Get-ComposeVariables($Config) {
    # The folders, as docker compose wants them: docker-compose.yml mounts
    # MEDIAHARVEST_STATE at /state, MEDIAHARVEST_MUSIC at /music and
    # MEDIAHARVEST_TEMP at /temp. These win over the same names in .env.
    $inWsl = [bool]$Config.wslDistro
    $convert = { param($p) if ($inWsl) { ConvertTo-WslPath $p } else { $p } }
    $folders = $Config.folders
    $vars = [ordered]@{
        MEDIAHARVEST_DOWNLOADS = & $convert $folders.downloads
        MEDIAHARVEST_STATE     = & $convert $StateDir
    }
    if ($folders.music) {
        $vars.MEDIAHARVEST_MUSIC = & $convert $folders.music
        $vars.MEDIAHARVEST_MUSIC_DIR = '/music'
    }
    if ($folders.temp) {
        $vars.MEDIAHARVEST_TEMP = & $convert $folders.temp
        $vars.MEDIAHARVEST_TEMP_DIR = '/temp'
    }
    return $vars
}

function Invoke-Compose($Config, [string[]]$ComposeArgs) {
    $vars = Get-ComposeVariables $Config
    if ($Config.wslDistro) {
        $envArgs = @($vars.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" })
        $output = & wsl.exe -d $Config.wslDistro --cd $Config.wslDir --exec env @envArgs docker compose @ComposeArgs 2>&1 | ForEach-Object { "$_" }
    } else {
        foreach ($pair in $vars.GetEnumerator()) { Set-Item -Path "env:$($pair.Key)" -Value $pair.Value }
        Push-Location $Config.composeDir
        try { $output = & docker compose @ComposeArgs 2>&1 | ForEach-Object { "$_" } } finally { Pop-Location }
    }
    $code = $LASTEXITCODE
    Write-Log ("docker compose {0}: exit {1}: {2}" -f ($ComposeArgs -join ' '), $code, (($output -join ' ') -replace '\s+', ' ').Trim())
    return $code -eq 0
}

function Test-Folders($Folders) {
    # Make each folder; the reason it cannot be used, or $null.
    foreach ($kind in 'downloads', 'music', 'temp') {
        $path = [string]$Folders.$kind
        if (-not $path) {
            if ($kind -eq 'downloads') { return 'Choose a download folder.' }
            continue
        }
        if ($path -notmatch '^[A-Za-z]:\\') { return "$path is not a full folder path, like D:\Videos." }
        if (-not (Test-Path ($path.Substring(0, 3)))) { return "Drive $($path.Substring(0, 2)) is not on this computer." }
        try { New-Item -ItemType Directory -Force -Path $path -ErrorAction Stop | Out-Null }
        catch { return "Could not make the folder $path." }
    }
    return $null
}

function Move-OldState($Config) {
    # Before this helper, the history lived in <download folder>\.metube.
    $old = Join-Path $Config.folders.downloads '.metube'
    $known = 'queue.json', 'completed.json', 'pending.json'
    $hasState = @(Get-ChildItem -Path $StateDir -File -ErrorAction SilentlyContinue | Where-Object { $known -contains $_.Name }).Count -gt 0
    if ($hasState -or -not (Test-Path $old)) { return }
    if (Test-Docker) { Invoke-Compose $Config @('stop') | Out-Null }
    Get-ChildItem -Force -Path $old | Move-Item -Destination $StateDir -Force
    Remove-Item -Force -Recurse $old -ErrorAction SilentlyContinue
    Write-Log "Moved the download history from $old to $StateDir"
}

function Write-Heartbeat($Config) {
    Write-Json $HeartbeatPath @{
        heartbeat = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000
        folders   = $Config.folders
        pid       = $PID
    }
}

function Test-Mounts($Config) {
    # After Docker restarts, the container can lose sight of a Windows folder
    # (it then looks empty). A marker file shows whether it still sees it.
    $marker = Join-Path $Config.folders.downloads '.mediaharvest-check'
    try { [System.IO.File]::WriteAllText($marker, 'check') } catch { return $true }
    docker exec $Container sh -c 'test -e /downloads/.mediaharvest-check && test -e /state/helper.json' *> $null
    $ok = $LASTEXITCODE -eq 0
    Remove-Item -Force $marker -ErrorAction SilentlyContinue
    return $ok
}

function Start-MediaHarvest($Config) {
    if (-not (Test-Docker)) {
        if (-not (Test-Path $DockerDesktop)) { Show-Error 'Docker Desktop is not installed. MediaHarvest runs in it.'; exit 1 }
        Write-Log 'Starting Docker Desktop'
        Start-Process $DockerDesktop
        $deadline = (Get-Date).AddMinutes(3)
        while (-not (Test-Docker)) {
            if ((Get-Date) -gt $deadline) {
                Show-Error 'Docker Desktop did not start within 3 minutes. Open it, wait for "Engine running", then open MediaHarvest again.'
                exit 1
            }
            Start-Sleep -Seconds 3
        }
    }
    $problem = Test-Folders $Config.folders
    if ($problem) { Show-Error "$problem Change it in $ConfigPath."; exit 1 }
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    Move-OldState $Config
    Write-Heartbeat $Config
    # The WSL side of Docker can lag a few seconds behind the engine.
    $started = $false
    for ($i = 0; $i -lt 10 -and -not $started; $i++) {
        $started = Invoke-Compose $Config @('up', '-d')
        if (-not $started) { Start-Sleep -Seconds 3 }
    }
    if (-not $started) { Show-Error "MediaHarvest could not start. The details are in $LogPath."; exit 1 }
    if (-not (Test-Mounts $Config)) {
        Write-Log 'The container could not see its folders; recreating it'
        Invoke-Compose $Config @('up', '-d', '--force-recreate') | Out-Null
    }
}

function Stop-MediaHarvest($Config) {
    if (-not (Test-Docker)) { return }
    Invoke-Compose $Config @('stop') | Out-Null
    $others = @(docker ps -q 2>$null | Where-Object { $_ })
    if ($others.Count -gt 0) {
        Write-Log "Docker Desktop stays open: $($others.Count) other containers are running"
        return
    }
    Write-Log 'Closing Docker Desktop'
    docker desktop stop *> $null
    if ($LASTEXITCODE -ne 0) {
        Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue | Stop-Process -Force
    }
}

function Select-Folder([string]$Current, [string]$Kind) {
    Add-Type -AssemblyName System.Windows.Forms
    $names = @{ downloads = 'download'; music = 'music'; temp = 'temporary files' }
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Choose the $($names[$Kind]) folder for MediaHarvest"
    $dialog.ShowNewFolderButton = $true
    if ($Current -and (Test-Path $Current)) { $dialog.SelectedPath = $Current }
    # An invisible window on top, so the picker opens in front of the browser.
    $owner = New-Object System.Windows.Forms.Form
    $owner.TopMost = $true
    $owner.ShowInTaskbar = $false
    $owner.Opacity = 0
    $owner.StartPosition = 'CenterScreen'
    $owner.Show()
    $owner.Activate()
    try {
        if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { return $dialog.SelectedPath }
        return $null
    } finally {
        $owner.Dispose()
        $dialog.Dispose()
    }
}

function Invoke-Request($Config, $Request) {
    switch ([string]$Request.action) {
        'close' {
            Write-Json $ResponsePath @{ id = $Request.id; ok = $true }
            Write-Log 'Close asked from the page'
            Stop-MediaHarvest $Config
            return 'exit'
        }
        'browse' {
            $path = Select-Folder ([string]$Request.current) ([string]$Request.kind)
            Write-Json $ResponsePath @{ id = $Request.id; path = $path }
        }
        'restart' {
            $folders = [pscustomobject]@{
                downloads = [string]$Request.folders.downloads
                music     = [string]$Request.folders.music
                temp      = [string]$Request.folders.temp
            }
            $problem = Test-Folders $folders
            if ($problem) {
                Write-Json $ResponsePath @{ id = $Request.id; ok = $false; error = $problem }
                return
            }
            Write-Json $ResponsePath @{ id = $Request.id; ok = $true }
            $previous = $Config.folders
            $Config.folders = $folders
            Save-Config $Config
            Write-Heartbeat $Config
            Write-Log "Restarting with folders $($folders | ConvertTo-Json -Compress)"
            Start-Sleep -Seconds 1  # let the page get its answer first
            if (-not (Invoke-Compose $Config @('up', '-d', '--force-recreate'))) {
                $Config.folders = $previous
                Save-Config $Config
                Write-Heartbeat $Config
                Invoke-Compose $Config @('up', '-d', '--force-recreate') | Out-Null
                Show-Error "MediaHarvest could not use those folders and went back to the ones before. The details are in $LogPath."
            }
        }
        default { Write-Log "Unknown request: $($Request.action)" }
    }
}

function Watch-Requests($Config) {
    $tick = 0
    $missing = 0
    while ($true) {
        Write-Heartbeat $Config
        $request = Read-Json $RequestPath
        if ($request) {
            Remove-Item -Force $RequestPath -ErrorAction SilentlyContinue
            $age = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - [double]$request.time
            # Requests from before a sleep or a crash are not acted on.
            if ([math]::Abs($age) -lt 120 -and (Invoke-Request $Config $request) -eq 'exit') { return }
        }
        $tick++
        if ($tick % 5 -eq 0) {
            if (Test-AppRunning) { $missing = 0 } else { $missing++ }
            if ($missing -ge 2) { Write-Log 'MediaHarvest is not running any more'; return }
        }
        Start-Sleep -Seconds 3
    }
}

function New-Shortcut([string]$Name, [string]$Arguments, [string]$Description) {
    $script = Join-Path $AppHome 'MediaHarvest.ps1'
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) "$Name.lnk"))
    $link.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $link.Arguments = ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" $Arguments").Trim()
    $link.WorkingDirectory = $AppHome
    $link.IconLocation = Join-Path $AppHome 'mediaharvest.ico'
    $link.Description = $Description
    $link.WindowStyle = 7
    $link.Save()
}

# --- Install ----------------------------------------------------------------
if ($Install) {
    if (-not $ComposeDir -and -not ($WslDistro -and $WslDir)) {
        Write-Host 'Give -ComposeDir <folder>, or -WslDistro <name> and -WslDir <path>.' -ForegroundColor Red
        exit 1
    }
    New-Item -ItemType Directory -Force -Path $AppHome, $StateDir | Out-Null
    $old = Read-Json $ConfigPath
    if ($old -and $old.folders) {
        $folders = $old.folders
    } else {
        $first = if ($Downloads) { $Downloads } else { Join-Path $env:USERPROFILE 'Downloads\MediaHarvest' }
        $folders = [pscustomobject]@{ downloads = $first; music = ''; temp = '' }
    }
    $savedPort = if ($Port) { $Port } elseif ($old -and $old.port) { $old.port } else { 8081 }
    Save-Config ([pscustomobject]@{
        composeDir = $ComposeDir
        wslDistro  = $WslDistro
        wslDir     = $WslDir
        port       = $savedPort
        folders    = $folders
    })
    $target = Join-Path $AppHome 'MediaHarvest.ps1'
    if ($PSCommandPath -ne $target) { Copy-Item -Force $PSCommandPath $target }
    $icon = Join-Path $PSScriptRoot 'mediaharvest.ico'
    if ((Test-Path $icon) -and ($PSScriptRoot -ne $AppHome)) { Copy-Item -Force $icon (Join-Path $AppHome 'mediaharvest.ico') }
    New-Shortcut 'MediaHarvest' '' 'Open MediaHarvest'
    # Closing is the power button in the page; older installs had a shortcut for it.
    $oldClose = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Close MediaHarvest.lnk'
    if (Test-Path $oldClose) { Remove-Item -Force $oldClose }
    Write-Log 'Installed the helper and the desktop shortcut'
    Write-Host 'The desktop now has "MediaHarvest". Close it with the power button at the top of the page.'
    exit 0
}

$config = Get-Config

# --- Close ------------------------------------------------------------------
if ($Close) {
    Write-Log 'Close from the desktop shortcut'
    Stop-MediaHarvest $config
    exit 0
}

# --- Open -------------------------------------------------------------------
$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Local\MediaHarvestHelper', [ref]$created)
if (-not $created) {
    # A helper is already running. If MediaHarvest answers, just show it;
    # otherwise that helper is on its way out, so wait for it.
    if (Test-Url (Get-Url $config)) { Start-Process (Get-Url $config); exit 0 }
    try { $created = $mutex.WaitOne(45000) } catch [System.Threading.AbandonedMutexException] { $created = $true }
    if (-not $created) { Show-Error 'MediaHarvest is still closing. Try again in a minute.'; exit 1 }
}

try {
    Write-Log 'Opening MediaHarvest'
    Start-MediaHarvest $config
    $url = Get-Url $config
    $deadline = (Get-Date).AddSeconds(90)
    while (-not (Test-Url $url)) {
        if ((Get-Date) -gt $deadline) { Show-Error "MediaHarvest started but $url did not answer within 90 seconds."; exit 1 }
        Write-Heartbeat $config
        Start-Sleep -Seconds 2
    }
    Start-Process $url
    Watch-Requests $config
} finally {
    Remove-Item -Force $HeartbeatPath -ErrorAction SilentlyContinue
    Write-Log 'Helper stopped'
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
