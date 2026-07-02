"""Tests for the resilient baseline speedtest — partial results must survive."""

from unittest import mock

from netpath import speedtest

_DL = {"bps": 1e8, "bytes": 100_000, "elapsed": 5.0, "ttfb_ms": 12.3}
_UL = {"bps": 5e7, "bytes": 50_000, "elapsed": 5.0}


def test_run_upload_fails_download_succeeds_returns_partial():
    """Upload timeout must not discard a successful download."""
    with mock.patch.object(speedtest, "_download", return_value=dict(_DL)), \
         mock.patch.object(speedtest, "_upload",
                           side_effect=RuntimeError("write operation timed out")):
        result = speedtest.run(duration=5)

    assert result["download"] is not None
    assert result["upload"] is None
    assert "upload" in result["errors"]
    assert "download" not in result["errors"]

    upload_stats, download_stats = speedtest.extract_stats(result)
    assert upload_stats is None
    assert download_stats is not None
    assert download_stats["ttfb_ms"] == 12.3


def test_run_download_fails_upload_succeeds_returns_partial():
    with mock.patch.object(speedtest, "_download",
                           side_effect=RuntimeError("connection reset")), \
         mock.patch.object(speedtest, "_upload", return_value=dict(_UL)):
        result = speedtest.run(duration=5)

    assert result["download"] is None
    assert result["upload"] is not None
    assert "download" in result["errors"]

    upload_stats, download_stats = speedtest.extract_stats(result)
    assert download_stats is None
    assert upload_stats is not None


def test_run_both_fail_records_both_errors_no_raise():
    with mock.patch.object(speedtest, "_download",
                           side_effect=RuntimeError("down fail")), \
         mock.patch.object(speedtest, "_upload",
                           side_effect=RuntimeError("up fail")):
        result = speedtest.run(duration=5)

    assert result["download"] is None
    assert result["upload"] is None
    assert set(result["errors"]) == {"download", "upload"}

    upload_stats, download_stats = speedtest.extract_stats(result)
    assert upload_stats is None
    assert download_stats is None


def test_run_both_succeed():
    with mock.patch.object(speedtest, "_download", return_value=dict(_DL)), \
         mock.patch.object(speedtest, "_upload", return_value=dict(_UL)):
        result = speedtest.run(duration=5)

    assert result["errors"] == {}
    upload_stats, download_stats = speedtest.extract_stats(result)
    assert upload_stats is not None
    assert download_stats is not None
