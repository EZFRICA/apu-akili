"""
The documentation, held to what is true of the repository.

Target: README.md, DEMO.md, docs/, every README under apu/

A document is a promise about the code beside it. These check the promises a reader acts on
without reading the code: the commands they type, the paths they open, the repository they
clone, and what the project says it is.
"""

import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _documents() -> list[pathlib.Path]:
    found = (list(ROOT.glob("*.md")) + list(ROOT.glob("docs/*.md"))
             + list(ROOT.glob("apu/**/*.md")) + list(ROOT.glob("cloud_registry/*.md")))
    return sorted(set(found))


def test_the_decommissioned_viewer_is_gone_and_unreferenced():
    """
    apu/ui/hardware was the first 3D viewer and this interface replaces it. A directory
    that is deleted but still named in the documentation sends the next reader to a path
    that does not exist, which is how a repository starts lying about itself.
    """
    import re

    root = ROOT
    assert not (root / "apu/ui/hardware").exists()

    stale = []
    for path in list(root.glob("*.md")) + list(root.glob("docs/*.md")) + list(root.glob("apu/**/*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"ui/hardware|ui\.hardware|:8766", line):
                stale.append(f"{path.relative_to(root)}: {line.strip()[:60]}")
    assert not stale, f"the old viewer is still named here: {stale}"


def test_every_command_the_documentation_gives_points_at_something_that_exists():
    """
    A command in a README is a promise. `apu.ui.presentation.app` was in three documents
    for a while after the module was deleted, and the only way to find out was to run it.
    """
    import importlib.util
    import re

    root = ROOT
    broken = []
    for doc in list(root.glob("*.md")) + list(root.glob("docs/*.md")) + list(root.glob("apu/**/*.md")):
        text = doc.read_text(encoding="utf-8")
        for module in re.findall(r"uv run python -m ([\w.]+)", text):
            if importlib.util.find_spec(module) is None:
                broken.append(f"{doc.relative_to(root)}: python -m {module}")
        for script in re.findall(r"uv run streamlit run ([\w./]+)", text):
            if not (root / script).exists():
                broken.append(f"{doc.relative_to(root)}: {script}")
        for script in re.findall(r"uv run python (scripts/[\w./]+)", text):
            if not (root / script).exists():
                broken.append(f"{doc.relative_to(root)}: {script}")
    assert not broken, f"these documented commands point at nothing: {broken}"


def test_the_front_ends_are_listed_with_the_command_that_starts_each():
    """
    Three interfaces, and the two that share a server are the ones people get wrong. The
    table is the answer to "what do I run", and it has to name all three.
    """
    readme = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    launch = readme[readme.index("### 7. Launch an interface"):readme.index("### 8.")]

    for command in ("uv run streamlit run apu/ui/app.py",
                    "uv run python -m apu.ui.live.proxy"):
        assert command in launch, command
    assert "http://localhost:8765/presentation/" in launch
    assert "one server" in launch.lower(), "the thing readers get wrong is that two share one"


def test_every_relative_link_leads_somewhere():
    broken = []
    for doc in _documents():
        for _, target in re.findall(r"\[([^\]]*)\]\(([^)]+)\)", doc.read_text(encoding="utf-8")):
            if target.startswith(("http", "#", "mailto:")):
                continue
            if not (doc.parent / target.split("#")[0]).exists():
                broken.append(f"{doc.relative_to(ROOT)}: {target}")
    assert not broken, broken


def test_the_clone_command_names_this_repository():
    """
    The README told a new reader to clone apu-nemotron, the repository this project started
    in for a hackathon. Whoever followed it got the old code.
    """
    try:
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT,
                                capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available")
    if not remote:
        pytest.skip("this checkout has no origin remote")

    repository = re.sub(r"\.git$", "", remote.rstrip("/")).split("/")[-1].split(":")[-1]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cloned = re.findall(r"git clone \S+?([\w.-]+?)(?:\.git)?\s", readme)
    assert cloned, "the README gives no clone command"
    for name in cloned:
        assert name == repository, f"the README clones {name}, but this is {repository}"
    assert f"cd {repository}" in readme


def test_the_project_describes_itself_rather_than_its_first_vendor():
    """
    It started as a port to one vendor's models for a hackathon, and the package description
    still said so long after every role had moved. A provider is a setting here, not an
    identity (docs/decisions.md), so neither the package nor the README's opening names one.
    """
    import tomllib

    description = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["description"]
    opening = (ROOT / "README.md").read_text(encoding="utf-8").split("## ", 1)[0]
    for text, where in ((description, "pyproject.toml"), (opening, "the README's opening")):
        for vendor in ("Nemotron", "Nebius", "Token Factory", "NVIDIA"):
            assert vendor not in text, f"{where} still introduces the project by {vendor}"


def test_no_document_mentions_an_interface_that_is_gone():
    """Chainlit was removed. A document that still offers it sends a reader to nothing."""
    for doc in _documents():
        text = doc.read_text(encoding="utf-8").lower()
        assert "chainlit" not in text, f"{doc.relative_to(ROOT)} still mentions Chainlit"
    assert not (ROOT / "apu/ui/chainlit_app.py").exists()
    assert not (ROOT / ".chainlit").exists()


def test_every_declared_dependency_is_used():
    """
    tavily-python was declared and imported by nothing, not even by langchain-tavily, which
    talks to the API itself. pyarrow and watchdog are never imported but are needed at
    runtime, by pandas for Parquet and by Streamlit for reloading, and the pyproject says so
    beside each.
    """
    import tomllib

    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    names = [re.split(r"[<>=!~ ]", spec, maxsplit=1)[0] for spec in declared]
    used_without_import = {"pyarrow", "watchdog", "uvicorn"}
    module_of = {"python-dotenv": "dotenv", "langchain-core": "langchain_core",
                 "langchain-tavily": "langchain_tavily", "google-cloud-storage": "google.cloud",
                 "google-auth": "google.auth|google.oauth2", "google-genai": "google.genai|google import genai",
                 "scikit-learn": "sklearn", "pyyaml": "yaml"}
    code = "\n".join(path.read_text(encoding="utf-8")
                     for folder in ("apu", "cloud_registry")
                     for path in (ROOT / folder).rglob("*.py"))
    unused = []
    for name in names:
        if name in used_without_import:
            continue
        module = module_of.get(name, name.replace("-", "_"))
        if not re.search(rf"^\s*(import|from) ({module})", code, re.MULTILINE):
            unused.append(name)
    assert not unused, f"declared and never imported: {unused}"


def test_the_demo_names_each_profile_exactly_as_the_sidebar_shows_it():
    """
    A presenter follows DEMO.md with the sidebar open and picks the profile it names. The
    admin's label was missing its scope, and the other two were rewritten once to drop a dash
    that is part of what the screen shows: a quotation of the interface is not prose.
    """
    from apu.ui import common

    shown = {identity.label for identity in common.available_identities()}
    named = re.findall(r"Profile \*\*([^*]+)\*\*", (ROOT / "DEMO.md").read_text(encoding="utf-8"))
    assert named, "DEMO.md names no profile"
    for label in named:
        assert label in shown, f"DEMO.md says {label!r}; the sidebar offers {sorted(shown)}"

