"""RAG quality evaluation — RAGAS-inspired metrics."""
from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass


@dataclass
class EvalCase:
    query: str
    context: list[str]
    answer: str
    expected_answer: str


def load_cases() -> list[EvalCase]:
    path = Path(__file__).parent / "fixtures" / "eval_cases.json"
    data = json.loads(path.read_text())
    return [EvalCase(**c) for c in data]


def token_overlap(a: str, b: str) -> float:
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def faithfulness(answer: str, context: list[str]) -> float:
    """Measure if answer is grounded in context."""
    ctx_text = " ".join(context)
    return token_overlap(answer, ctx_text)


def context_recall(context: list[str], expected: str) -> float:
    return max(token_overlap(c, expected) for c in context) if context else 0.0


def answer_relevancy(query: str, answer: str) -> float:
    return token_overlap(query, answer)


def hallucination_rate(cases: list[EvalCase], threshold: float = 0.3) -> float:
    hallucinated = 0
    for case in cases:
        if faithfulness(case.answer, case.context) < threshold:
            hallucinated += 1
    return hallucinated / max(len(cases), 1)


def run_evaluation() -> dict:
    cases = load_cases()
    results = []
    for case in cases:
        results.append({
            "query": case.query,
            "faithfulness": faithfulness(case.answer, case.context),
            "context_recall": context_recall(case.context, case.expected_answer),
            "answer_relevancy": answer_relevancy(case.query, case.answer),
        })
    avg = lambda key: sum(r[key] for r in results) / max(len(results), 1)
    return {
        "cases_evaluated": len(cases),
        "avg_faithfulness": round(avg("faithfulness"), 3),
        "avg_context_recall": round(avg("context_recall"), 3),
        "avg_answer_relevancy": round(avg("answer_relevancy"), 3),
        "hallucination_rate": round(hallucination_rate(cases), 3),
        "results": results,
    }
