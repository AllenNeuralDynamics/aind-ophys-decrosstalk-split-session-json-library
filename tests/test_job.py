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


def _plane(index: int, coupled: int, structure=None) -> dict:
    """Build a minimal v2 coupled plane entry."""
    return {
        "plane_index": index,
        "coupled_plane_index": coupled,
        "targeted_structure": structure
        or {"atlas": "CCFv3", "acronym": "VISp", "id": "385"},
    }


# v2 layout of a real mesoscope session: one imaging configuration whose
# image planes each name their partner.
ACQUISITION = {
    "data_streams": [
        {"configurations": [{"object_type": "Laser config"}]},
        {
            "configurations": [
                {
                    "images": [
                        {
                            "planes": [
                                _plane(0, 1),
                                _plane(1, 0),
                                _plane(2, 3),
                                _plane(3, 2),
                            ]
                        }
                    ]
                }
            ]
        },
    ]
}


class TestPairV2Planes(unittest.TestCase):
    """Pairing of v2 coupled planes."""

    def test_pairs_by_coupled_plane_index(self) -> None:
        """Pairs are numbered in plane order, lower index first."""
        self.assertEqual(
            job.pair_v2_planes(ACQUISITION),
            {0: ("VISp_0", "VISp_1"), 1: ("VISp_2", "VISp_3")},
        )

    def test_partner_listed_first(self) -> None:
        """Plane order in the file does not change the pairs."""
        planes = [_plane(3, 2), _plane(1, 0), _plane(2, 3), _plane(0, 1)]
        acquisition = {
            "data_streams": [
                {"configurations": [{"images": [{"planes": planes}]}]}
            ]
        }
        self.assertEqual(
            job.pair_v2_planes(acquisition),
            {0: ("VISp_0", "VISp_1"), 1: ("VISp_2", "VISp_3")},
        )

    def test_string_structure_and_uncoupled_plane(self) -> None:
        """A bare structure name is kept; uncoupled planes are skipped."""
        uncoupled = {"plane_index": 2, "targeted_structure": "VISl"}
        planes = [_plane(0, 1, "VISl"), _plane(1, 0, "VISl"), uncoupled]
        acquisition = {
            "data_streams": [
                {"configurations": [{"images": [{"planes": planes}]}]}
            ]
        }
        self.assertEqual(
            job.pair_v2_planes(acquisition), {0: ("VISl_0", "VISl_1")}
        )


class TestFindMetadata(unittest.TestCase):
    """Metadata file discovery."""

    def test_direct_file_wins(self) -> None:
        """A top-level file is preferred over a nested one."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw").mkdir()
            (root / "raw" / "session.json").write_text("{}")
            (root / "session.json").write_text("{}")
            self.assertEqual(
                job.find_metadata(root, "session.json"),
                root / "session.json",
            )

    def test_nested_file(self) -> None:
        """A file one level down is found."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw").mkdir()
            (root / "raw" / "session.json").write_text("{}")
            self.assertEqual(
                job.find_metadata(root, "session.json"),
                root / "raw" / "session.json",
            )

    def test_missing_returns_none(self) -> None:
        """No match gives None."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(job.find_metadata(Path(tmp), "session.json"))


class TestReadPairs(unittest.TestCase):
    """Choice of metadata version."""

    def test_acquisition_preferred_over_session(self) -> None:
        """With both files present, the v2 acquisition is read."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "acquisition.json").write_text(json.dumps(ACQUISITION))
            (root / "session.json").write_text(
                json.dumps({"data_streams": []})
            )
            self.assertEqual(len(job.read_pairs(root)), 2)

    def test_missing_names_files_and_directory(self) -> None:
        """The error states what was searched for and where."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(
                FileNotFoundError, "acquisition.json or session.json"
            ):
                job.read_pairs(Path(tmp))
            with self.assertRaisesRegex(FileNotFoundError, tmp):
                job.read_pairs(Path(tmp))


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

    def test_v2_acquisition_layout(self) -> None:
        """A session with only a nested acquisition.json gets pair files."""
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            (data / "raw").mkdir(parents=True)
            (data / "raw" / "acquisition.json").write_text(
                json.dumps(ACQUISITION)
            )
            job.run(_settings(data, Path(tmp) / "results"))
            results = Path(tmp) / "results"
            self.assertEqual(
                (results / "pair0.txt").read_text(), "VISp_0\nVISp_1\n"
            )
            self.assertEqual(
                (results / "pair1.txt").read_text(), "VISp_2\nVISp_3\n"
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
