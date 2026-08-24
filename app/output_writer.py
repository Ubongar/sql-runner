"""
output_writer.py
Writes the SQL run, its result set, and any cleaning actions taken
to a .json file in outputs/.
"""

import json
import os
from datetime import datetime, date
from decimal import Decimal


def _default(obj):
    if isinstance(obj, (Decimal, datetime, date)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def write_output(sql: str, result: list, cleaning_report: list | None = None, output_dir: str = "outputs") -> str:
    os.makedirs(output_dir, exist_ok=True)
    filename = f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(output_dir, filename)

    output = {
        "sql": sql,
        "result": result,
        "data_cleaned": bool(cleaning_report),
        "cleaning_report": cleaning_report or [],
    }

    with open(filepath, "w") as f:
        json.dump(output, f, default=_default, indent=2)

    return filepath