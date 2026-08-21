"""Helper connection state as an explicit machine.

Inferring state ad hoc from process liveness at each call site is how a UI ends up
showing "connected" for a process that died thirty seconds ago. One machine, one
transition table, unit-tested.
"""

import time

__all__ = ["STATES", "HelperState", "IllegalTransition"]

STATES = ("stopped", "starting", "connected", "degraded", "disconnected", "error")

#: Legal transitions. "stopped" is reachable from anywhere (an explicit stop always
#: wins); everything else must follow the graph. Notably a reconnect cannot go
#: straight from "disconnected" to "connected" -- it passes through "starting", so
#: socket rediscovery always happens.
_ALLOWED = {
    "stopped": {"starting"},
    "starting": {"connected", "disconnected", "error"},
    "connected": {"degraded", "disconnected", "error"},
    "degraded": {"connected", "disconnected", "error"},
    "disconnected": {"starting", "error"},
    "error": {"starting"},
}


class IllegalTransition(Exception):
    def __init__(self, origin, target):
        super().__init__("cannot move from {0} to {1}".format(origin, target))
        self.origin = origin
        self.target = target


class HelperState:
    def __init__(self, on_change=None, clock=time.time):
        self._state = "stopped"
        self._since = clock()
        self._last_error = None
        self._on_change = on_change
        self._clock = clock

    @property
    def state(self):
        return self._state

    @property
    def since(self):
        return self._since

    @property
    def last_error(self):
        return self._last_error

    def can(self, target):
        if target not in STATES:
            return False
        if target == "stopped":
            return True
        return target in _ALLOWED[self._state]

    def to(self, target, reason=None):
        """Move to ``target``. Raises IllegalTransition if the graph forbids it."""
        if target == self._state:
            if reason is not None:
                self._last_error = reason
            return self._state

        if not self.can(target):
            raise IllegalTransition(self._state, target)

        origin = self._state
        self._state = target
        self._since = self._clock()

        if target == "connected":
            # A successful connection clears whatever went wrong last time.
            self._last_error = None
        elif reason is not None:
            self._last_error = reason

        self._notify(origin, target, reason)
        return target

    def force(self, target, reason=None):
        """Set the state without consulting the graph. For tests and recovery paths only."""
        if target not in STATES:
            raise IllegalTransition(self._state, target)
        origin = self._state
        self._state = target
        self._since = self._clock()
        if reason is not None:
            self._last_error = reason
        if origin != target:
            self._notify(origin, target, reason)
        return target

    def snapshot(self):
        return {"state": self._state, "since": self._since, "last_error": self._last_error}

    def _notify(self, origin, target, reason):
        if self._on_change is None:
            return
        try:
            self._on_change(origin, target, reason)
        except Exception:  # noqa: BLE001 - a broken listener must not corrupt the machine
            pass
