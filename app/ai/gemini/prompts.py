from __future__ import annotations

import json


def build_extraction_prompt(prompt_context: str, schema: dict, feedback: str | None) -> str:
    base = (
        "You are extracting structured lab-result data from the attached document.\n"
        f"{prompt_context}\n"
        "Only include an item if you are confident of its correct LOINC code. If you "
        "are not confident a LOINC code correctly and specifically identifies an item "
        "(including vital signs, body measurements, or any other non-laboratory "
        "reading you are unsure how to code), omit that item entirely rather than "
        "guessing or leaving the code blank.\n"
        "Return ONLY a single JSON object matching this JSON Schema, with no extra "
        "commentary and no markdown fences:\n"
        f"{json.dumps(schema)}"
    )
    if feedback:
        base += f"\n\nYour previous response was invalid. {feedback}"
    return base
