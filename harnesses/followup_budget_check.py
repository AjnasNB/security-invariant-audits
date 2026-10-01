"""Freeze observed-plus-uncertain cost before the remaining follow-up calls."""
from pathlib import Path

from research.io import ROOT, read_json, write_json, utc_now


def main():
    root = ROOT / "artifacts/private/open-harness-ordinary-v1"
    recorded = sum(read_json(path)["reference_estimate_usd"] for path in root.glob("*/usage.json"))
    missing = []
    for path in root.glob("*/*/provider-*-request.json"):
        metadata = path.with_name(path.name.replace("-request.json", "-metadata.json"))
        if metadata.exists():
            continue
        body = read_json(path)
        import json
        input_estimate = (len(json.dumps(body).encode()) + 1) // 2
        reserve = (input_estimate * 2.5 + body.get("max_output_tokens", 1536) * 10) / 1e6
        missing.append({"request": path.relative_to(root).as_posix(),
                        "usage_unknown": True, "reference_reservation_usd": reserve})
    extra = read_json(ROOT / "protocols/open-harness-post-transport-v1.json")["additional_reference_allocation_usd"]
    total = recorded + sum(row["reference_reservation_usd"] for row in missing) + extra
    record = {"recorded_at": utc_now(), "prior_recorded_estimate_usd": recorded,
              "unreported_request_reservations": missing, "followup_allocation_usd": extra,
              "combined_reserved_maximum_usd": total, "total_cap_usd": 1.5,
              "passed": total <= 1.5, "scope": "Planning/reference reservations, not Azure invoice"}
    write_json(root / "followup-budget-registration.json", record)
    print(record)
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
