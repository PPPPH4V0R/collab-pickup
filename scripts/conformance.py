# Conformance check: Schemathesis reads the running service's contract,
# generates many requests for every operation (valid and invalid), and
# checks two things on every response:
#   not_a_server_error           -- never a 5xx
#   response_schema_conformance  -- the body matches the schema the contract promises
# Requests carry Alice's token, so staff-only operations answer 403 (which
# the contract documents). It places many orders, so the demo data is
# reset afterwards. The report is also saved to conformance_output.txt.
#
# Start the service first, then from the project root:
#   python scripts/conformance.py
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                     # import app/ and seed.py

import httpx
from sqlalchemy import create_engine
from app.config import settings
import seed

API = os.environ.get("API_URL", "http://127.0.0.1:8000")
SCHEMATHESIS = Path(sys.executable).parent / "schemathesis"   # installed next to python

token = httpx.post(f"{API}/auth/login", json={
    "username": "alice", "password": os.environ["DEMO_PASSWORD"]}).json()["accessToken"]

result = subprocess.run(
    [str(SCHEMATHESIS), "run", f"{API}/openapi.json",
     "--checks", "not_a_server_error,response_schema_conformance",
     "--header", f"Authorization: Bearer {token}",
     "--max-examples", "50",
     "--seed", "387",                             # same requests every run
     "--generation-database", "none",             # keep nothing on disk between runs
     "--no-color"],
    capture_output=True, text=True, encoding="utf-8",
    env={**os.environ, "PYTHONUTF8": "1"})        # Windows: report in UTF-8, not the code page
report = result.stdout + result.stderr
sys.stdout.reconfigure(errors="replace")         # the report has emoji a Windows console may lack
print(report)
(ROOT / "conformance_output.txt").write_text(report, encoding="utf-8")

seed.reset(create_engine(settings.database_url))
print("Demo data reset.")
sys.exit(result.returncode)
