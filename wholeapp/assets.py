"""Retain actual prebuilt asset manifests from the pinned local image."""
import io
import tarfile

from wholeapp.runtime import AREA, checked
from research.io import digest, write_json


def extract():
    data = checked(["exec", "ajnas-erp-security-20261001-backend-1", "tar", "-C",
        "/home/frappe/frappe-bench/assets", "-cf", "-", "assets.json", "assets-rtl.json"]).stdout
    destination = AREA / "assets"
    destination.mkdir(exist_ok=False)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as source:
        for member in source.getmembers():
            if member.name not in ("assets.json", "assets-rtl.json") or not member.isfile():
                raise RuntimeError("Unexpected asset manifest member")
            body = source.extractfile(member).read()
            (destination / member.name).write_bytes(body)
            site_assets = AREA / "sites/assets"
            site_assets.mkdir(exist_ok=True)
            (site_assets / member.name).write_bytes(body)
            files[member.name] = digest(body)
    write_json(AREA / "asset-manifests.json", {"source": "Actual pinned ERP image build manifests",
               "files": files, "ui_bundle_not_rebuilt": True})
    return files


if __name__ == "__main__":
    if (AREA / "assets").exists():
        target = AREA / "sites/assets"
        target.mkdir(exist_ok=False)
        for path in (AREA / "assets").iterdir():
            (target / path.name).write_bytes(path.read_bytes())
        print("Pinned manifests placed at the runtime's site-relative asset path")
    else:
        print(extract())
