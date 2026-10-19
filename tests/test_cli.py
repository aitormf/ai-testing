import pytest

from ia_testing.cli import main


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    main()

    assert capsys.readouterr().out == "Hello from ia-testing!\n"
