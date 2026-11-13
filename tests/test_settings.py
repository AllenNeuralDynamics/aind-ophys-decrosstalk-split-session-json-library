"""Tests for SplitSessionSettings."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from aind_ophys_decrosstalk_split_session_json_library.settings import (
    SplitSessionSettings,
)


class TestSplitSessionSettings(unittest.TestCase):
    """Settings defaults and CLI parsing."""

    def test_defaults_are_task_relative(self) -> None:
        """Defaults resolve against the working directory, not root."""
        with patch.object(sys, "argv", ["run_capsule.py"]):
            settings = SplitSessionSettings()
        self.assertEqual(settings.input_dir, Path("../data/"))
        self.assertEqual(settings.output_dir, Path("../results/"))

    def test_cli_named_parameters(self) -> None:
        """Every field parses from the ``--name=value`` form CO emits."""
        argv = ["run_capsule.py", "--input_dir=in", "--output_dir=out"]
        with patch.object(sys, "argv", argv):
            settings = SplitSessionSettings()
        self.assertEqual(settings.input_dir, Path("in"))
        self.assertEqual(settings.output_dir, Path("out"))

    def test_no_single_character_field_names(self) -> None:
        """Single-character names become short options CO cannot emit."""
        for name in SplitSessionSettings.model_fields:
            self.assertGreater(len(name), 1, name)


if __name__ == "__main__":
    unittest.main()
