import json
from agents.base_agent import run_agent

async def detect_conflict(output_a: str, output_b: str, label_a: str = "A", label_b: str = "B") -> dict | None:
    prompt = f"""Compare these two pieces of text for any FACTUAL conflict (a contradicting number, date, name, or claim). Ignore wording or style differences.

Text {label_a}: {output_a}

Text {label_b}: {output_b}

Return ONLY valid JSON, no markdown, no other text.
Format if they conflict: {{"conflict": true, "explanation": "...", "suggested_resolution": "..."}}
Format if they do NOT conflict: {{"conflict": false}}"""
    raw = await run_agent("arbitrator", prompt)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    result = json.loads(raw)
    return result if result.get("conflict") else None
