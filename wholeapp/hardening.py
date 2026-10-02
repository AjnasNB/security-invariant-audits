"""Explicit desired-policy hardening, separate from all model-generated outputs."""
from research.io import read_json, write_json, digest, utc_now
from wholeapp.runtime import AREA, WORKSPACES
from wholeapp.http_run import run


def main():
    path = WORKSPACES / "baseline/frappe/frappe/www/printview.py"
    original = path.read_text(encoding="utf-8")
    old = "\tif frappe.has_website_permission(doc):\n\t\treturn\n"
    new = (
        '\t# Internal staff must not use portal/customer access to bypass their\n'
        '\t# configured company boundary. Website users retain portal access.\n'
        '\tif (\n'
        '\t\tfrappe.get_cached_value("User", frappe.session.user, "user_type") == "Website User"\n'
        '\t\tand frappe.has_website_permission(doc)\n'
        '\t):\n'
        '\t\treturn\n'
    )
    if original.count(old) != 1:
        raise RuntimeError("Pinned print permission block is not unique")
    directory = AREA / "policy-hardening"
    directory.mkdir(exist_ok=False)
    candidate = directory / "printview.py"
    candidate.write_text(original.replace(old, new), encoding="utf-8", newline="\n")
    record = {
        "registered_at": utc_now(), "not_an_ai_generated_patch": True,
        "not_a_stock_upstream_security_claim": True,
        "goal": "Enforce the study's Company boundary for internal System Users at the print/website fallback",
        "native_exceptions_retained": "Normal read/print authorization, Website User portal fallback and explicit valid share keys",
        "original_sha256": digest(path.read_bytes()), "patch_sha256": digest(candidate.read_bytes()),
        "application_mutation_scope": "Disposable overlay only; no original ERP/source checkout is modified",
        "existing_baseline_print_failures": 9,
        "protocol": "730 frozen real-HTTP requests; no replacing original or generated model results",
    }
    write_json(directory / "protocol.json", record)
    result = run(WORKSPACES / "baseline", directory / "http",
                 overlays={"frappe/frappe/www/printview.py": candidate})
    write_json(directory / "result.json", {**record, "assessment": result})
    print({key: result[key] for key in ("total", "passed", "functional_failures", "security_failures", "unknown_access_checks")})


if __name__ == "__main__":
    main()
