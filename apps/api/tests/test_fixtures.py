from pathlib import Path

from ion_api.fixtures import load_synthetic_fixture


def test_phase_0b_fixture_is_explicitly_synthetic():
    root = Path(__file__).resolve().parents[3]
    fixture = load_synthetic_fixture(root / "fixtures/synthetic/phase-0b.json")

    assert fixture["synthetic"] is True
    assert fixture["records"][0]["id"].startswith("synthetic-")


def test_phase_1a_task_fixture_is_explicitly_synthetic():
    root = Path(__file__).resolve().parents[3]
    fixture = load_synthetic_fixture(root / "fixtures/synthetic/phase-1a-tasks.json")

    assert fixture["tasks"][0]["id"].startswith("synthetic-")
