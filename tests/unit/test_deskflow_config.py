"""Generation of Deskflow's INI file.

deskflow-core takes no host/port/name flags -- everything arrives through this file,
which makes it a boundary worth defending even though validation runs upstream.
"""

import configparser
import os
import stat

import pytest
from deskflow_config import ConfigError, render_ini, write_config
from validation import DEFAULTS


def client_settings(**overrides):
    settings = dict(DEFAULTS)
    settings.update(mode="client", server_host="desktop.local")
    settings.update(overrides)
    return settings


def parse(text):
    parser = configparser.ConfigParser()
    parser.read_string(text)
    return parser


def test_client_mode_renders_core_mode_one():
    parsed = parse(render_ini(client_settings(), cert_path="/tmp/tls/deskflow.pem"))
    assert parsed["core"]["coreMode"] == "1"


def test_server_mode_renders_core_mode_two():
    settings = dict(DEFAULTS, mode="server", server_host="")
    parsed = parse(render_ini(settings, cert_path="/tmp/tls/deskflow.pem"))
    assert parsed["core"]["coreMode"] == "2"


def test_client_details_are_written():
    parsed = parse(
        render_ini(client_settings(server_port=25000, client_name="deck-1"), cert_path="/c.pem")
    )
    assert parsed["core"]["port"] == "25000"
    assert parsed["core"]["computerName"] == "deck-1"
    assert parsed["client"]["remoteHost"] == "desktop.local"


def test_server_mode_omits_the_client_section():
    settings = dict(DEFAULTS, mode="server", server_host="")
    parsed = parse(render_ini(settings, cert_path="/c.pem"))
    assert not parsed.has_section("client")


def test_security_section_reflects_settings():
    parsed = parse(render_ini(client_settings(), cert_path="/path/deskflow.pem"))
    assert parsed["security"]["tlsEnabled"] == "true"
    assert parsed["security"]["checkPeerFingerprints"] == "true"
    assert parsed["security"]["certificate"] == "/path/deskflow.pem"


def test_tls_disabled_is_rendered_as_false():
    settings = client_settings(tls_enabled=False, check_peer_fingerprints=False)
    parsed = parse(render_ini(settings, cert_path="/c.pem"))
    assert parsed["security"]["tlsEnabled"] == "false"


def test_rendering_is_deterministic():
    settings = client_settings()
    assert render_ini(settings, cert_path="/c.pem") == render_ini(settings, cert_path="/c.pem")


@pytest.mark.parametrize(
    "hostile",
    [
        "host\ncomputerName=evil",
        "host\r\nport=1",
        "host\x00",
        "host\n[security]\ntlsEnabled=false",
    ],
)
def test_injection_attempts_are_refused_rather_than_escaped(hostile):
    # Defence in depth: validation should already have rejected these, so reaching
    # here means something upstream failed and the safe move is to refuse outright.
    with pytest.raises(ConfigError):
        render_ini(client_settings(server_host=hostile), cert_path="/c.pem")


def test_injection_through_the_certificate_path_is_refused():
    with pytest.raises(ConfigError):
        render_ini(client_settings(), cert_path="/c.pem\ntlsEnabled=false")


def test_write_config_creates_the_file_readable_only_by_its_owner(tmp_path):
    target = tmp_path / "nested" / "Deskflow.conf"
    write_config(str(target), client_settings(), cert_path="/c.pem")
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o600


def test_write_config_is_idempotent(tmp_path):
    target = tmp_path / "Deskflow.conf"
    write_config(str(target), client_settings(), cert_path="/c.pem")
    first = target.read_text()
    write_config(str(target), client_settings(), cert_path="/c.pem")
    assert target.read_text() == first


def test_write_config_replaces_previous_content(tmp_path):
    target = tmp_path / "Deskflow.conf"
    write_config(str(target), client_settings(server_port=24800), cert_path="/c.pem")
    write_config(str(target), client_settings(server_port=25555), cert_path="/c.pem")
    assert "25555" in target.read_text()
    assert "24800" not in target.read_text()


def test_written_file_parses_back(tmp_path):
    target = tmp_path / "Deskflow.conf"
    write_config(str(target), client_settings(), cert_path="/c.pem")
    parsed = parse(target.read_text())
    assert parsed["core"]["computerName"] == "steamdeck"
