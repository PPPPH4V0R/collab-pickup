# The committed openapi.json is the contract clients program against.
# This test fails when the code's API changes but the contract file was
# not updated (fix: python scripts/export_openapi.py, then review the diff).
# Run from the project root: python -m pytest -q tests/test_contract.py
import json
from pathlib import Path
from app.main import app

CONTRACT = Path(__file__).resolve().parent.parent / "openapi.json"


def test_committed_contract_matches_the_code():
    committed = json.loads(CONTRACT.read_text(encoding="utf-8"))
    generated = json.loads(json.dumps(app.openapi()))     # same JSON types as the file
    assert generated == committed
