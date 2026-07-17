import sys
from pathlib import Path

# Service root (so `from src.xxx import ...` works)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Shared vector-db lib (so `from client import ...` in vector_client.py resolves)
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "libs" / "vector-db" / "src"))
# Shared contracts lib (so `from rag import RetrieveRequest` resolves — WO-013)
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "libs" / "contracts" / "src"))
