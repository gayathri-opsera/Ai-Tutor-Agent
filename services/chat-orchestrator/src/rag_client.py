"""RAG retrieval, web search, and demo fallback helpers."""
from __future__ import annotations

import logging

import httpx

from rag import RetrieveRequest  # shared contract from libs/contracts (WO-013)
from src.models import AGENT_REASONING_URL, RAG_SERVICE_URL

logger = logging.getLogger(__name__)


def _demo_answer(question: str) -> str:
    """Return a rich educational fallback when the LLM backend is unavailable."""
    q = question.lower()

    if any(w in q for w in ["python", "variable", "function", "class", "loop", "list", "dict", "tuple"]):
        return (
            "## Python Overview\n\n"
            "Python is a **high-level, dynamically typed** language favoured for its readable syntax.\n\n"
            "### Key concepts\n"
            "- **Variables** — no declaration needed: `x = 42`\n"
            "- **Functions** — `def greet(name): return f'Hello, {name}'`\n"
            "- **Classes** — `class Dog: def __init__(self, name): self.name = name`\n"
            "- **Lists** — mutable sequences: `nums = [1, 2, 3]`\n"
            "- **Dicts** — key-value pairs: `person = {'name': 'Alice', 'age': 30}`\n\n"
            "```python\n# Quick example\nfor i in range(5):\n    print(f'Step {i}')\n```\n\n"
            "> **Note:** The AI backend is currently unavailable (check Anthropic billing at console.anthropic.com). This is a built-in demo answer."
        )

    if any(w in q for w in ["async", "await", "coroutine", "asyncio", "event loop", "non-blocking"]):
        return (
            "## Async Programming in Python\n\n"
            "Async lets you run **non-blocking I/O** in a single thread using `asyncio`.\n\n"
            "```python\nimport asyncio\n\nasync def fetch(url):\n    # await pauses this coroutine without blocking the thread\n    await asyncio.sleep(1)\n    return f'Response from {url}'\n\nasync def main():\n    result = await fetch('https://api.example.com')\n    print(result)\n\nasyncio.run(main())\n```\n\n"
            "**Use async for:** HTTP requests, DB queries, file I/O\n"
            "**Avoid for:** CPU-heavy tasks (use `multiprocessing` instead)\n\n"
            "> **Note:** The AI backend is temporarily unavailable (Anthropic billing needed). This is a built-in demo answer."
        )

    if any(w in q for w in ["machine learning", "ml", "model", "regression", "classification", "neural", "train", "supervised", "unsupervised"]):
        return (
            "## Machine Learning Basics\n\n"
            "Machine learning teaches computers to learn patterns from data without being explicitly programmed.\n\n"
            "### Main types\n"
            "| Type | How it works | Example |\n"
            "|------|--------------|---------|\n"
            "| **Supervised** | Learns from labelled data | Spam detection |\n"
            "| **Unsupervised** | Finds hidden structure | Customer clustering |\n"
            "| **Reinforcement** | Learns by reward/penalty | Game-playing AI |\n\n"
            "```python\nfrom sklearn.linear_model import LinearRegression\nmodel = LinearRegression()\nmodel.fit(X_train, y_train)\npredictions = model.predict(X_test)\n```\n\n"
            "> **Note:** The AI backend is temporarily unavailable (Anthropic billing needed). This is a built-in demo answer."
        )

    if any(w in q for w in ["linear regression", "logistic", "gradient", "loss", "epoch", "weight", "bias", "feature"]):
        return (
            "## Linear Regression\n\n"
            "Fits a line `y = β₀ + β₁x` by minimising the **Sum of Squared Residuals**.\n\n"
            "```python\nfrom sklearn.linear_model import LinearRegression\nimport numpy as np\n\nX = np.array([[1],[2],[3],[4],[5]])\ny = np.array([2, 4, 5, 4, 5])\nmodel = LinearRegression().fit(X, y)\nprint(f'Slope: {model.coef_[0]:.2f}, Intercept: {model.intercept_:.2f}')\n```\n\n"
            "**Key assumptions:** Linearity, independence, normality of residuals, homoscedasticity.\n\n"
            "> **Note:** The AI backend is temporarily unavailable (Anthropic billing needed). This is a built-in demo answer."
        )

    return (
        f"## Answer to: *{question[:80]}*\n\n"
        "I can help you understand this topic! However, the AI backend is temporarily unavailable.\n\n"
        "**To enable live AI answers:**\n"
        "1. Go to **console.anthropic.com → Settings → Billing**\n"
        "2. Add a payment method and purchase credits\n"
        "3. The chatbot will automatically start giving real answers\n\n"
        "In the meantime, try asking about:\n"
        "- Python variables, functions, classes, loops\n"
        "- Async programming with asyncio\n"
        "- Machine learning concepts\n"
        "- Linear regression and classification\n\n"
        "> Built-in demo mode — real AI responses activate once billing is configured."
    )


async def _fetch_rag_context(
    query: str, knowledge_base_id: str | None, top_k: int = 5
) -> list[dict]:
    """Call the RAG pipeline to get relevant chunks. Returns [] on any failure."""
    if not knowledge_base_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{RAG_SERVICE_URL}/api/internal/rag/retrieve",
                json=RetrieveRequest(
                    query=query,
                    knowledge_base_id=knowledge_base_id,
                    top_k=top_k,
                ).model_dump(),
            )
            if resp.is_success:
                data = resp.json()
                return data.get("chunks", data.get("results", []))
    except Exception as exc:
        logger.debug("RAG retrieval skipped: %s", exc)
    return []


async def _fetch_web_context(query: str) -> list[dict]:
    """Call agent-reasoning to trigger a real-time web search.

    Only invoked when RAG retrieval returns no results so general-knowledge
    questions can still get helpful, up-to-date answers.
    Returns [] on any failure so the chat flow always continues.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{AGENT_REASONING_URL}/api/internal/agent/reason",
                json={
                    "query": query,
                    # confidence=0 forces the agent to trigger web_search immediately
                    "confidence": 0.0,
                },
            )
            if resp.is_success:
                data = resp.json()
                web_chunks: list[dict] = []
                for step in data.get("steps", []):
                    if step.get("action") == "web_search" and step.get("observation"):
                        web_chunks.append({
                            "text": step["observation"],
                            "document_title": "Web Search",
                            "score": 0.5,
                        })
                if data.get("final_answer") and not web_chunks:
                    web_chunks.append({
                        "text": data["final_answer"],
                        "document_title": "Web Search",
                        "score": 0.5,
                    })
                return web_chunks
    except Exception as exc:
        logger.debug("Web search skipped: %s", exc)
    return []
