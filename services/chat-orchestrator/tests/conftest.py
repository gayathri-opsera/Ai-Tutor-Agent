import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

# Add libs/contracts/src so `from rag import RetrieveRequest` resolves (WO-013)
_REPO_ROOT = _SERVICE_ROOT.parents[1]
sys.path.insert(0, str(_REPO_ROOT / "libs" / "contracts" / "src"))
