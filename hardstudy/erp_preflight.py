"""Inspect a current reference failure before model runs; raw diagnostics stay private."""
import json
from unittest.mock import patch

from erp.evaluate import assess, cases, PROTECTED
from research.io import ROOT, write_json, utc_now


def main():
    records = [case for case in cases() if case["id"] == "erp-009"]
    with patch("erp.evaluate.score_erp", side_effect=lambda challenges, observations: observations):
        observations = assess(PROTECTED / "client-baseline.py", records=records)
    write_json(ROOT / "artifacts/private/hard-preflight-v1/update-diagnostic.json",
               {"recorded_at": utc_now(), "observations": observations, "azure_calls": 0})
    for row in observations:
        print(row.get("diagnostic", "")[-1700:])


if __name__ == "__main__":
    main()
