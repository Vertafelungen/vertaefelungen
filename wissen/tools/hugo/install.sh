#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="${SCRIPT_DIR}/VERSION"

if [[ ! -f "${VERSION_FILE}" ]]; then
  echo "VERSION file not found at ${VERSION_FILE}" >&2
  exit 1
fi

VERSION="$(cat "${VERSION_FILE}")"

OS_RAW="$(uname -s)"
ARCH_RAW="$(uname -m)"

case "${OS_RAW}" in
  Linux) OS="linux" ;;
  Darwin) OS="darwin" ;;
  *)
    echo "Unsupported OS: ${OS_RAW}" >&2
    exit 1
    ;;
esac

case "${ARCH_RAW}" in
  x86_64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *)
    echo "Unsupported ARCH: ${ARCH_RAW}" >&2
    exit 1
    ;;
esac

DEST_DIR="${SCRIPT_DIR}/${OS}-${ARCH}"
DEST_BIN="${DEST_DIR}/hugo"

if [[ -x "${DEST_BIN}" ]]; then
  "${DEST_BIN}" version
  exit 0
fi

TARBALL="hugo_extended_${VERSION}_${OS}-${ARCH}.tar.gz"
URL="https://github.com/gohugoio/hugo/releases/download/v${VERSION}/${TARBALL}"
CHECKSUMS_URL="https://github.com/gohugoio/hugo/releases/download/v${VERSION}/hugo_${VERSION}_checksums.txt"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

CHECKSUMS_FILE="${TMP_DIR}/checksums.txt"
TARBALL_PATH="${TMP_DIR}/${TARBALL}"

fetch() {
  local url="$1"
  local output="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "${url}" -o "${output}"
    return
  fi

  if command -v wget >/dev/null 2>&1; then
    wget -qO "${output}" "${url}"
    return
  fi

  echo "Neither curl nor wget is available for downloads." >&2
  exit 1
}

echo "Downloading checksums from ${CHECKSUMS_URL}"
fetch "${CHECKSUMS_URL}" "${CHECKSUMS_FILE}"

EXPECTED_SHA="$(grep " ${TARBALL}$" "${CHECKSUMS_FILE}" | awk '{print $1}')"
if [[ -z "${EXPECTED_SHA}" ]]; then
  echo "Checksum for ${TARBALL} not found in ${CHECKSUMS_URL}" >&2
  exit 1
fi

echo "Downloading ${URL}"
fetch "${URL}" "${TARBALL_PATH}"

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA="$(sha256sum "${TARBALL_PATH}" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  ACTUAL_SHA="$(shasum -a 256 "${TARBALL_PATH}" | awk '{print $1}')"
else
  echo "No SHA256 tool found (sha256sum or shasum)." >&2
  exit 1
fi

if [[ "${EXPECTED_SHA}" != "${ACTUAL_SHA}" ]]; then
  echo "Checksum mismatch for ${TARBALL}" >&2
  echo "Expected: ${EXPECTED_SHA}" >&2
  echo "Actual:   ${ACTUAL_SHA}" >&2
  exit 1
fi

echo "Checksum verified for ${TARBALL}"

mkdir -p "${DEST_DIR}"
tar -xzf "${TARBALL_PATH}" -C "${TMP_DIR}"

if [[ ! -f "${TMP_DIR}/hugo" ]]; then
  echo "Hugo binary not found in tarball." >&2
  exit 1
fi

cp "${TMP_DIR}/hugo" "${DEST_BIN}"
chmod +x "${DEST_BIN}"

"${DEST_BIN}" version
