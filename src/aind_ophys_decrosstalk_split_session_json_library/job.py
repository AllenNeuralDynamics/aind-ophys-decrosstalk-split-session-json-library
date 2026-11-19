"""Write one pair<k>.txt file per coupled plane pair in a session's metadata.

Pairs come from a v2 ``acquisition.json`` when present, otherwise from a v1
``session.json``. Each pair file lists the two plane directory names, one per
line. The names are relative to the consumer's input directory, so the files
stay valid wherever the planes are staged.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from aind_ophys_decrosstalk_split_session_json_library.settings import (
    SplitSessionSettings,
)

SESSION_JSON = "session.json"
ACQUISITION_JSON = "acquisition.json"

logger = logging.getLogger(__name__)


def find_metadata(input_dir: Path, name: str) -> Optional[Path]:
    """Locate ``name`` directly in or one level below ``input_dir``.

    Parameters
    ----------
    input_dir : Path
        Directory to search.
    name : str
        File name to find.

    Returns
    -------
    Path or None
        The top-level file when present, else the first nested match, else
        None.
    """
    direct = input_dir / name
    if direct.is_file():
        return direct
    return next(iter(sorted(input_dir.glob(f"*/{name}"))), None)


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


def v2_plane_name(plane: dict) -> str:
    """Return the plane directory name for a v2 coupled plane.

    Parameters
    ----------
    plane : dict
        One entry of an imaging configuration image's ``planes``.

    Returns
    -------
    str
        ``<targeted structure acronym>_<plane_index>``.
    """
    structure = plane["targeted_structure"]
    if isinstance(structure, dict):
        structure = structure["acronym"]
    return f"{structure}_{plane['plane_index']}"


def pair_v2_planes(acquisition: dict) -> Dict[int, Tuple[str, str]]:
    """Group the coupled planes of a v2 acquisition into plane-name pairs.

    v2 records each plane's partner as ``coupled_plane_index``. Pairs are
    numbered in plane-index order, which matches v1's ``coupled_fov_index``.

    Parameters
    ----------
    acquisition : dict
        Parsed acquisition JSON.

    Returns
    -------
    dict of int to tuple of str
        Pair number mapped to the two plane names, lower plane index first.
    """
    planes: Dict[int, Tuple[int, str]] = {}
    for data_stream in acquisition["data_streams"]:
        for config in data_stream.get("configurations") or []:
            for image in config.get("images") or []:
                for plane in image.get("planes") or []:
                    if plane.get("coupled_plane_index") is None:
                        continue
                    planes[plane["plane_index"]] = (
                        plane["coupled_plane_index"],
                        v2_plane_name(plane),
                    )
    pairs: Dict[int, Tuple[str, str]] = {}
    paired = set()
    for index in sorted(planes):
        if index in paired:
            continue
        partner, name = planes[index]
        paired.update((index, partner))
        pairs[len(pairs)] = (name, planes[partner][1])
    return pairs


def read_pairs(input_dir: Path) -> Dict[int, Tuple[str, str]]:
    """Read the plane pairs from the session metadata in ``input_dir``.

    Parameters
    ----------
    input_dir : Path
        Directory holding ``acquisition.json`` or ``session.json``, directly
        or one level down.

    Returns
    -------
    dict of int to tuple of str
        Pair number mapped to the two plane names.

    Raises
    ------
    FileNotFoundError
        If neither metadata file is found.
    """
    acquisition = find_metadata(input_dir, ACQUISITION_JSON)
    if acquisition is not None:
        logger.info("Pairing planes from %s", acquisition)
        return pair_v2_planes(json.loads(acquisition.read_text()))
    session = find_metadata(input_dir, SESSION_JSON)
    if session is not None:
        logger.info("Pairing planes from %s", session)
        return pair_planes(json.loads(session.read_text()))
    raise FileNotFoundError(
        f"No {ACQUISITION_JSON} or {SESSION_JSON} found in {input_dir} "
        "or one level below it"
    )


def write_pair_files(
    pairs: Dict[int, Tuple[str, str]], output_dir: Path
) -> List[Path]:
    """Write ``pair<k>.txt`` for each pair.

    Parameters
    ----------
    pairs : dict of int to tuple of str
        Output of :func:`read_pairs`.
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
    written = write_pair_files(
        read_pairs(settings.input_dir), settings.output_dir
    )
    for path in written:
        logger.info("Wrote %s", path)
    return written
