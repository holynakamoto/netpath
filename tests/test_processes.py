import signal
from unittest.mock import Mock, call, patch

from netpath import processes


def test_terminate_process_tree_signals_dedicated_posix_group():
    process = Mock(pid=4321)
    process.poll.return_value = None

    with (
        patch("netpath.processes.os.name", "posix"),
        patch("netpath.processes.os.killpg") as kill_group,
    ):
        processes.terminate_process_tree(process, grace_seconds=0)

    assert kill_group.call_args_list == [
        call(4321, signal.SIGTERM),
        call(4321, signal.SIGKILL),
    ]
    process.terminate.assert_not_called()


def test_terminate_process_tree_cleans_group_after_leader_exits():
    process = Mock(pid=4321)
    process.poll.return_value = 0

    with (
        patch("netpath.processes.os.name", "posix"),
        patch("netpath.processes.os.killpg") as kill_group,
    ):
        processes.terminate_process_tree(process, grace_seconds=0)

    assert kill_group.call_args_list == [
        call(4321, signal.SIGTERM),
        call(4321, signal.SIGKILL),
    ]


def test_terminate_process_tree_falls_back_to_direct_process():
    process = Mock()
    process.poll.return_value = None

    with patch("netpath.processes.os.name", "nt"):
        processes.terminate_process_tree(process, grace_seconds=0)

    process.terminate.assert_called_once_with()
    process.kill.assert_called_once_with()
