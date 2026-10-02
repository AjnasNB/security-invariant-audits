"""One registered transport/schema correction; rejected originals are retained."""
from pathlib import Path

from research.io import ROOT, read_json, write_json, digest, utc_now
from wholeapp.runtime import AREA
from wholeapp.bridge import inventory


def main():
    original = AREA / "agent-runs"
    results = read_json(original / "results.json")
    usage = read_json(original / "usage.json")
    if len(results["results"]) != 3 or usage["reference_estimate_usd"] != 0 or usage["pending_requests"]:
        raise RuntimeError("Only the three no-inference schema-rejected attempts qualify for this correction")
    if any(row["changed_files"] for row in results["results"]):
        raise RuntimeError("Do not replace a generated output with a correction retry")
    target = AREA / "agent-runs-schema-fixed"
    target.mkdir(exist_ok=False)
    spec = read_json(original / "protocol.json")
    spec["version"] = "wholeapp-schema-fixed-v1"
    spec["registered_at"] = utc_now()
    spec["correction"] = {
        "original_stage": "wholeapp-v1", "original_http_attempts": 3,
        "original_reference_cost_usd": 0,
        "issue": "Responses tool schema defaulted to strict, but inspect_file had optional paging fields",
        "fix": "Set strict=false only for inspect_file; keep exact request, source, cases, limits and model schedule",
        "scope": "Transport repair, not replacement of safe/failed model generations or new attack selection",
        "combined_reference_ceiling_usd": 5,
        "original_results_sha256": digest((original / "results.json").read_bytes()),
    }
    for item in spec["schedule"]:
        source = Path(item["workspace"])
        checked = inventory(source, read_json(AREA / "source-inventory.json"))
        if checked["changed_count"] or checked["missing_files"]:
            raise RuntimeError("Retry source no longer matches the original")
        directory = target / item["run_id"]
        directory.mkdir()
        write_json(directory / "input-inventory.json", read_json(AREA / "source-inventory.json"))
    write_json(target / "protocol.json", spec)
    write_json(ROOT / "protocols/wholeapp-schema-fixed-v1.json", spec)
    print("Registered one schema-corrected three-model run; original three 400 responses retained at $0 reported inference")


if __name__ == "__main__":
    main()
