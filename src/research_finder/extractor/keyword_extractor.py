from __future__ import annotations

import json
from typing import Any

from litellm import completion


EXTRACTION_PROMPT = """\
You are a research assistant. Given the following text written by a researcher, generate search queries to find relevant academic papers.

Return a JSON object with exactly this structure:
{{
    "keywords": ["keyword1", "keyword2", ...],
    "queries": [
        "keyword1 keyword2 keyword3",
        "keyword4 keyword5 keyword6",
        "keyword7 keyword8 keyword9"
    ]
}}

Requirements:
- Extract 5-15 keywords that capture the core academic topics, methods, and theories.
- Generate 5-7 search queries, each covering a DIFFERENT aspect or angle of the text (methods, theory, domain, application, policy, etc.) so together they give broad coverage.
- Each query is 2-5 keywords joined by spaces — NO filler words like "in", "for", "of", "using", "based", "with", "and".
- Use precise academic/technical terms from the text.

Text:
{text}
"""


class KeywordExtractor:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.llm_config = config.get("llm", {})

    def extract(self, text: str) -> list[str]:
        """Extract keywords and return search queries."""
        provider = self.llm_config.get("provider", "openai")
        model = self.llm_config.get("model", "gpt-4o-mini")
        api_key = self.llm_config.get("api_key", "")

        # Build litellm model string
        model_str = f"{provider}/{model}" if provider != "openai" else model

        response = completion(
            model=model_str,
            messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(text=text)}],
            api_key=api_key or None,
            temperature=0.3,
        )

        content = response.choices[0].message.content
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        if content.startswith("```json"):
            content = content[7:].rsplit("```", 1)[0]

        parsed = json.loads(content)
        return parsed.get("queries", [])
