from __future__ import annotations

import json


def build_extraction_prompt(prompt_context: str, schema: dict, feedback: str | None) -> str:
    base = (
        "You are extracting structured lab-result data from the attached document.\n"
        f"{prompt_context}\n"
        "Only include laboratory test results (e.g. blood/urine chemistry, hematology, "
        "hormone, lipid, or metabolic panel results). Do NOT include vital signs or "
        "body measurements (e.g. weight, height, BMI, blood pressure, heart rate, "
        "temperature, oxygen saturation) even if you can identify a LOINC code for "
        "them - omit those entirely. Also omit any laboratory item if you are not "
        "confident of its correct LOINC code, rather than guessing or leaving the "
        "code blank.\n"
        "Return ONLY a single JSON object matching this JSON Schema, with no extra "
        "commentary and no markdown fences:\n"
        f"{json.dumps(schema)}"
    )
    if feedback:
        base += f"\n\nYour previous response was invalid. {feedback}"
    return base
