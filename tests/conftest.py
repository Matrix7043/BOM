import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="mmm-test-"))
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))
