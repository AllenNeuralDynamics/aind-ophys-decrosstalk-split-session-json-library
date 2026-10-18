"""Write one pair<k>.txt file per coupled plane pair in a session JSON.

Each pair file lists the two plane directory names, one per line. The names
are relative to the consumer's input directory, so the files stay valid
wherever the planes are staged.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from aind_ophys_decrosstalk_split_session_json_library.settings import (
    SplitSessionSettings,
)

SESSION_JSON = "session.json"

logger = logging.getLogger(__name__)


def find_session_json(input_dir: Path) -> Path:
    """Locate session.json directly in or one level below ``input_dir``.

    Parameters
    ----------
    input_dir : Path
        Directory to search.

    Returns
    -------
    Path
        Path to the session JSON.

    Raises
    ------
    FileNotFoundError
        If neither ``session.json`` nor ``*/session.json`` matches.
    """
    direct = input_dir / SESSION_JSON
    if direct.is_file():
        return direct
    nested = next(iter(sorted(input_dir.glob(f"*/{SESSION_JSON}"))), None)
    if nested is None:
        raise FileNotFoundError(
            f"No {SESSION_JSON} or */{SESSION_JSON} found in {input_dir}"
        )
    return nested


def plane_name(fov: dict) -> str:
    """Return the plane directory name for an ophys FOV.

    Parameters
    ----------
    fov : dict
        One entry of a data stream's ``ophys_fovs``.

    Returns
    -------
    str
        ``<targeted_structure>_<index>``.
    """
    return f"{fov['targeted_structure']}_{fov['index']}"


def pair_planes(session_data: dict) -> Dict[int, Tuple[str, str]]:
    """Group coupled FOVs into plane-name pairs.

    A pair is closed when the second FOV naming the same
    ``coupled_fov_index`` follows the first, so coupled FOVs must be
    adjacent in ``ophys_fovs`` order.

    Parameters
    ----------
    session_data : dict
        Parsed session JSON.

    Returns
    -------
    dict of int to tuple of str
        ``coupled_fov_index`` of the second FOV mapped to the two plane names
        in FOV order.
    """
    pairs: Dict[int, Tuple[str, str]] = {}
    open_pairs: List[int] = []
    first = ""
    for data_stream in session_data["data_streams"]:
        for fov in data_stream.get("ophys_fovs") or []:
            coupled_fov_index = fov["coupled_fov_index"]
            if coupled_fov_index in open_pairs:
                pairs[coupled_fov_index] = (first, plane_name(fov))
                open_pairs = []
            else:
                first = plane_name(fov)
                open_pairs.append(coupled_fov_index)
    return pairs


def write_pair_files(
    pairs: Dict[int, Tuple[str, str]], output_dir: Path
) -> List[Path]:
    """Write ``pair<k>.txt`` for each pair.

    Parameters
    ----------
    pairs : dict of int to tuple of str
        Output of :func:`pair_planes`.
    output_dir : Path
        Directory to write into; created if missing.

    Returns
    -------
    list of Path
        Written files, in pair order.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for coupled_fov_index, (first, second) in pairs.items():
        path = output_dir / f"pair{coupled_fov_index}.txt"
        path.write_text(f"{first}\n{second}\n")
        written.append(path)
    return written


def run(settings: Optional[SplitSessionSettings] = None) -> List[Path]:
    """Write the pair files for the session in ``settings.input_dir``.

    Parameters
    ----------
    settings : SplitSessionSettings, optional
        Parsed settings; constructed from CLI/env when omitted.

    Returns
    -------
    list of Path
        Written pair files.
    """
    settings = settings or SplitSessionSettings()
    session_json = find_session_json(settings.input_dir)
    with open(session_json, "r") as f:
        session_data = json.load(f)
    written = write_pair_files(pair_planes(session_data), settings.output_dir)
    for path in written:
        logger.info("Wrote %s", path)
    return written
