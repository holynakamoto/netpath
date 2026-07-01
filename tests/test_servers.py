from unittest.mock import patch

from netpath.servers import _is_alive


def test_is_alive_returns_false_on_oserror():
    """_is_alive returns False when socket.create_connection raises OSError."""
    with patch("netpath.servers.socket.create_connection", side_effect=OSError("refused")):
        assert _is_alive("192.0.2.1", 5201) is False


def test_is_alive_returns_true_on_success():
    """_is_alive returns True when socket.create_connection succeeds."""
    mock_sock = patch("netpath.servers.socket.create_connection")
    with mock_sock as m:
        m.return_value.__enter__ = lambda s: s
        m.return_value.__exit__ = lambda s, *a: None
        m.return_value.close = lambda: None
        assert _is_alive("192.0.2.1", 5201) is True
