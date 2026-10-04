"""NHTSA vPIC VIN decoding (free, no key). Enriches listing snapshots with
body class, drivetrain, fuel and engine so comps can be grouped properly."""
from __future__ import annotations

import json
import sqlite3
from typing import Callable

from .http import http_post_form

BATCH_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/"
FIELDS = {"BodyClass": "body_class", "DriveType": "drive_type", "FuelTypePrimary": "fuel",
          "DisplacementL": "displacement_l", "EngineCylinders": "cylinders",
          "ErrorCode": "error_code"}
Post = Callable[[str, dict], bytes]


def decode(conn: sqlite3.Connection, vins: list[str], post: Post = http_post_form) -> int:
    """Decode VINs not already stored, 50 per call (the API maximum)."""
    have = {r[0] for r in conn.execute("SELECT vin FROM vin_decode")}
    todo = [v for v in dict.fromkeys(v.upper() for v in vins) if v and v not in have]
    written = 0
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        resp = json.loads(post(BATCH_URL, {"format": "json", "data": ";".join(chunk)}))
        for r in resp.get("Results", []):
            conn.execute(
                "INSERT OR REPLACE INTO vin_decode (vin, body_class, drive_type, fuel, "
                "displacement_l, cylinders, error_code) VALUES (?,?,?,?,?,?,?)",
                (r.get("VIN", "").upper(), *(r.get(k) or None for k in list(FIELDS)[:-1]),
                 r.get("ErrorCode")))
            written += 1
    conn.commit()
    return written
