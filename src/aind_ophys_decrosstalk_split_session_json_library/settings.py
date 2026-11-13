"""CLI/environment settings for the decrosstalk session split."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class SplitSessionSettings(BaseSettings, cli_parse_args=True):
    """Settings for writing paired-plane lists from a session JSON."""

    input_dir: Path = Field(
        default=Path("../data/"),
        description=(
            "Directory containing session.json (directly or one level "
            "down) and the per-plane motion-correction directories."
        ),
    )
    output_dir: Path = Field(
        default=Path("../results/"),
        description="Directory where the pair<k>.txt files are written.",
    )
