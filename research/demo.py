"""Offline byte verification and observation replay. No code execution or Azure."""
import argparse
import ast
from pathlib import Path

from research.cases import fixture_cases
from research.io import ROOT, digest, read_json
from research.scoring import score_fixture

SCORE_FIELDS = ("status", "total", "passed", "functional_failures", "security_failures",
                "invalid_outputs", "unknown_security_checks", "invariant_preserved")


def verify(evidence):
    evidence = Path(evidence)
    manifest = read_json(evidence / "manifest.json")
    for filename, expected in manifest["files"].items():
        target = (evidence / filename).resolve()
        if not target.is_relative_to(evidence.resolve()):
            raise RuntimeError("Manifest target is outside the evidence directory")
        if not target.is_file() or digest(target.read_bytes()) != expected:
            raise RuntimeError("Evidence hash mismatch: " + filename)
        if target.suffix == ".py":
            ast.parse(target.read_text(encoding="utf-8"))
    summary = read_json(evidence / "summary.json")
    checked = passed = completed = leaks = unknown = 0
    requests = input_tokens = output_tokens = cached_tokens = cache_write_tokens = 0
    for item in summary["runs"]:
        directory = evidence / item["run_id"]
        run = read_json(directory / "run.json")
        observations = read_json(directory / "observations.json")
        replay = score_fixture(run["task"], fixture_cases(run["task"]), observations)
        if any(replay[key] != run["assessment"][key] for key in SCORE_FIELDS):
            raise RuntimeError("Replayed assessment does not match the recorded verdict")
        if digest((directory / "candidate.py").read_bytes()) != run["candidate_sha256"]:
            raise RuntimeError("Candidate hash mismatch")
        if digest((directory / "input.py").read_bytes()) != run["source_sha256"]:
            raise RuntimeError("Input hash mismatch")
        checked += replay["total"]
        passed += replay["passed"] or 0
        completed += run["task_completed"]
        leaks += replay["security_failures"] or 0
        unknown += replay["invariant_preserved"] is None
        for metadata in read_json(directory / "provenance.json")["provider_metadata"]:
            usage = metadata.get("usage")
            requests += 1
            if usage:
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)
                details = usage.get("input_tokens_details", {})
                cached_tokens += details.get("cached_tokens", 0)
                cache_write_tokens += details.get("cache_write_tokens", 0)
    total = summary["total"]
    if (checked, passed, completed, leaks, unknown) != (
        total["checks_all_saved_files"], total["passed_all_saved_files"], total["task_completed"],
        total["security_failing_checks"], total["unknown_files"],
    ):
        raise RuntimeError("Evidence totals do not reconcile")
    usage = read_json(evidence / "usage.json")
    if (requests, input_tokens, output_tokens, cached_tokens, cache_write_tokens) != (
        usage["http_attempts"], usage["input_tokens"], usage["output_tokens"],
        usage["cached_tokens"], usage["cache_write_tokens"],
    ):
        raise RuntimeError("Provider metadata usage does not reconcile")
    print(f"Verified {len(manifest['files'])} evidence files; {len(summary['runs'])} recorded trajectories.")
    print(f"Replayed {passed}/{checked} checks; {completed} completed refactors; "
          f"{leaks} access violations; {unknown} unknown files.")
    print("No Azure calls, candidate code execution, Docker or credentials used. "
          "This replays saved observations; a fresh model experiment is a separate paid command.")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=ROOT / "evidence/ordinary-v1")
    args = parser.parse_args()
    verify(args.evidence)


if __name__ == "__main__":
    main()
