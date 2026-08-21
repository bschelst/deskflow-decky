"""The diagnostics export is written to be pasted into a bug report by someone who
will not read it first. Every field in it is therefore treated as public."""

from diagnostics import ALLOWED_FIELDS, build_report, redact_line


def test_report_contains_only_allowlisted_fields():
    report = build_report({"state": "connected", "totally_secret": "hunter2"})
    assert set(report).issubset(ALLOWED_FIELDS)
    assert "totally_secret" not in report


def test_unknown_field_cannot_smuggle_a_secret_in():
    report = build_report({"password": "hunter2", "SSH_KEY": "-----BEGIN"})
    assert "hunter2" not in repr(report)
    assert "BEGIN" not in repr(report)


def test_missing_fields_are_reported_as_unknown_not_omitted():
    # An absent field and an unknown value look different to whoever reads the report.
    report = build_report({})
    assert report["state"] == "unknown"


def test_values_are_stringified():
    report = build_report({"helper_pid": 1234})
    assert report["helper_pid"] == "1234"


def test_long_values_are_truncated():
    report = build_report({"last_error": "x" * 10000})
    assert len(report["last_error"]) < 1000


def test_report_is_built_from_an_allowlist_not_by_filtering():
    # Every allowed field is present regardless of what was passed in.
    report = build_report({})
    assert set(report) == set(ALLOWED_FIELDS)


def test_redact_line_masks_an_openssl_private_key_marker():
    assert "PRIVATE KEY" not in redact_line("-----BEGIN PRIVATE KEY-----")


def test_redact_line_masks_things_that_look_like_fingerprints_only_partially():
    line = redact_line("fingerprint " + "ab" * 32)
    assert "ab" * 32 not in line
    # Enough remains to correlate two log lines, not enough to be the whole secret.
    assert "ab" in line


def test_redact_line_leaves_ordinary_text_alone():
    assert redact_line("connected to server on port 24800") == "connected to server on port 24800"


def test_redact_line_handles_non_string_input():
    assert isinstance(redact_line(None), str)
