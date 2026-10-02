"""A separate, fixed low-cost current-model replay of three archived examples."""
import random

from hardstudy.models import MODELS
from research.io import ROOT, digest, read_json


def questions():
    records = {}
    for path in sorted((ROOT / "evidence/open-harness-ordinary-v1/predictions").rglob("question.json")):
        row = read_json(path)
        if row["status"] != "assessed":
            continue
        value = {key: row[key] for key in ("id", "task", "condition", "prompt", "expected", "program_sha256")}
        if row["id"] in records and records[row["id"]] != value:
            raise RuntimeError("Previously published paper questions disagree")
        records[row["id"]] = value
    if len(records) != 6:
        raise RuntimeError("Expected six original/mutant questions from three archived examples")
    return [records[key] for key in sorted(records)]


def protocol():
    selected = questions()
    schedule = [{"model_id": model["id"], "question_id": row["id"]}
                for model in MODELS for row in selected]
    random.Random(20261003).shuffle(schedule)
    previous = read_json(ROOT / "artifacts/private/hard-vague-context-v1/usage.json")
    if previous["pending_requests"]:
        raise RuntimeError("The coding stage must settle before registering this separate stage")
    return {
        "version": "hard-paper-models-v1", "registered_date": "2026-10-02", "author": "Ajnas N B",
        "models": MODELS, "questions": selected, "schedule_seed": 20261003, "schedule": schedule,
        "prior_coding_stage_settled_reference_usd": previous["reference_estimate_usd"],
        "prior_coding_usage_sha256": digest((ROOT / "artifacts/private/hard-vague-context-v1/usage.json").read_bytes()),
        "limits": {"max_model_requests": 40, "max_output_tokens_per_request": 512,
                   "max_request_input_estimate": 10000, "reference_cap_per_model_usd": .075,
                   "total_reference_cap_usd": .375, "wall_seconds_per_question": 75},
        "failure_definition": "Correct original answer and incorrect semantics-preserving mutant answer",
        "request": "Use the exact already-published ordinary question, with no expected answer in model input",
        "scope": "Known-positive archived paper examples, not an unbiased discovery sample or full-paper accuracy replication",
        "separate_stage": "The coding stage's 136-attempt limit is not raised or resumed. Thirty fixed prediction "
                          "questions are registered before these new answers; no wrong-answer mining or replacement.",
        "combined_budget_note": "Settled coding usage/reservations plus the connection stage and this stage remain "
                                "inside the previously disclosed $15 reference ceiling.",
    }
