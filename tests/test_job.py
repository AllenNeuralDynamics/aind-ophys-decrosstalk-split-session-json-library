"""Tests for the session split job."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aind_ophys_decrosstalk_split_session_json_library import job
from aind_ophys_decrosstalk_split_session_json_library.settings import (
    SplitSessionSettings,
)


def _fov(index: int, coupled_fov_index: int) -> dict:
    """Build a minimal ophys FOV entry."""
    return {
        "index": index,
        "coupled_fov_index": coupled_fov_index,
        "targeted_structure": "VISp",
    }


# Layout of a real multiplane session: pairs share coupled_fov_index and are
# adjacent in FOV order.
SESSION = {
    "data_streams": [
        {"ophys_fovs": []},
        {
            "ophys_fovs": [
                _fov(0, 0),
                _fov(1, 0),
                _fov(2, 1),
                _fov(3, 1),
            ]
        },
    ]
}


def _settings(input_dir: Path, output_dir: Path) -> SplitSessionSettings:
    """Construct settings with a clean ``sys.argv``."""
    with patch.object(sys, "argv", ["run_capsule.py"]):
        return SplitSessionSettings(input_dir=input_dir, output_dir=output_dir)


class TestPairPlanes(unittest.TestCase):
    """Pairing of coupled FOVs."""

    def test_pairs_adjacent_coupled_fovs(self) -> None:
        """Each shared coupled_fov_index yields one ordered pair."""
        self.assertEqual(
            job.pair_planes(SESSION),
            {0: ("VISp_0", "VISp_1"), 1: ("VISp_2", "VISp_3")},
        )

    def test_streams_without_fovs_are_skipped(self) -> None:
        """A stream with no ophys_fovs key contributes nothing."""
        self.assertEqual(job.pair_planes({"data_streams": [{}]}), {})


class TestFindSessionJson(unittest.TestCase):
    """Session JSON discovery."""

    def test_direct_file_wins(self) -> None:
        """A top-level session.json is preferred over a nested one."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw").mkdir()
            (root / "raw" / "session.json").write_text("{}")
            (root / "session.json").write_text("{}")
            self.assertEqual(
                job.find_session_json(root), root / "session.json"
            )

    def test_nested_file(self) -> None:
        """A session.json one level down is found."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw").mkdir()
            (root / "raw" / "session.json").write_text("{}")
            self.assertEqual(
                job.find_session_json(root), root / "raw" / "session.json"
            )

    def test_missing_names_pattern_and_directory(self) -> None:
        """The error states what was searched for and where."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "session.json"):
                job.find_session_json(Path(tmp))
            with self.assertRaisesRegex(FileNotFoundError, tmp):
                job.find_session_json(Path(tmp))


class TestRun(unittest.TestCase):
    """End-to-end run in a task-relative layout."""

    def test_task_relative_layout(self) -> None:
        """Reads and writes stay in the task; pair files hold bare names.

        Mirrors a Nextflow task that has ``data/`` and ``results/`` beside
        ``code/`` and no ``/data`` or ``/results`` at the filesystem root.
        """
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp)
            (task / "code").mkdir()
            data = task / "data"
            data.mkdir()
            (data / "session.json").write_text(json.dumps(SESSION))
            written = job.run(
                _settings(
                    task / "code" / ".." / "data",
                    task / "code" / ".." / "results",
                )
            )
            results = task / "results"
            self.assertEqual(
                sorted(p.name for p in results.iterdir()),
                ["pair0.txt", "pair1.txt"],
            )
            self.assertEqual(len(written), 2)
            self.assertEqual(
                (results / "pair0.txt").read_text(), "VISp_0\nVISp_1\n"
            )
            self.assertEqual(
                (results / "pair1.txt").read_text(), "VISp_2\nVISp_3\n"
            )
            self.assertEqual(
                sorted(p.name for p in task.iterdir()),
                ["code", "data", "results"],
            )

    def test_settings_from_cli_when_omitted(self) -> None:
        """Without explicit settings, run() parses them from argv."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session.json").write_text(json.dumps(SESSION))
            argv = [
                "run_capsule.py",
                f"--input_dir={root}",
                f"--output_dir={root / 'out'}",
            ]
            with patch.object(sys, "argv", argv):
                written = job.run()
            self.assertEqual(
                [p.name for p in written], ["pair0.txt", "pair1.txt"]
            )


if __name__ == "__main__":
    unittest.main()
