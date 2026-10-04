"""Census ZCTA centroids (no key). Written as the tab-separated file that
analysis.catchment.load_centroids reads."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from .http import Fetch, http_get

URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{year}_Gazetteer/{year}_Gaz_zcta_national.zip"
DEFAULT_PATH = Path("data/reference/zcta_gazetteer.txt")


def download(year: int = 2023, dest: Path | str = DEFAULT_PATH, fetch: Fetch = http_get) -> Path:
    blob = fetch(URL.format(year=year))
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        text = z.read(name)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(text)
    return dest
