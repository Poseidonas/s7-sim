"""The command line, including how it fails."""
import pytest

from s7sim.cli import main, parse_args

GOOD = """
line: {mean_run_minutes: 5, mean_stop_minutes: 1}
blocks:
  10:
    tags:
      running: {offset: 0, bit: 3, type: bool, behaviour: running}
      parts:   {offset: 2, type: dint, behaviour: counter, per_minute: 120}
      speed:   {offset: 6, type: int, behaviour: setpoint, value: 400}
"""


def _write(tmp_path, text):
    path = tmp_path / "line.yml"
    path.write_text(text)
    return str(path)


def test_check_prints_the_layout_with_addresses(tmp_path, capsys):
    assert main(["--config", _write(tmp_path, GOOD), "--check"]) == 0

    out = capsys.readouterr().out
    assert "DB10  8 bytes" in out
    assert "DB10.DBX0.3" in out, "a bool must show which bit it is"
    assert "runs 5 min on average" in out


def test_check_marks_which_tags_a_client_may_write(tmp_path, capsys):
    main(["--config", _write(tmp_path, GOOD), "--check"])

    lines = {ln.split()[0]: ln for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("    ")}
    assert " rw " in lines["speed"]
    assert " r- " in lines["parts"]


def test_check_does_not_open_a_port(tmp_path):
    """It has to be safe to run against a file without starting anything."""
    assert main(["--config", _write(tmp_path, GOOD), "--check"]) == 0


def test_a_missing_file_exits_with_a_message(tmp_path, capsys):
    assert main(["--config", str(tmp_path / "nope.yml"), "--check"]) == 2
    assert capsys.readouterr().err.startswith("s7-sim:")


def test_a_broken_plant_exits_with_the_reason(tmp_path, capsys):
    path = _write(tmp_path, "blocks:\n  1:\n    tags:\n      a: {offset: 0, type: nope}\n")

    assert main(["--config", path, "--check"]) == 2
    assert "unknown type 'nope'" in capsys.readouterr().err


def test_unreadable_yaml_exits_with_the_reason(tmp_path, capsys):
    assert main(["--config", _write(tmp_path, "blocks: [oops\n"), "--check"]) == 2
    assert capsys.readouterr().err.startswith("s7-sim:")


def test_health_reports_a_failure_when_nothing_is_listening(tmp_path, capsys, free_port):
    """The container check has to fail when the plant is not there, or it says
    nothing at all."""
    assert main(["--config", _write(tmp_path, GOOD), "--health", "--port", str(free_port)]) == 1
    assert capsys.readouterr().err.startswith("s7-sim:")


def test_health_passes_against_a_running_simulator(tmp_path, free_port):
    import time

    from s7sim import Simulator, loads

    with Simulator(loads(GOOD), host="127.0.0.1", port=free_port):
        time.sleep(0.3)
        assert main(["--config", _write(tmp_path, GOOD), "--health",
                     "--port", str(free_port)]) == 0


def test_it_listens_on_every_interface_by_default():
    """This runs in a container, where loopback would make it unreachable."""
    assert parse_args(["--config", "x"]).host == "0.0.0.0"


def test_the_config_argument_is_required():
    with pytest.raises(SystemExit):
        parse_args([])
