"""RAG evaluation tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from evaluator import run_evaluation, faithfulness, load_cases


def test_load_20_cases():
    cases = load_cases()
    assert len(cases) == 20


def test_faithfulness_high_for_grounded_answer():
    score = faithfulness("Machine learning is AI.", ["Machine learning is a subset of AI."])
    assert score > 0.3


def test_run_evaluation():
    result = run_evaluation()
    assert result["cases_evaluated"] == 20
    assert "hallucination_rate" in result
    assert result["avg_faithfulness"] >= 0
