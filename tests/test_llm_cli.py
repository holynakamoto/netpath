import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from netpath import llm_cli

SCHEMA = {"type": "object", "properties": {"narrative": {"type": "string"}}}


def test_available_false_for_unknown_provider():
    assert llm_cli.available("gpt") is False


def test_available_false_when_not_on_path():
    with patch("netpath.llm_cli.shutil.which", return_value=None):
        assert llm_cli.available("claude") is False


def test_available_true_when_on_path():
    with patch("netpath.llm_cli.shutil.which", return_value="/usr/bin/claude"):
        assert llm_cli.available("claude") is True


def test_run_schema_constrained_returns_none_for_unknown_provider():
    assert llm_cli.run_schema_constrained("gpt", "hello", SCHEMA) is None


def test_run_schema_constrained_returns_none_when_cli_missing():
    with patch("netpath.llm_cli.shutil.which", return_value=None):
        assert llm_cli.run_schema_constrained("claude", "hello", SCHEMA) is None


def test_run_schema_constrained_claude_parses_structured_output():
    response = json.dumps({"structured_output": {"narrative": "all clear"}})
    with patch("netpath.llm_cli.shutil.which", return_value="/usr/bin/claude"), \
         patch("netpath.llm_cli.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, stdout=response, stderr="")
        result = llm_cli.run_schema_constrained("claude", "hello", SCHEMA)

    assert result == {"narrative": "all clear"}
    command = run.call_args.args[0]
    assert command[0] == "/usr/bin/claude"
    assert "--json-schema" in command


def test_run_schema_constrained_codex_writes_and_cleans_up_schema_file():
    response = json.dumps({"narrative": "all clear"})
    captured_path = {}

    def _fake_run(command, **kwargs):
        idx = command.index("--output-schema")
        schema_path = command[idx + 1]
        captured_path["path"] = schema_path
        assert json.loads(Path(schema_path).read_text()) == SCHEMA
        return subprocess.CompletedProcess(command, 0, stdout=response, stderr="")

    with patch("netpath.llm_cli.shutil.which", return_value="/usr/bin/codex"), \
         patch("netpath.llm_cli.subprocess.run", side_effect=_fake_run):
        result = llm_cli.run_schema_constrained("codex", "hello", SCHEMA)

    assert result == {"narrative": "all clear"}
    assert not Path(captured_path["path"]).exists()


def test_run_schema_constrained_returns_none_on_timeout():
    with patch("netpath.llm_cli.shutil.which", return_value="/usr/bin/claude"), \
         patch("netpath.llm_cli.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=60)):
        assert llm_cli.run_schema_constrained("claude", "hello", SCHEMA) is None


def test_run_schema_constrained_returns_none_on_invalid_json():
    with patch("netpath.llm_cli.shutil.which", return_value="/usr/bin/claude"), \
         patch("netpath.llm_cli.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, stdout="not json", stderr="")
        assert llm_cli.run_schema_constrained("claude", "hello", SCHEMA) is None


def test_run_schema_constrained_returns_none_when_output_not_an_object():
    with patch("netpath.llm_cli.shutil.which", return_value="/usr/bin/claude"), \
         patch("netpath.llm_cli.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, stdout=json.dumps([1, 2, 3]), stderr="")
        assert llm_cli.run_schema_constrained("claude", "hello", SCHEMA) is None
