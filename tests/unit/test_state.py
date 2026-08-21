"""Connection state is an explicit machine, not something inferred at each call site."""

import pytest
from state import STATES, HelperState, IllegalTransition


def test_starts_stopped():
    assert HelperState().state == "stopped"


def test_all_states_are_declared():
    assert set(STATES) == {
        "stopped",
        "starting",
        "connected",
        "degraded",
        "disconnected",
        "error",
    }


def test_normal_startup_path():
    machine = HelperState()
    machine.to("starting")
    machine.to("connected")
    assert machine.state == "connected"


def test_cannot_jump_from_stopped_to_connected():
    machine = HelperState()
    with pytest.raises(IllegalTransition):
        machine.to("connected")
    assert machine.state == "stopped"


def test_reconnect_must_pass_through_starting():
    machine = HelperState()
    machine.to("starting")
    machine.to("connected")
    machine.to("disconnected")
    with pytest.raises(IllegalTransition):
        machine.to("connected")
    machine.to("starting")
    machine.to("connected")
    assert machine.state == "connected"


def test_error_recovers_only_through_an_explicit_restart():
    machine = HelperState()
    machine.to("starting")
    machine.to("error")
    with pytest.raises(IllegalTransition):
        machine.to("connected")
    machine.to("starting")
    assert machine.state == "starting"


def test_stop_is_always_allowed():
    for origin in STATES:
        machine = HelperState()
        machine.force(origin)
        machine.to("stopped")
        assert machine.state == "stopped"


def test_degraded_can_recover_to_connected():
    machine = HelperState()
    machine.force("degraded")
    machine.to("connected")
    assert machine.state == "connected"


def test_transition_to_an_unknown_state_is_rejected():
    machine = HelperState()
    with pytest.raises(IllegalTransition):
        machine.to("banana")


def test_can_reports_without_transitioning():
    machine = HelperState()
    assert machine.can("starting") is True
    assert machine.can("connected") is False
    assert machine.state == "stopped"


def test_reason_is_recorded_and_exposed():
    machine = HelperState()
    machine.to("starting")
    machine.to("error", reason="socket not found")
    assert machine.last_error == "socket not found"


def test_reason_clears_on_a_successful_connection():
    machine = HelperState()
    machine.to("starting")
    machine.to("error", reason="socket not found")
    machine.to("starting")
    machine.to("connected")
    assert machine.last_error is None


def test_listeners_are_notified_of_transitions():
    seen = []
    machine = HelperState(on_change=lambda old, new, reason: seen.append((old, new)))
    machine.to("starting")
    machine.to("connected")
    assert seen == [("stopped", "starting"), ("starting", "connected")]


def test_listener_failure_does_not_break_the_transition():
    def broken(old, new, reason):
        raise RuntimeError("listener blew up")

    machine = HelperState(on_change=broken)
    machine.to("starting")
    assert machine.state == "starting"


def test_redundant_transition_to_the_same_state_is_a_noop():
    seen = []
    machine = HelperState(on_change=lambda o, n, r: seen.append((o, n)))
    machine.to("starting")
    machine.to("starting")
    assert machine.state == "starting"
    assert len(seen) == 1


def test_snapshot_is_serialisable_and_complete():
    machine = HelperState()
    machine.to("starting")
    snapshot = machine.snapshot()
    assert snapshot["state"] == "starting"
    assert "since" in snapshot
    assert "last_error" in snapshot
