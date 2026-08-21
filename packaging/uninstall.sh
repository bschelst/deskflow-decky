#!/usr/bin/env bash
#
# Remove the Deskflow helper and the state this project created.
#
# Says what it will delete before deleting it: the certificate in particular cannot be
# recovered, and removing it forces re-pairing with every server that trusted this Deck.
#
set -Eeuo pipefail

APP_ID="io.github.bschelst.DeskflowDeck"
PLUGIN_NAME="Deskflow Decky"
DECKY_HOME="${DECKY_HOME:-$HOME/homebrew}"

SETTINGS_DIR="$DECKY_HOME/settings/$PLUGIN_NAME"
RUNTIME_DIR="$DECKY_HOME/data/$PLUGIN_NAME"
LOG_DIR="$DECKY_HOME/logs/$PLUGIN_NAME"

info() { printf '%s\n' "$1"; }

info "This will remove:"
info "  - the flatpak $APP_ID (user scope)"
info "  - $SETTINGS_DIR   (settings, TLS certificate, trusted fingerprints)"
info "  - $RUNTIME_DIR    (generated config, diagnostics)"
info "  - $LOG_DIR        (logs)"
info ""
info "The TLS certificate cannot be recovered. Removing it means every Deskflow"
info "server that trusted this Deck will ask you to pair again."
info ""

if [[ "${1:-}" != "--yes" ]]; then
    read -r -p "Continue? [y/N] " reply
    [[ "$reply" == "y" || "$reply" == "Y" ]] || { info "Cancelled."; exit 0; }
fi

if flatpak info --user "$APP_ID" >/dev/null 2>&1; then
    info "Stopping the helper..."
    flatpak kill "$APP_ID" 2>/dev/null || true
    info "Removing the flatpak..."
    flatpak uninstall --user --assumeyes --noninteractive "$APP_ID" || \
        printf 'warning: flatpak uninstall failed; remove it manually\n' >&2
else
    info "Flatpak $APP_ID is not installed."
fi

for dir in "$SETTINGS_DIR" "$RUNTIME_DIR" "$LOG_DIR"; do
    if [[ -d "$dir" ]]; then
        info "Removing $dir"
        rm -rf -- "$dir"
    fi
done

info ""
info "Done. The plugin itself is removed from Decky's own plugin list."
