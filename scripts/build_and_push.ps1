Param(
  [string]$RegistryHost = $env:REGISTRY_HOST,
  [string]$ImageName = $env:IMAGE_NAME,
  [string]$ImageVersion = $env:IMAGE_VERSION,
  [string]$YtDlpVersion = $env:YT_DLP_VERSION,
  [switch]$BuildOnly,
  [switch]$PushOnly
)

if (-not $RegistryHost) { $RegistryHost = '192.168.2.5:5000' }
if (-not $ImageName) { $ImageName = 'music-downloader' }
# YT_DLP_VERSION: if not set, Dockerfile default is used

if (-not $ImageVersion) {
  $versionFile = Join-Path -Path (Join-Path -Path $PSScriptRoot -ChildPath '..') -ChildPath 'VERSION'
  if (Test-Path $versionFile) {
    $ImageVersion = (Get-Content -Path $versionFile -Raw).Trim()
  } else {
    throw "VERSION file not found and IMAGE_VERSION not provided"
  }
}

if (-not $ImageVersion) {
  throw "IMAGE_VERSION resolved to an empty string"
}

if ($BuildOnly -and $PushOnly) {
  Write-Warning "Both -BuildOnly and -PushOnly specified; running both build and push."
  $BuildOnly = $false
  $PushOnly = $false
}

$doBuild = $true
$doPush = $true
if ($BuildOnly) {
  $doPush = $false
}
elseif ($PushOnly) {
  $doBuild = $false
}

$imageRef = "${RegistryHost}/${ImageName}:${ImageVersion}"
$latestRef = "${RegistryHost}/${ImageName}:latest"

if ($doBuild) {
  Write-Host "[build] Building $imageRef" -ForegroundColor Cyan
  $buildArgs = @('-t', $imageRef, '-t', $latestRef, '.')
  if ($YtDlpVersion) {
    Write-Host "[build] Using yt-dlp version: $YtDlpVersion" -ForegroundColor Yellow
    $buildArgs = @('--build-arg', "YT_DLP_VERSION=$YtDlpVersion") + $buildArgs
  }
  docker build @buildArgs
}

if ($doPush) {
  Write-Host "[push] Pushing $imageRef" -ForegroundColor Cyan
  docker push $imageRef
  Write-Host "[push] Pushing $latestRef" -ForegroundColor Cyan
  docker push $latestRef
}

Write-Host "Done." -ForegroundColor Green