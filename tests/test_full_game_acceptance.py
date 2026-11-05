"""Acceptance refuses stale builds, missing execution evidence and interrupted publication."""

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from godfield_bot import full_game_acceptance as module
from godfield_bot.cli import app
from godfield_bot.full_game_integration_audit import canonical_sha256, workflow_ledger

ROOT = Path(__file__).resolve().parents[1]
PATHS = dict(
    catalog_path=ROOT / "data/snapshots/2026-10-01/api-catalog-en.json",
    bible_path=ROOT / "data/snapshots/2026-09-20/bible.json",
)


def nodes():
    return tuple(
        sorted({f"{path}::test_required" for w in workflow_ledger() for path in w.test_files})
    )


def junit(path, expected):
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root, "testsuite", tests=str(len(expected)), errors="0", failures="0", skipped="0"
    )
    for node in expected:
        filename, *names = node.split("::")
        ET.SubElement(
            suite,
            "testcase",
            classname=".".join((filename[:-3].replace("/", "."), *names[:-1])),
            name=names[-1],
        )
    ET.ElementTree(root).write(path)
    return root


def save_xml(path, tree):
    ET.ElementTree(tree).write(path)


def test_exact_parameterized_and_class_test_identities(tmp_path):
    expected = ("tests/test_a.py::test_a[2-nine]", "tests/test_a.py::TestB::test_b")
    path = tmp_path / "results.xml"
    junit(path, expected)
    assert module.verify_junit(path, expected) == 2


@pytest.mark.parametrize(
    "change",
    ["missing", "duplicate", "uncollected", "failure", "error", "skipped", "count", "suite"],
)
def test_test_counts_cannot_substitute_for_exact_successful_execution(tmp_path, change):
    expected = ("tests/test_a.py::test_a", "tests/test_a.py::test_b")
    path = tmp_path / "results.xml"
    tree = junit(path, expected)
    suite = tree.find("testsuite")
    first, second = list(suite)
    if change == "missing":
        suite.remove(second)
    elif change == "duplicate":
        second.set("name", first.get("name"))
    elif change == "uncollected":
        second.set("name", "test_c")
    elif change in ("failure", "error", "skipped"):
        ET.SubElement(first, change)
    elif change == "count":
        suite.set("tests", "3")
    else:
        suite.set("skipped", "1")
    save_xml(path, tree)
    with pytest.raises(ValueError, match="every collected test"):
        module.verify_junit(path, expected)


@pytest.mark.parametrize("expected", [(), ("tests/a.py::f", "tests/a.py::f"), ("other/a.py::f",)])
def test_invalid_expected_test_identities(tmp_path, expected):
    path = tmp_path / "results.xml"
    junit(path, ("tests/a.py::f",))
    with pytest.raises(ValueError):
        module.verify_junit(path, expected)


def test_xml_entities_are_not_accepted(tmp_path):
    path = tmp_path / "results.xml"
    path.write_text('<!DOCTYPE testsuites [<!ENTITY x "hello">]><testsuites/>')
    with pytest.raises(ValueError, match="entity-bearing"):
        module.verify_junit(path, ("tests/a.py::f",))


def test_collected_tests_cover_every_required_workflow():
    expected = tuple(sorted((*nodes(), "tests/test_example.py::test_text[1 skipped]")))
    assert module.collected_test_nodes("\n".join(reversed(expected))) == expected
    for collection in ((), expected[:-1], (*expected, expected[0])):
        with pytest.raises(ValueError):
            module.collected_test_nodes("\n".join(collection))


def test_source_identity_includes_fixtures_and_excludes_runs_accounts_and_caches(tmp_path):
    for folder in (
        "src",
        "tests",
        "native",
        "data/snapshots",
        "runs",
        "accounts",
        "src/__pycache__",
    ):
        (tmp_path / folder).mkdir(parents=True)
    for name in (
        "pyproject.toml",
        "uv.lock",
        "src/a.py",
        "tests/fixture.json",
        "native/a.cpp",
        "data/snapshots/catalog.json",
        "runs/a.py",
        "accounts/a.py",
        "src/__pycache__/a.pyc",
    ):
        (tmp_path / name).write_text("old")
    before = module.source_files(tmp_path)
    assert len(before) == 6
    assert {row.path for row in before} >= {"tests/fixture.json", "data/snapshots/catalog.json"}
    (tmp_path / "tests/fixture.json").write_text("new")
    assert module.source_files(tmp_path) != before


def test_loaded_build_proves_its_native_source_identity(monkeypatch):
    runtime = module.acceptance_runtime(ROOT)
    native = module.importlib.import_module("godfield_sim._native")
    assert runtime.native_source_sha256 == native.BUILD_SOURCE_SHA256
    assert runtime.native_source_sha256 == module.native_source_sha256(ROOT)
    assert runtime.native_binary_sha256 == module.file_sha256(Path(native.__file__))
    monkeypatch.setattr(native, "BUILD_SOURCE_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="native build is stale"):
        module.acceptance_runtime(ROOT)


def test_another_checkout_cannot_be_certified_by_this_import(tmp_path):
    with pytest.raises(ValueError, match="checkout"):
        module.run_full_game_acceptance(
            repository_root=tmp_path, output_root=tmp_path / "reports", **PATHS
        )
    assert not (tmp_path / "reports").exists()
    with pytest.raises(ValueError, match="checkout"):
        module.verify_full_game_acceptance(tmp_path, repository_root=tmp_path)


@pytest.mark.parametrize("path", ["/tmp/outside", "../outside", "inside/../../outside"])
def test_manifest_paths_cannot_escape(path):
    with pytest.raises(ValueError):
        module.AcceptanceFile(path=path, sha256="0" * 64)


def test_evidence_symlinks_cannot_escape(tmp_path):
    folder = tmp_path / "evidence"
    folder.mkdir()
    (tmp_path / "outside").write_text("outside")
    (folder / "tests.xml").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlink"):
        module._read_evidence(folder, "tests.xml")


@pytest.fixture
def manifest():
    sources = module.source_files(ROOT)
    return module.FullGameLocalAcceptance(
        sources=sources,
        source_tree_sha256=canonical_sha256([row.model_dump() for row in sources]),
        runtime=module.acceptance_runtime(ROOT),
        evidence=tuple(
            module.AcceptanceFile(path=name, sha256="0" * 64) for name in module.EVIDENCE_FILES
        ),
        executed_tests=1,
    )


@pytest.mark.parametrize(
    "field",
    [
        "official_fidelity_verified",
        "live_checkpoint_compatible",
        "promotion_eligible",
        "competitive_strength_verified",
    ],
)
def test_local_acceptance_cannot_grant_official_fidelity_or_live_readiness(manifest, field):
    with pytest.raises(ValueError):
        module.FullGameLocalAcceptance.model_validate(manifest.model_dump() | {field: True})


def test_parsing_a_manifest_is_not_verifying_its_artifacts(tmp_path, manifest):
    (tmp_path / "acceptance.json").write_text(manifest.model_dump_json())
    with pytest.raises(FileNotFoundError):
        module.verify_full_game_acceptance(tmp_path, repository_root=ROOT)


def test_verifier_rejects_source_changes_before_reading_evidence(tmp_path, manifest, monkeypatch):
    (tmp_path / "acceptance.json").write_text(manifest.model_dump_json())
    monkeypatch.setattr(module, "source_files", lambda _: ())
    with pytest.raises(ValueError, match="stale"):
        module.verify_full_game_acceptance(tmp_path, repository_root=ROOT)


@pytest.mark.parametrize("stage", ["collection", "tests", "probe", "interruption", "validation"])
def test_failed_or_interrupted_runs_never_publish_acceptance(tmp_path, monkeypatch, stage):
    expected = nodes()

    def execute(command, **kwargs):
        if "--collect-only" in command:
            kwargs["stdout"].write("\n".join(expected))
            code = int(stage == "collection")
        else:
            assert "--ignore=tests/test_browser_controls.py" in command
            junit(
                Path(
                    next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml="))
                ),
                expected,
            )
            code = int(stage == "tests")
        return subprocess.CompletedProcess(command, code)

    def probe(**kwargs):
        if stage == "interruption":
            raise KeyboardInterrupt()
        if stage == "probe":
            raise RuntimeError("injected learning failure")
        return SimpleNamespace(model_dump_json=lambda **_: "{}")

    def validate(report, directory, **kwargs):
        assert not (directory / "acceptance.json").exists()
        raise ValueError("injected final validation failure")

    monkeypatch.setattr(module.subprocess, "run", execute)
    monkeypatch.setattr(module, "run_full_game_learning_probe", probe)
    monkeypatch.setattr(module, "verify_learning_matrix", lambda *_: 256)
    monkeypatch.setattr(module, "_validate_acceptance", validate)
    error = KeyboardInterrupt if stage == "interruption" else RuntimeError
    with pytest.raises(error):
        module.run_full_game_acceptance(repository_root=ROOT, output_root=tmp_path, **PATHS)
    (directory,) = tmp_path.iterdir()
    assert not (directory / "acceptance.json").exists()
    assert not (directory / "acceptance.pending.json").exists()
    failure = json.loads((directory / "failure.json").read_text())
    assert not failure["full_game_training_ready"] and not failure["promotion_eligible"]


def test_cli_runs_local_acceptance_and_reports_path(tmp_path, monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    received = []

    def run(**kwargs):
        received.append(kwargs)
        return tmp_path

    monkeypatch.setattr(module, "run_full_game_acceptance", run)
    result = CliRunner().invoke(app, ["simulation", "full-game-acceptance", "--seed", "1400010"])
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == str(tmp_path / "acceptance.json")
    assert received[0]["repository_root"] == ROOT and received[0]["seed"] == 1400010


def test_cli_verification_fails_closed_for_missing_evidence(tmp_path, manifest, monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    (tmp_path / "acceptance.json").write_text(manifest.model_dump_json())
    result = CliRunner().invoke(app, ["simulation", "full-game-acceptance-verify", str(tmp_path)])
    assert result.exit_code == 1


@pytest.mark.parametrize("summary", ["1 skipped", "2 deselected", "1 error"])
def test_incomplete_collection_is_rejected_even_when_required_workflows_are_present(summary):
    with pytest.raises(ValueError, match="collection cannot"):
        module.collected_test_nodes("\n".join(nodes()) + "\n" + summary)


def test_source_and_evidence_manifests_are_strict(manifest):
    for change in (
        {"source_tree_sha256": "0" * 64},
        {"sources": manifest.sources[:-1]},
        {"sources": tuple(reversed(manifest.sources))},
        {"evidence": manifest.evidence[:-1]},
        {"full_game_training_ready": False},
        {"schema_version": 2},
    ):
        with pytest.raises(ValueError):
            module.FullGameLocalAcceptance.model_validate(manifest.model_dump() | change)


def test_collection_environment_cannot_select_a_small_subset(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k only_one")
    monkeypatch.setenv("PYTEST_PLUGINS", "external_mutator")
    seen = []

    def fail_collection(command, **kwargs):
        seen.append(command)
        assert "PYTEST_ADDOPTS" not in kwargs["env"]
        assert "PYTEST_PLUGINS" not in kwargs["env"]
        assert "tests" in command
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(module.subprocess, "run", fail_collection)
    with pytest.raises(RuntimeError, match="collection failed"):
        module.run_full_game_acceptance(repository_root=ROOT, output_root=tmp_path, **PATHS)
    assert len(seen) == 1


@pytest.mark.parametrize("change", ["small-matrix", "failed", "limit", "configuration", "games"])
def test_learning_acceptance_rejects_incomplete_or_mismatched_matrix(change):
    # Isolate the acceptance checks; the typed probe has its own nested validation suite.
    from godfield_bot.full_game_learning_probe import FullGameLearningProbeConfig

    metadata = SimpleNamespace(model_dump=lambda **_: {"kernel": 33})
    outcomes = [SimpleNamespace(status="winner") for _ in range(8)]
    case = SimpleNamespace(
        training=SimpleNamespace(
            initial_collection=SimpleNamespace(environment=metadata),
            updates=[SimpleNamespace(outcomes=outcomes)],
        )
    )
    report = SimpleNamespace(config=FullGameLearningProbeConfig(), cases=[case] * 32, passed=True)
    audit = SimpleNamespace(metadata=metadata)
    assert module.verify_learning_matrix(report, audit) == 256
    if change == "small-matrix":
        report.cases.pop()
    elif change == "failed":
        report.passed = False
    elif change == "limit":
        outcomes[0].status = "turn-limit"
    elif change == "configuration":
        case.training.initial_collection.environment = SimpleNamespace(
            model_dump=lambda **_: {"kernel": 32}
        )
    else:
        outcomes.pop()
    with pytest.raises(ValueError):
        module.verify_learning_matrix(report, audit)
