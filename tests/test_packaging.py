"""Packaging tests: one version source, declared extras, --version."""

import tomllib
from pathlib import Path

import pytest

import madd
from madd import cli

ROOT = Path(__file__).resolve().parent.parent


def _pyproject():
    """The parsed pyproject.toml of the repository root."""
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_version_has_a_single_source():
    """The version lives in madd/__init__.py and nowhere else."""
    project = _pyproject()["project"]
    assert "version" not in project
    assert project["dynamic"] == ["version"]
    dynamic = _pyproject()["tool"]["setuptools"]["dynamic"]
    assert dynamic["version"]["attr"] == "madd.__version__"
    assert madd.__version__


def test_optional_extras_cover_the_design_stack():
    """The extras name the verified compute stack and PDF export."""
    extras = _pyproject()["project"]["optional-dependencies"]
    design = " ".join(extras["design"])
    for package in ("rdkit", "admet-ai", "posebusters", "meeko"):
        assert package in design
    assert "weasyprint" in " ".join(extras["pdf"])
    assert set(extras) == {"design", "pdf", "all"}


def test_cli_reports_the_package_version(capsys):
    """madd --version prints the package version and exits 0."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"madd {madd.__version__}"
