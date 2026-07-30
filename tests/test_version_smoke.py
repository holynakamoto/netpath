from netpath._version import __version__


def test_version_is_nonempty_string():
    assert isinstance(__version__, str)
    assert __version__
