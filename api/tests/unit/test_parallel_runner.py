"""Unit tests for the parallel test suite partitioner invariants."""

import re
from pathlib import Path

from tools.run_parallel_tests import SERIAL_FILES, is_browser_file, partition_files

CLUSTER_MUTATION_RE = re.compile(
    r"(?:create|alter|drop)\s+role\b|"
    r"(?:grant|revoke)\s+(?:gba_runtime|gba_receipt_writer|gba_receipt_worker|gba_test_)\b|"
    r"drop\s+function\b",
    re.IGNORECASE,
)


def test_partition_is_disjoint_complete_and_preserves_serial_order() -> None:
    api_dir = Path(__file__).resolve().parents[2]
    all_files = sorted(
        str(p.relative_to(api_dir)).replace("\\", "/")
        for p in (api_dir / "tests").rglob("test_*.py")
    )
    part = partition_files(all_files, workers=6, api_dir=api_dir)

    assert part.serial == [f for f in SERIAL_FILES if f in set(all_files)]
    assert part.serial[0] == "tests/integration/test_location_access.py"
    assert all(is_browser_file(f) for f in part.browser)
    assert len(part.parallel_buckets) == 6
    combined = [*part.serial, *part.browser, *(f for b in part.parallel_buckets for f in b)]
    assert len(combined) == len(all_files)
    assert set(combined) == set(all_files)


def test_all_cluster_role_and_function_drop_tests_are_in_serial_lane() -> None:
    api_dir = Path(__file__).resolve().parents[2]
    serial_set = set(SERIAL_FILES)
    missing: list[str] = []
    for path in sorted((api_dir / "tests/integration").glob("test_*.py")):
        rel = str(path.relative_to(api_dir)).replace("\\", "/")
        if CLUSTER_MUTATION_RE.search(path.read_text(encoding="utf-8")) and rel not in serial_set:
            missing.append(rel)
    assert missing == [], f"Add cluster/DDL-mutating tests to SERIAL_FILES: {missing}"
