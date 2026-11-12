# Writes the contract that FastAPI generates to openapi.json.
# Run from the project root: python scripts/export_openapi.py
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                 # so "app" can be imported

from app.main import app

(ROOT / "openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print("Wrote openapi.json")
