"""Suite-wide guards — see docs/INVARIANTS.md.

INV-10: the test suite must prove netpath's behavior without touching the
real network. Any socket connect to a non-loopback address fails the test
that attempted it, so a green run never depends on — or leaks anything to —
external services. Mock the egress point (requests.*, subprocess, socket)
instead of loosening this guard.
"""

import socket

_REAL_CONNECT = socket.socket.connect
_REAL_CONNECT_EX = socket.socket.connect_ex


def _is_local(address):
    if isinstance(address, (str, bytes)):  # AF_UNIX path
        return True
    if isinstance(address, tuple) and address:
        host = address[0]
        if isinstance(host, bytes):
            try:
                host = host.decode("ascii")
            except UnicodeDecodeError:
                return False
        if not isinstance(host, str):
            return False
        return host in ("localhost", "::1", "") or host.startswith("127.")
    return False


def _refuse(address):
    raise RuntimeError(
        "INV-10: a test attempted a real network connection to "
        + repr(address)
        + "; mock the egress point instead (see docs/INVARIANTS.md)"
    )


def _guarded_connect(self, address):
    if not _is_local(address):
        _refuse(address)
    return _REAL_CONNECT(self, address)


def _guarded_connect_ex(self, address):
    if not _is_local(address):
        _refuse(address)
    return _REAL_CONNECT_EX(self, address)


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
