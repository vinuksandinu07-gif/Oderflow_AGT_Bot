from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import json


def export_json(data: Dict[str, Any], path: str) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(path_obj, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
