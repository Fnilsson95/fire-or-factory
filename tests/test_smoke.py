from fof import __version__
from fof.cli import main


def test_version_is_set():
    assert __version__


def test_cli_runs():
    assert main([]) == 0
