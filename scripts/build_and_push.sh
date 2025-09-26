#!/usr/bin/env bash
set -euo pipefail

REGISTRY_HOST=${REGISTRY_HOST:-192.168.2.5:5000}
IMAGE_NAME=${IMAGE_NAME:-music-downloader}
YT_DLP_VERSION=${YT_DLP_VERSION:-2025.09.05}

VERSION_FILE="$(dirname "$0")/../VERSION"
if [ -z "${IMAGE_VERSION:-}" ]; then
  if [ -f "$VERSION_FILE" ]; then
    IMAGE_VERSION=$(tr -d '\r\n' < "$VERSION_FILE")
  else
    echo "[error] VERSION file not found and IMAGE_VERSION not provided" >&2
    exit 1
  fi
fi

if [ -z "$IMAGE_VERSION" ]; then
  echo "[error] IMAGE_VERSION is empty" >&2
  exit 1
fi

IMAGE_REF="${REGISTRY_HOST}/${IMAGE_NAME}:${IMAGE_VERSION}"

DO_BUILD=true
DO_PUSH=true
while [ $# -gt 0 ]; do
  case "$1" in
    --build-only)
      DO_PUSH=false
      ;;
    --push-only)
      DO_BUILD=false
      ;;
    --help|-h)
      cat <<'USAGE'
Usage: build_and_push.sh [--build-only|--push-only]

Environment variables:
  REGISTRY_HOST   (default 192.168.2.5:5000)
  IMAGE_NAME      (default music-downloader)
  IMAGE_VERSION   (defaults to contents of VERSION file)
  YT_DLP_VERSION  (default 2025.09.05)
USAGE
      exit 0
      ;;
  esac
  shift
done

IMAGE_REF="${REGISTRY_HOST}/${IMAGE_NAME}:${IMAGE_VERSION}"
LATEST_REF="${REGISTRY_HOST}/${IMAGE_NAME}:latest"

if [ "$DO_BUILD" = true ]; then
  echo "[build] Building ${IMAGE_REF} (yt-dlp ${YT_DLP_VERSION})"
  docker build \
    --build-arg YT_DLP_VERSION="${YT_DLP_VERSION}" \
    -t "${IMAGE_REF}" \
    -t "${LATEST_REF}" .
fi

if [ "$DO_PUSH" = true ]; then
  echo "[push] Pushing ${IMAGE_REF}"
  docker push "${IMAGE_REF}"
  echo "[push] Pushing ${LATEST_REF}"
  docker push "${LATEST_REF}"
fi

echo "Done."