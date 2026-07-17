import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT / "src"))
# Add libs/contracts/src so `from llm import ...` resolves (WO-014)
sys.path.insert(0, str(_SERVICE_ROOT.parents[1] / "libs" / "contracts" / "src"))
