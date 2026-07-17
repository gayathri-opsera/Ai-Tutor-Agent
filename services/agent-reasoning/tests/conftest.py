import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT / "src"))
sys.path.insert(0, str(_SERVICE_ROOT.parents[1] / "libs" / "contracts" / "src"))
