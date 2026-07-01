import pytest
import requests
from unittest.mock import Mock
from netpath.utils import _with_retry


def test_succeeds_on_first_try():
    fn = Mock(return_value="ok")
    result = _with_retry(fn, base_delay=0)
    assert result == "ok"
    assert fn.call_count == 1


def test_retries_on_connection_error_then_succeeds():
    fn = Mock(side_effect=[requests.ConnectionError("down"), "ok"])
    result = _with_retry(fn, attempts=2, base_delay=0)
    assert result == "ok"
    assert fn.call_count == 2


def test_retries_on_timeout_then_succeeds():
    fn = Mock(side_effect=[requests.Timeout("slow"), "ok"])
    result = _with_retry(fn, attempts=2, base_delay=0)
    assert result == "ok"
    assert fn.call_count == 2


def test_raises_after_max_attempts():
    fn = Mock(side_effect=requests.ConnectionError("unreachable"))
    with pytest.raises(requests.ConnectionError):
        _with_retry(fn, attempts=3, base_delay=0)
    assert fn.call_count == 3


def test_retries_on_5xx_response():
    mock_500 = Mock()
    mock_500.status_code = 500
    mock_ok = Mock()
    mock_ok.status_code = 200
    fn = Mock(side_effect=[mock_500, mock_ok])
    result = _with_retry(fn, attempts=2, base_delay=0)
    assert result is mock_ok
    assert fn.call_count == 2
