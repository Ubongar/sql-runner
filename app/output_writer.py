"""
output_writer.py
Writes the SQL run, its result set, and any cleaning actions taken
to a .json file in outputs/.
"""

import json
import math
import os
from datetime import datetime, date
from decimal import Decimal

try:
    import numpy as np
except ImportError:  # numpy should always be present via pandas, but don't hard-fail
    np = None


def _sanitize(obj):
    """
    Recursively converts numpy scalar types (which the default json module
    cannot serialize and which _default() alone can't reach inside nested
    lists/dicts) into plain Python types, and turns NaN into null so the
    output file is always valid JSON.
    """
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if np is not None:
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            val = float(obj)
            return None if math.isnan(val) else val
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return _sanitize(obj.tolist())
    return obj


def _default(obj):
    if isinstance(obj, (Decimal, datetime, date)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def write_output(sql: str, result: list, cleaning_report: list | None = None, output_dir: str = "outputs") -> str:
    os.makedirs(output_dir, exist_ok=True)
    # Microsecond precision (was second-level before) so two runs completing
    # within the same second no longer overwrite each other's output file.
    filename = f"result_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    filepath = os.path.join(output_dir, filename)

    output = {
        "sql": sql,
        "result": _sanitize(result),
        "data_cleaned": bool(cleaning_report),
        "cleaning_report": _sanitize(cleaning_report or []),
    }

    with open(filepath, "w") as f:
        json.dump(output, f, default=_default, indent=2)

    return filepath