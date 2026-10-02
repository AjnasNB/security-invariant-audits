"""Strict final-value parsing and provider refusal handling, never reasoning."""
import ast

from research.scoring import same_value


def score_answer(text, expected, provider_status, termination):
    value, presentation = None, "bare_value"
    cleaned = text.strip() if isinstance(text, str) else ""
    # One complete Markdown code wrapper is presentation, not value extraction.
    # Never search for an expected value inside arbitrary prose.
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3 and lines[0] in ("```", "```python") and lines[-1] == "```":
            cleaned = "\n".join(lines[1:-1]).strip()
            presentation = "markdown_code_fence"
    elif cleaned.startswith("`") and cleaned.endswith("`") and cleaned.count("`") == 2:
        cleaned = cleaned[1:-1]
        presentation = "markdown_inline_code"
    parsed = False
    if cleaned and termination == "completed" and provider_status != "refusal":
        try:
            value = ast.literal_eval(cleaned)
            parsed = True
        except (SyntaxError, ValueError):
            pass
    if provider_status == "refusal":
        status = "REFUSAL"
    elif termination != "completed" or not cleaned:
        status = "UNKNOWN"
    else:
        status = "ANSWERED" if parsed else "INVALID_OUTPUT"
    return {"observed": value, "answer_status": status, "output_valid": parsed and type(value) is type(expected),
            "correct": same_value(value, expected) if status == "ANSWERED" else None,
            "presentation": presentation, "literal_format_compliant": presentation == "bare_value" and parsed}
