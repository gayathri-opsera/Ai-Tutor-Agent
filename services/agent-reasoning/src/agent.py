"""ReAct agent reasoning loop."""
from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class ReasoningStep:
    thought: str
    action: str
    action_input: str
    observation: str


@dataclass
class ReasoningTrace:
    query: str
    sub_queries: list[str] = field(default_factory=list)
    steps: list[ReasoningStep] = field(default_factory=list)
    final_answer: str = ""


RetrieverFn = Callable[[str], Awaitable[list[dict]]]
WebSearchFn = Callable[[str, float], Awaitable[list[dict]]]


def decompose_query(query: str) -> list[str]:
    parts = re.split(r"\band\b|\?", query, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()] or [query]


def _calculator(expr: str) -> str:
    allowed = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg,
    }
    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            return allowed[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            return allowed[type(node.op)](_eval(node.operand))
        raise ValueError("Unsupported expression")
    tree = ast.parse(expr.strip(), mode="eval")
    return str(_eval(tree.body))


class ReActAgent:
    MAX_ITERATIONS = 5

    def __init__(
        self,
        retriever: RetrieverFn | None = None,
        web_search: WebSearchFn | None = None,
    ) -> None:
        self.retriever = retriever
        self.web_search = web_search

    async def reason(self, query: str, confidence: float = 0.8) -> ReasoningTrace:
        trace = ReasoningTrace(query=query, sub_queries=decompose_query(query))
        context: list[dict] = []

        for i in range(self.MAX_ITERATIONS):
            sub_q = trace.sub_queries[min(i, len(trace.sub_queries) - 1)]
            thought = f"Need to find information about: {sub_q}"
            action = "retriever"
            action_input = sub_q
            observation = ""

            if re.search(r"\d+\s*[\+\-\*/]\s*\d+", query) and i == 0:
                action = "calculator"
                match = re.search(r"[\d\+\-\*/\.\(\)\s]+", query)
                action_input = match.group(0) if match else "0"
                try:
                    observation = _calculator(action_input)
                except Exception as exc:
                    observation = f"Calculator error: {exc}"
            elif self.retriever and action == "retriever":
                chunks = await self.retriever(sub_q)
                context.extend(chunks)
                observation = "; ".join(c.get("text", "")[:100] for c in chunks) or "No results"
            elif self.web_search and confidence < 0.5:
                action = "web_search"
                web_chunks = await self.web_search(sub_q, confidence)
                context.extend(web_chunks)
                observation = f"Found {len(web_chunks)} web results"

            trace.steps.append(ReasoningStep(thought, action, action_input, observation))
            if observation and i >= len(trace.sub_queries) - 1:
                break

        trace.final_answer = observation or "Unable to determine answer"
        return trace
