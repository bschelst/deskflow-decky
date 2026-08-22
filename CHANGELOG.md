# Changelog

## 0.3.0 — 22 Aug 2026

### What's new

- The plugin can now install, configure, and set up autostart for the stock desktop
  Deskflow app in one click, and sync your server address and screen name between it
  and the plugin in either direction. Handy if you use both Gaming Mode and Desktop
  Mode and dont want to type the server address in twice.
- Gaming Mode and Desktop Mode now actually hand off to each other properly: leaving
  Gaming Mode releases the connection instead of holding the screen name hostage, and
  coming back reconnects automatically instead of needing a manual restart every time.

### Fixes

- Found out mid-session that Gaming Mode detection has been silently broken this
  whole time: it checked an env var that plain doesnt exist on this kind of systemd
  service, so it always though it was in Desktop Mode. Replaced with checking for
  Gamescope's own process, which actually works.
- The "input enabled" toggle in the quick access panel used to just flip a flag that
  nothing read. It now actually starts and stops the helper, since there is no way to
  really pause input without dropping the connection anyway.
- tests/ had snuck into .gitignore by accident, which is a bit of a problem for a
  folder full of tests that are supposed to be committed.

### Other

- Every source file now has an author header.


## 0.2.0 — 22 Aug 2026

### What's new

- Keyboard layot is now independent of the server. Pick your own keyboard language layout in the plugin
  and should remain like this regardless of what OS or layout the server side is running — needed
  a fifth patch that replays physical key positions instead of trusting the server's
  keysyms. Needs a reboot after changing.
- Settings shows a reboot button when a layout change needs Gaming Mode to restart before
  it takes effect, guarded behind a confirm dialog so it doesnt fire by accident.
- Autostart now retries while gamescope's input socket is not up yet, instead of staying
  in error on the first boot every time.

### Fixes

- Reboot now goes through Steam's own restart call instead of systemctl. The plugin
  backend has no permission to reboot directly ("interactive authentication required"),
  but Steam's own power-menu path needs nothing extra.
- Cleared out a pile of ruff lint debt so CI actually passes again.

### Other

- Rewrote the README with a logo and an overview.


## 0.1.0 — 22 Aug 2026

First version that actually works. Keyboard and mouse from my laptop now reach the
Steam Machine in gaming mode, which was the whole point.

### What it does

- Use the keyboard and mouse from another computer on your Deck, also inside gaming
  mode (steam UI, native games, proton games)
- Everything is configured from the Quick Access menu, no ssh needed
- Ships its own patched Deskflow as a flatpak, so it doesnt touch the system

### The patch

Deskflow already had the code to talk to gamescope directly, it just never used it —
both the client and the server pass "use the portal" no matter what, and there is no
portal behind gamescope. So the socket path was unreachable. Two small patches:

- let you pick the backend with an env var (defaults to the old behaviour, so nothing
  changes for anyone else)
- send a sensible screen size when the compositor doesnt report one, and back off
  between reconnects instead of retrying every single second

Both are against v1.26.0 and could go upstream as they are.

### Things that took way too long to figure out

- The helper runs in a flatpak sandbox and can not see decky's folders at all. The
  config was there, so it "loaded" fine and then reported no server configured. That
  one cost an hour.
- Decky runs plugins in a bundled python, and that breaks any normal program you start
  from it. openssl refused to run until the environment was cleaned up.
- Do not pass PATH into the sandbox. It hides /app/bin and then nothing starts.
- Gamescope says its screen is 2147483647 pixels wide. That does not fit in the
  protocol, so the server just droped the connection with a very unhelpful error.
- Killing the helper only killed the wrapper. The real proces kept running and then
  blocked every next start, forever.

### Nice to have bits

- Tells you when the connection drops and when its back, once each, no spam
- Warns you before trusting a server certificate, and says something different if the
  fingerprint changed (that would be someone in the middle)
- Self test that checks the things that actually break: helper installed, socket there,
  server reachable, certificate trusted
- Picks a unique name per machine, because every steam deck and steam machine is called
  "steamdeck" out of the box and two of them fight over it
- Works out the screen size by itself
- Gives up on auto starting if the helper keeps crashing, instead of looping forever

### Getting the pointer back

Scroll Lock locks and unlocks the pointer to whatever screen its on. Deskflow sets that
up by itself, you dont have to configure anything. You can also bind your own key in the
server options with keystroke(alt+shift+l) = lockCursorToScreen(toggle), or start locked
with defaultLockToScreenState = true.

### Known problems

- The mouse cursor is invisible until you click. Thats gamescope hiding it after 3
  seconds, not us. Turning off relativeMouseMoves on the server side might help.
- Server mode only works in desktop mode. Gaming mode has no way to capture input, so
  the plugin refuses instead of pretending.
- Clipboard sharing is in the box but does not work in gaming mode. wl-paste says it
  straight out: "The compositor does not seem to implement wl_data_device_manager".
  Its off by default, and the self test now actually runs wl-paste and shows you that
  message instead of me guessing.
- No drag and drop. Maybe later.
- Not tested with anticheat and I'm not going to.
