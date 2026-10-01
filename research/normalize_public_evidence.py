"""Mechanical LF normalization of new publication JSON, not raw experiment data."""
from research.io import ROOT, digest, read_json, write_json


def main():
    for relative in ("evidence/ordinary-v1", "evidence/mucoco-author-replay-v1"):
        directory = ROOT / relative
        manifest = read_json(directory / "manifest.json")
        normalized = 0
        for path in directory.rglob("*.json"):
            if path.name == "manifest.json":
                continue
            body = path.read_bytes()
            next_body = body.replace(b"\r\n", b"\n")
            if next_body != body:
                path.write_bytes(next_body)
                normalized += 1
        manifest["files"] = {path.relative_to(directory).as_posix(): digest(path.read_bytes())
                             for path in sorted(directory.rglob("*"))
                             if path.is_file() and path.name != "manifest.json"}
        manifest["publication_line_endings"] = (
            "New JSON exports normalized to LF for cross-platform byte verification; "
            "raw private inputs, responses, events and generated Python code unchanged")
        write_json(directory / "manifest.json", manifest)
        print(f"{relative}: {normalized} JSON files mechanically normalized; manifest refreshed.")


if __name__ == "__main__":
    main()
