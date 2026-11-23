"""Tests for the live demo script.

The demo runs in-process with the fake client, so no API key or
network access is needed. Its output must include the tailored
resume, the grounding report, and the trace spans.
"""
import runpy
import sys
from pathlib import Path

import pytest

DEMO_PATH = Path(__file__).resolve().parent.parent / "scripts" / "demo.py"


def test_demo_with_fake_client_prints_resume_report_and_spans(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["demo.py", "--fake"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(DEMO_PATH), run_name="__main__")
    assert excinfo.value.code == 0

    out = capsys.readouterr().out
    assert "Jane Doe" in out
    assert "Built Python services and APIs with Flask" in out
    assert "Grounding rate: 1.00" in out
    assert "[grounded / exact]" in out
    assert "agent.run" in out
    assert "tool.research_company" in out
    assert "tool.name: research_company" in out
    assert "tool.success: True" in out


def test_demo_with_fake_client_env_var(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["demo.py"])
    monkeypatch.setenv("DEMO_FAKE_CLIENT", "1")

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(DEMO_PATH), run_name="__main__")
    assert excinfo.value.code == 0

    out = capsys.readouterr().out
    assert "Jane Doe" in out
    assert "agent.run" in out
