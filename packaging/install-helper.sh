#!/usr/bin/env bash
#
# Install or update the Deskflow helper flatpak at user scope.
#
# User scope on purpose: a system-scope install needs root and does not survive SteamOS
# updates cleanly. Nothing here writes to the immutable system partition.
#
# Usage:
#   ./install-helper.sh <bundle.flatpak> [SHA256SUMS]
#
set -Eeuo pipefail

APP_ID="org.schelstraete.DeskFlowDecky"

die() { printf 'error: %s\n' "$1" >&2; exit 1; }
info() { printf '%s\n' "$1"; }

bundle="${1:-}"
sumsfile="${2:-}"

[[ -n "$bundle" ]] || die "usage: $0 <bundle.flatpak> [SHA256SUMS]"
[[ -f "$bundle" ]] || die "bundle not found: $bundle"
command -v flatpak >/dev/null 2>&1 || die "flatpak is not installed"

# --------------------------------------------------------------------- verify

# Verify before installing, never after: an unverified bundle must not be unpacked at
# all. If no checksum file is supplied the script refuses rather than proceeding
# quietly, because "no checksum" and "checksum matched" must not look the same.
if [[ -z "$sumsfile" ]]; then
    sumsfile="$(dirname "$bundle")/SHA256SUMS"
fi
[[ -f "$sumsfile" ]] || die "checksum file not found: $sumsfile (refusing to install unverified)"

info "Verifying $(basename "$bundle") against $(basename "$sumsfile")..."
(
    cd "$(dirname "$bundle")"
    sha256sum -c --ignore-missing "$(basename "$sumsfile")" 2>/dev/null \
        | grep -q "$(basename "$bundle"): OK"
) || die "checksum mismatch or bundle not listed - refusing to install"
info "Checksum OK."

# --------------------------------------------------------------------- current state

installed_ref=""
if flatpak info --user --show-ref "$APP_ID" >/dev/null 2>&1; then
    installed_ref="$(flatpak info --user --show-ref "$APP_ID" 2>/dev/null || true)"
    info "Currently installed: $installed_ref"
fi

# --------------------------------------------------------------------- stop, install

if pgrep -f "$APP_ID" >/dev/null 2>&1; then
    info "Stopping the running helper..."
    flatpak kill "$APP_ID" 2>/dev/null || true
    # Give it a moment to release its devices and drop any held keys.
    for _ in 1 2 3 4 5; do
        pgrep -f "$APP_ID" >/dev/null 2>&1 || break
        sleep 1
    done
fi

info "Installing $APP_ID at user scope..."
if ! flatpak install --user --bundle --assumeyes --noninteractive "$bundle"; then
    die "install failed; the previously installed version (if any) is untouched"
fi

# --------------------------------------------------------------------- verify install

if ! flatpak info --user --show-ref "$APP_ID" >/dev/null 2>&1; then
    die "install reported success but $APP_ID is not present"
fi

info "Verifying the helper starts..."
if ! flatpak run --user --command=deskflow-core "$APP_ID" --version >/dev/null 2>&1; then
    printf 'warning: the helper did not report a version.\n' >&2
    if [[ -n "$installed_ref" ]]; then
        printf 'The previous version was %s; reinstall it with its own bundle to roll back.\n' \
            "$installed_ref" >&2
    fi
    die "helper verification failed"
fi

new_ref="$(flatpak info --user --show-ref "$APP_ID" 2>/dev/null || echo "$APP_ID")"
info "Installed and verified: $new_ref"
info ""
info "Permissions granted by the bundle: network, ipc, wayland, fallback-x11."
info "Access to Gamescope's input socket is granted per-launch by the plugin,"
info "scoped to the single discovered socket path."
