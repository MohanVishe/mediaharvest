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
    environment:
      PUID: `${MEDIAHARVEST_UID:-1000}
      PGID: `${MEDIAHARVEST_GID:-1000}
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

    $url = "http://localhost:$Port"
    Write-Host ''
    Write-Host "MediaHarvest is running: $url" -ForegroundColor Green
    Write-Host "Downloads are saved in:  $Downloads"
    Write-Host ''
    Write-Host "In $Dir :"
    Write-Host '  Update:     docker compose pull; docker compose up -d'
    Write-Host '  Stop:       docker compose down'
    Write-Host '  Settings:   edit .env, then docker compose up -d'
    Write-Host "  Uninstall:  docker compose down --rmi all, then delete $Dir"
    Start-Process $url
}

Install-MediaHarvest
