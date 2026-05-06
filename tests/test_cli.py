import json

import pytest

from spek.cli import FINDINGS, OK, USAGE, main

SPEC = 'slugify(title) -> text\n  "Hello World" "hello-world"\n  "" ""\n'
IMPL = (
    "import re\n\n\n"
    'def slugify(title):\n    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")\n'
)


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "s.spek").write_text(SPEC)
    (tmp_path / "s.py").write_text(IMPL)
    return tmp_path


def run(*argv: str) -> int:
    return main(list(argv))


def test_check_is_clean(project, capsys):
    assert run("check", str(project / "s.spek")) == OK
    assert "clean" in capsys.readouterr().out


def test_check_json_shape(project, capsys):
    assert run("check", str(project / "s.spek"), "--json") == OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["diagnostics"] == []
    assert payload["summary"]["ok"] is True
    assert payload["triage"]["slugify"]["triage"] == "machine-verifiable"


def test_check_reports_findings_with_a_nonzero_exit(tmp_path, capsys):
    (tmp_path / "s.spek").write_text("f(a, b) -> y\n  (1) ok\n")
    assert run("check", str(tmp_path / "s.spek")) == FINDINGS
    assert "E203" in capsys.readouterr().err


def test_verify_passes(project, capsys):
    code = run(
        "verify", str(project / "s.spek"), str(project / "s.py"), "--out", str(project / "b")
    )
    assert code == OK
    assert "OK" in capsys.readouterr().out


def test_verify_json_carries_diagnostics_and_triage(tmp_path, capsys):
    (tmp_path / "s.spek").write_text("f(x) -> y\n  !net\n  1 ok\n  ? fast\n")
    (tmp_path / "s.py").write_text("def f(x):\n    return x\n")
    code = run(
        "verify", str(tmp_path / "s.spek"), str(tmp_path / "s.py"),
        "--out", str(tmp_path / "b"), "--json",
    )
    assert code == FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["ok"] is False
    assert payload["summary"]["hatches"] == 1
    codes = [d["code"] for d in payload["diagnostics"]]
    assert "E103" in codes
    finding = next(d for d in payload["diagnostics"] if d["code"] == "E103")
    assert finding["symbol"] == "net" and finding["fix"]


def test_effects_reports_an_undeclared_call(tmp_path, capsys):
    (tmp_path / "s.spek").write_text("f(x) -> y\n  !fs\n  1 ok\n")
    (tmp_path / "s.py").write_text("import requests\n\ndef f(x):\n    return requests.get(x)\n")
    assert run("effects", str(tmp_path / "s.spek"), str(tmp_path / "s.py")) == FINDINGS
    assert "E101" in capsys.readouterr().err


def test_effects_show_lists_observations(project, capsys):
    (project / "n.spek").write_text("f(x) -> y\n  !net\n  1 ok\n")
    (project / "n.py").write_text("import requests\n\ndef f(x):\n    return requests.get(x)\n")
    assert run("effects", str(project / "n.spek"), str(project / "n.py"), "--show") == OK
    assert "requests.get" in capsys.readouterr().out


def test_build_writes_a_test_module(project, capsys):
    out = project / "b"
    assert run("build", str(project / "s.spek"), "--impl", str(project / "s.py"),
               "--out", str(out)) == OK
    assert "wrote" in capsys.readouterr().out
    assert (out / "test_s_spek.py").exists()


def test_prompt_prints_the_spec_and_the_conventions(project, capsys):
    assert run("prompt", str(project / "s.spek"), "--impl", "out.py") == OK
    printed = capsys.readouterr().out
    assert "slugify(title) -> text" in printed
    assert "!net" in printed and "Hatches" in printed


def test_missing_file_is_a_usage_error(capsys):
    assert run("check", "/nonexistent/x.spek") == USAGE
    assert "no such file" in capsys.readouterr().err


def test_no_subcommand_prints_help():
    assert main([]) == USAGE
