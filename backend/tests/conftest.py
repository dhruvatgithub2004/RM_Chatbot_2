import os
import tempfile

# Tests must be offline, deterministic and must never touch the live database.
os.environ["SKIP_LLM_SUGGESTIONS"] = "1"
_tmp = tempfile.mkdtemp(prefix="rm_copilot_test_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "test.db").replace("\\", "/")
os.environ["AUDIT_LOG_PATH"] = os.path.join(_tmp, "audit.jsonl").replace("\\", "/")
os.environ["QUALITY_REPORT_PATH"] = os.path.join(_tmp, "quality.json")

import pytest  # noqa: E402

from app import ingest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def loaded():
    return ingest.run(verbose=False)
