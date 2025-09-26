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
if (-not $YtDlpVersion) { $YtDlpVersion = '2025.09.05' }

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

if ($doBuild) {
  Write-Host "[build] Building $imageRef (yt-dlp $YtDlpVersion)" -ForegroundColor Cyan
  docker build `
    --build-arg YT_DLP_VERSION=$YtDlpVersion `
    -t $imageRef .
}

if ($doPush) {
  Write-Host "[push] Pushing $imageRef" -ForegroundColor Cyan
  docker push $imageRef
}

Write-Host "Done." -ForegroundColor Green