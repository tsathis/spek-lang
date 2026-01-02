import pytest
from unittest.mock import patch
from spek.cli import main


def test_cli_no_command_prints_help():
    with patch("sys.argv", ["spek"]):
        rc = main()
    assert rc == 1
