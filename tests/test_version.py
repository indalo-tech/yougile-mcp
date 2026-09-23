import importlib.util
import re
import tomllib
from pathlib import Path

from yougile_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_is_semver_and_single_sourced():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
    assert "version" not in project and "version" in project["dynamic"]


def test_changelog_has_a_section_for_the_current_version():
    notes = load_script("release_notes")
    text = (ROOT / "CHANGELOG.md").read_text("utf-8")
    section = notes.section(__version__, text)
    assert section, f"add a '## [{__version__}]' section to CHANGELOG.md"
    assert "### Русский" in section and "### English" in section
    assert f"[{__version__}]: https://github.com/" in text, "add the compare link at the bottom"
