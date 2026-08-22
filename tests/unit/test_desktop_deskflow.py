"""Syncing this Deck's identity into the stock Deskflow desktop app.

Fixture content below is trimmed from the real file read off hardware
(2026-08-22, org.deskflow.deskflow 1.26.0) -- including the Qt-escaped
``screens\\1\\name=`` key and the binary ``@Variant(...)`` blob that a generic INI
parser could mangle, to prove the surgical substitution really does leave them alone.
"""

import pytest
from desktop_deskflow import (
    DESKTOP_APP_ID,
    DESKTOP_DESKTOP_FILE_NAME,
    SyncError,
    autostart_path,
    bootstrap_client_config,
    desktop_client_config_needs_bootstrap,
    desktop_config_path,
    find_exported_desktop_file,
    is_desktop_app_running,
    read_desktop_identity,
    sync_desktop_identity,
    write_autostart_entry,
)

# The exact shape a plain first launch writes -- captured on hardware (2026-08-22) by
# moving the real config aside and launching the flatpak headlessly. No [client]
# section at all: that only appears once a human completes Deskflow's own wizard.
FRESH_LAUNCH_CONFIG = """[core]
computerName=steamdeck
coreMode=0
lastVersion=1.26.0.0

[gui]
logExpanded=true

[internalConfig]
clipboardSharingSize=@Variant(\\0\\0\\0\\x84\\0\\0\\0\\0\\0\\0\\f\\0)
screens\\1\\name=
screens\\size=15
"""

REAL_DESKTOP_FILE = """[Desktop Entry]
Categories=Utility;
Comment=Mouse and keyboard sharing utility
Exec=/usr/bin/flatpak run --branch=master --arch=x86_64 --command=deskflow org.deskflow.deskflow
Icon=org.deskflow.deskflow
Name=Deskflow
Terminal=false
Type=Application
X-Flatpak=org.deskflow.deskflow
"""

REAL_CONFIG = """[client]
remoteHost=bschelst-thinkpad-p70
xdpRestoreToken=18c4bdbf-325c-481f-afc0-fab374a23763

[core]
computerName=steamdeck2
coreMode=1
port=24800

[internalConfig]
clipboardSharingSize=@Variant(\\0\\0\\0\\x84\\0\\0\\0\\0\\0\\0\\f\\0)
screens\\1\\name=
screens\\size=15

[security]
certificate=/home/deck/.var/app/org.deskflow.deskflow/config/Deskflow/tls/deskflow.pem
checkPeerFingerprints=true
keySize=2048
tlsEnabled=true
"""


def write_config(tmp_path, text=REAL_CONFIG, mode=0o644):
    path = tmp_path / "Deskflow.conf"
    path.write_text(text)
    path.chmod(mode)
    return str(path)


# --------------------------------------------------------------------------- path


def test_config_path_uses_the_upstream_app_id():
    path = desktop_config_path("/home/deck")
    assert DESKTOP_APP_ID in path
    assert path == "/home/deck/.var/app/org.deskflow.deskflow/config/Deskflow/Deskflow.conf"


# ---------------------------------------------------------------------- reading


def test_reads_the_current_identity(tmp_path):
    identity = read_desktop_identity(write_config(tmp_path))
    assert identity == {"remote_host": "bschelst-thinkpad-p70", "computer_name": "steamdeck2"}


def test_missing_file_returns_none(tmp_path):
    assert read_desktop_identity(str(tmp_path / "nope.conf")) is None


def test_file_without_the_expected_keys_returns_none(tmp_path):
    path = tmp_path / "Deskflow.conf"
    path.write_text("[core]\nlanguage=en\n")
    assert read_desktop_identity(str(path)) is None


# ---------------------------------------------------------------------- syncing


def test_sync_rewrites_only_the_two_lines(tmp_path):
    path = write_config(tmp_path)
    sync_desktop_identity(path, "new-server", "steamdeck-99")

    text = open(path).read()
    assert "remoteHost=new-server" in text
    assert "computerName=steamdeck-99" in text
    # Everything else -- including the escaped key and the binary blob -- untouched.
    assert "xdpRestoreToken=18c4bdbf-325c-481f-afc0-fab374a23763" in text
    assert "screens\\1\\name=" in text
    assert "clipboardSharingSize=@Variant(" in text
    assert "certificate=/home/deck/.var/app/org.deskflow.deskflow" in text


def test_sync_preserves_file_permissions(tmp_path):
    import os

    path = write_config(tmp_path, mode=0o644)
    sync_desktop_identity(path, "host", "name")
    assert os.stat(path).st_mode & 0o777 == 0o644


def test_sync_raises_when_the_file_is_missing(tmp_path):
    with pytest.raises(SyncError):
        sync_desktop_identity(str(tmp_path / "nope.conf"), "host", "name")


def test_sync_raises_when_the_expected_keys_are_absent(tmp_path):
    path = tmp_path / "Deskflow.conf"
    path.write_text("[core]\nlanguage=en\n")
    with pytest.raises(SyncError):
        sync_desktop_identity(str(path), "host", "name")


@pytest.mark.parametrize("bad", ["evil\nkeySize=1", "evil\r", "evil\x00"])
def test_sync_refuses_a_value_with_a_control_character(tmp_path, bad):
    # A newline in server_host would let a malicious setting inject arbitrary extra
    # lines into a config file that is not even ours.
    path = write_config(tmp_path)
    with pytest.raises(SyncError):
        sync_desktop_identity(path, bad, "name")


def test_sync_returns_the_path(tmp_path):
    path = write_config(tmp_path)
    assert sync_desktop_identity(path, "host", "name") == path


# --------------------------------------------------------------- is the app running


def make_proc(tmp_path, pid, cmdline):
    d = tmp_path / str(pid)
    d.mkdir()
    (d / "cmdline").write_bytes(cmdline.encode())


def test_detects_the_desktop_app_running(tmp_path):
    make_proc(tmp_path, 501, "flatpak\x00run\x00org.deskflow.deskflow\x00")
    assert is_desktop_app_running(proc_root=str(tmp_path)) is True


def test_does_not_confuse_our_own_helper_with_the_desktop_app(tmp_path):
    make_proc(tmp_path, 501, "deskflow-core\x00client\x00org.schelstraete.DeskFlowDecky")
    assert is_desktop_app_running(proc_root=str(tmp_path)) is False


def test_missing_proc_is_not_an_error():
    assert is_desktop_app_running(proc_root="/nonexistent-proc") is False


def test_unreadable_cmdline_is_skipped(tmp_path):
    (tmp_path / "202").mkdir()  # no cmdline file at all
    assert is_desktop_app_running(proc_root=str(tmp_path)) is False


# -------------------------------------------------------------- fresh-install bootstrap


def write_fresh_config(tmp_path, text=FRESH_LAUNCH_CONFIG):
    path = tmp_path / "Deskflow.conf"
    path.write_text(text)
    path.chmod(0o644)
    return str(path)


def test_needs_bootstrap_after_a_plain_first_launch(tmp_path):
    assert desktop_client_config_needs_bootstrap(write_fresh_config(tmp_path)) is True


def test_does_not_need_bootstrap_once_client_is_configured(tmp_path):
    path = write_config(tmp_path)  # the REAL_CONFIG fixture, already has [client]
    assert desktop_client_config_needs_bootstrap(path) is False


def test_does_not_need_bootstrap_when_never_launched_at_all(tmp_path):
    assert desktop_client_config_needs_bootstrap(str(tmp_path / "nope.conf")) is False


def test_bootstrap_adds_a_client_section(tmp_path):
    path = write_fresh_config(tmp_path)
    bootstrap_client_config(path, "new-server", "steamdeck-99")

    text = open(path).read()
    assert "[client]" in text
    assert "remoteHost=new-server" in text
    assert "computerName=steamdeck-99" in text
    assert "coreMode=1" in text
    # Everything from the first-launch bootstrap survives untouched.
    assert "clipboardSharingSize=@Variant(" in text
    assert "screens\\1\\name=" in text


def test_bootstrap_preserves_file_permissions(tmp_path):
    import os

    path = write_fresh_config(tmp_path)
    bootstrap_client_config(path, "host", "name")
    assert os.stat(path).st_mode & 0o777 == 0o644


def test_bootstrap_raises_when_never_launched(tmp_path):
    with pytest.raises(SyncError):
        bootstrap_client_config(str(tmp_path / "nope.conf"), "host", "name")


def test_bootstrap_raises_when_a_client_section_already_exists(tmp_path):
    # That is sync_desktop_identity's job -- bootstrap only handles the empty case.
    path = write_config(tmp_path)  # already has [client]
    with pytest.raises(SyncError):
        bootstrap_client_config(path, "host", "name")


@pytest.mark.parametrize("bad", ["evil\nkeySize=1", "evil\r", "evil\x00"])
def test_bootstrap_refuses_a_value_with_a_control_character(tmp_path, bad):
    path = write_fresh_config(tmp_path)
    with pytest.raises(SyncError):
        bootstrap_client_config(path, bad, "name")


# -------------------------------------------------------------------------- autostart


def test_finds_the_user_scope_export(tmp_path):
    export_dir = tmp_path / ".local" / "share" / "flatpak" / "exports" / "share" / "applications"
    export_dir.mkdir(parents=True)
    (export_dir / DESKTOP_DESKTOP_FILE_NAME).write_text(REAL_DESKTOP_FILE)
    assert find_exported_desktop_file(str(tmp_path)) == str(
        export_dir / DESKTOP_DESKTOP_FILE_NAME
    )


def test_finds_no_export_when_not_installed(tmp_path):
    # An unrelated, real system_export_dir is deliberately never passed here -- this
    # must not depend on what happens to be installed system-wide on the test runner.
    no_system_exports = str(tmp_path / "no-such-system-export-dir")
    assert find_exported_desktop_file(str(tmp_path), no_system_exports) is None


def test_autostart_path_is_under_dot_config(tmp_path):
    path = autostart_path(str(tmp_path))
    assert path == str(tmp_path / ".config" / "autostart" / DESKTOP_DESKTOP_FILE_NAME)


def test_write_autostart_entry_copies_the_real_exported_file(tmp_path):
    export_dir = tmp_path / ".local" / "share" / "flatpak" / "exports" / "share" / "applications"
    export_dir.mkdir(parents=True)
    (export_dir / DESKTOP_DESKTOP_FILE_NAME).write_text(REAL_DESKTOP_FILE)

    written = write_autostart_entry(str(tmp_path))

    assert written == autostart_path(str(tmp_path))
    assert open(written).read() == REAL_DESKTOP_FILE
    # Never hand-built: the source's real Exec= line (with flatpak's own branch/arch
    # choices) must survive verbatim, not something we reconstructed ourselves.
    assert "Exec=/usr/bin/flatpak run --branch=master" in open(written).read()


def test_write_autostart_entry_raises_when_the_app_is_not_installed(tmp_path):
    no_system_exports = str(tmp_path / "no-such-system-export-dir")
    with pytest.raises(SyncError):
        write_autostart_entry(str(tmp_path), no_system_exports)
