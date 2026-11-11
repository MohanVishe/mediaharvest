# MediaHarvest installer for Windows. Needs Docker Desktop, started.
#
#   irm https://raw.githubusercontent.com/MohanVishe/mediaharvest/main/install.ps1 | iex
#
# Or download it, read it, then run:  powershell -ExecutionPolicy Bypass -File install.ps1
#
# It makes one folder (default %USERPROFILE%\MediaHarvest) holding compose.yaml
# and .env, pulls the published image, starts it on http://localhost:8081
# (this computer only) and opens it. Downloads go to Downloads\MediaHarvest.
# Run it again at any time to update. Change the defaults with the
# environment variables MEDIAHARVEST_DIR, MEDIAHARVEST_PORT, MEDIAHARVEST_DOWNLOADS.
# MEDIAHARVEST_PULL=0 skips the download and uses an image already on this
# computer (offline machines, or one built from source).

function Install-MediaHarvest {
    $Image = 'ghcr.io/mohanvishe/mediaharvest'
    $Dir = if ($env:MEDIAHARVEST_DIR) { $env:MEDIAHARVEST_DIR } else { Join-Path $env:USERPROFILE 'MediaHarvest' }
    $Port = if ($env:MEDIAHARVEST_PORT) { $env:MEDIAHARVEST_PORT } else { '8081' }
    $Downloads = if ($env:MEDIAHARVEST_DOWNLOADS) { $env:MEDIAHARVEST_DOWNLOADS } else { Join-Path $env:USERPROFILE 'Downloads\MediaHarvest' }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host 'Docker Desktop is not installed. Get it from https://www.docker.com/products/docker-desktop/ and run this again.' -ForegroundColor Red
        return
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Docker Desktop is not running. Start it, wait until it says "Engine running", and run this again.' -ForegroundColor Red
        return
    }

    New-Item -ItemType Directory -Force -Path $Dir, $Downloads | Out-Null
    $utf8 = New-Object System.Text.UTF8Encoding($false)

    # Settings are written once; later runs keep your edits.
    $envFile = Join-Path $Dir '.env'
    if (-not (Test-Path $envFile)) {
        $settings = @(
            "MEDIAHARVEST_DOWNLOADS=$($Downloads -replace '\\', '/')",
            "MEDIAHARVEST_PORT=$Port",
            'MEDIAHARVEST_TAG=latest',
            'MEDIAHARVEST_UID=1000',
            'MEDIAHARVEST_GID=1000'
        ) -join "`n"
        [System.IO.File]::WriteAllText($envFile, "$settings`n", $utf8)
    }
    $saved = (Get-Content $envFile | Where-Object { $_ -like 'MEDIAHARVEST_PORT=*' }) -replace '^MEDIAHARVEST_PORT=', ''
    if ($saved) { $Port = $saved }

    # Same service as the repo's docker-compose.yml, without the source build.
    $compose = @"
services:
  mediaharvest:
    image: ${Image}:`${MEDIAHARVEST_TAG:-latest}
    container_name: mediaharvest
    restart: unless-stopped
    ports:
      - "127.0.0.1:`${MEDIAHARVEST_PORT:-8081}:8081"
    volumes:
      - "`${MEDIAHARVEST_DOWNLOADS:-./downloads}:/downloads"
      - "`${MEDIAHARVEST_STATE:-`${MEDIAHARVEST_DOWNLOADS:-./downloads}/.metube}:/state"
      - "`${MEDIAHARVEST_MUSIC:-`${MEDIAHARVEST_DOWNLOADS:-./downloads}}:/music"
      - "`${MEDIAHARVEST_TEMP:-`${MEDIAHARVEST_DOWNLOADS:-./downloads}}:/temp"
    environment:
      PUID: `${MEDIAHARVEST_UID:-1000}
      PGID: `${MEDIAHARVEST_GID:-1000}
      STATE_DIR: /state
      AUDIO_DOWNLOAD_DIR: `${MEDIAHARVEST_MUSIC_DIR:-/downloads}
      TEMP_DIR: `${MEDIAHARVEST_TEMP_DIR:-/downloads}
      ALLOW_YTDL_OPTIONS_OVERRIDES: "false"
      DEFAULT_THEME: "auto"
"@
    [System.IO.File]::WriteAllText((Join-Path $Dir 'compose.yaml'), ($compose -replace "`r`n", "`n") + "`n", $utf8)

    Push-Location $Dir
    try {
        if ($env:MEDIAHARVEST_PULL -ne '0') {
            Write-Host 'Downloading MediaHarvest...'
            docker compose pull
            if ($LASTEXITCODE -ne 0) { Write-Host 'Could not download the image.' -ForegroundColor Red; return }
        }
        # An NVIDIA GPU makes the "Any device" compression faster. Use it
        # only when Docker can really reach it; otherwise the CPU does the work.
        if ($env:MEDIAHARVEST_GPU -ne '0' -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
            docker run --rm --gpus all --entrypoint true $Image *> $null
            if ($LASTEXITCODE -eq 0) {
                $gpu = @"
      NVIDIA_DRIVER_CAPABILITIES: "compute,utility,video"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
"@
                [System.IO.File]::AppendAllText((Join-Path $Dir 'compose.yaml'), ($gpu -replace "`r`n", "`n") + "`n", $utf8)
                Write-Host 'NVIDIA graphics card found: MediaHarvest will use it to compress videos.'
            }
        }
        docker compose up -d
        if ($LASTEXITCODE -ne 0) { Write-Host 'Could not start MediaHarvest.' -ForegroundColor Red; return }
    } finally {
        Pop-Location
    }

    Write-Host -NoNewline 'Starting'
    for ($i = 0; $i -lt 45; $i++) {
        $state = docker inspect -f '{{.State.Health.Status}}' mediaharvest 2>$null
        if ($state -eq 'healthy') { break }
        Write-Host -NoNewline '.'
        Start-Sleep -Seconds 2
    }
    Write-Host ''

    # The Windows helper: desktop shortcuts to open and close MediaHarvest,
    # and what the Settings page needs to change folders and close Docker.
    $helper = Join-Path $Dir 'windows\MediaHarvest.ps1'
    New-Item -ItemType Directory -Force -Path (Split-Path $helper) | Out-Null
    $source = if ($PSScriptRoot) { Join-Path $PSScriptRoot 'windows' } else { $null }
    foreach ($name in 'MediaHarvest.ps1', 'mediaharvest.ico') {
        $target = Join-Path (Split-Path $helper) $name
        if ($source -and (Test-Path (Join-Path $source $name))) {
            Copy-Item -Force (Join-Path $source $name) $target
        } else {
            try { Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/MohanVishe/mediaharvest/main/windows/$name" -OutFile $target }
            catch { Write-Host "Could not download $name; the desktop shortcuts are skipped." -ForegroundColor Yellow }
        }
    }
    $url = "http://localhost:$Port"
    $shortcuts = $false
    if (Test-Path $helper) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $helper -Install -ComposeDir $Dir -Downloads $Downloads -Port $Port
        $shortcuts = $LASTEXITCODE -eq 0
    }

    Write-Host ''
    Write-Host "MediaHarvest is running: $url" -ForegroundColor Green
    Write-Host "Downloads are saved in:  $Downloads"
    Write-Host ''
    if ($shortcuts) {
        Write-Host 'Open it with "MediaHarvest" on the desktop; close it with the power button at the top of the page.'
        Write-Host 'Folders and file settings: the gear button next to it.'
        Write-Host ''
    }
    Write-Host "In $Dir :"
    Write-Host '  Update:     docker compose pull; docker compose up -d'
    Write-Host '  Stop:       docker compose down'
    Write-Host '  Settings:   edit .env, then docker compose up -d'
    Write-Host "  Uninstall:  docker compose down --rmi all, then delete $Dir and %LOCALAPPDATA%\MediaHarvest"
    if ($shortcuts) {
        Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', (Join-Path $env:LOCALAPPDATA 'MediaHarvest\MediaHarvest.ps1'))
    } else {
        Start-Process $url
    }
}

Install-MediaHarvest
