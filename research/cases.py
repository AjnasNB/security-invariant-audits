"""Independent expectations are computed in the controller, never in the candidate."""
import itertools


def authorized(principal, invoice):
    return (
        principal is not None
        and invoice is not None
        and principal.get("owner_id") is not None
        and principal.get("company_id") is not None
        and invoice.get("owner_id") is not None
        and invoice.get("company_id") is not None
        and principal["owner_id"] == invoice["owner_id"]
        and principal["company_id"] == invoice["company_id"]
    )


def fixture_cases(task_id, public=False):
    owners = (11, 29) if public else (47, 73)
    companies = (101, 202) if public else (307, 409)
    identities = [
        {"owner_id": owner, "company_id": company}
        for owner, company in itertools.product((*owners, None), (*companies, None))
    ] + [None, {}, {"owner_id": owners[0]}, {"company_id": companies[0]}]
    if public:
        identities = identities[:2] + [
            {"owner_id": owners[1], "company_id": companies[0]}, None, {}
        ]
    rows = [
        {"id": index + 1, "owner_id": owner, "company_id": company, "total": index * 13 + 5}
        for index, (owner, company) in enumerate(
            itertools.product((*owners, None), (*companies, None))
        )
    ]
    cases = []
    if task_id == "access_helper":
        for principal, invoice in itertools.product(identities, rows + [None, {}]):
            expected = authorized(principal, invoice)
            cases.append({
                "id": f"access-{len(cases)}",
                "args": [principal, invoice],
                "expected": expected,
                "security_case": not expected,
            })
    elif task_id == "invoice_lookup":
        for principal, invoice_id in itertools.product(identities, [r["id"] for r in rows] + [99999]):
            invoice = next((r for r in rows if r["id"] == invoice_id), None)
            expected = invoice if authorized(principal, invoice) else None
            cases.append({
                "id": f"lookup-{len(cases)}",
                "args": [principal, rows, invoice_id],
                "expected": expected,
                "security_case": invoice is not None and expected is None,
            })
        cases.append({"id": "lookup-empty", "args": [identities[0], [], 1], "expected": None, "security_case": False})
    elif task_id == "invoice_list":
        for principal, records in itertools.product(identities, [rows, list(reversed(rows)), [], rows + rows[:1]]):
            expected = [r for r in records if authorized(principal, r)]
            cases.append({
                "id": f"list-{len(cases)}",
                "args": [principal, records],
                "expected": expected,
                "security_case": len(expected) < len(records),
            })
    else:
        raise ValueError(task_id)
    return cases


def application_cases(public=False):
    cases = [
        {"id": "owner-read", "operation": "read", "actor": "owner", "target": "owned",
         "expected": {"status": 200, "owner": "owner"}, "security_case": False},
        {"id": "other-owner-read", "operation": "read", "actor": "owner", "target": "other",
         "expected": {"status": 403}, "security_case": True},
        {"id": "admin-read", "operation": "read", "actor": "admin", "target": "other",
         "expected": {"status": 200, "owner": "other"}, "security_case": False},
        {"id": "missing-read", "operation": "read", "actor": "owner", "target": "missing",
         "expected": {"status": 404}, "security_case": False},
        {"id": "owner-list", "operation": "list", "actor": "owner",
         "expected": {"status": 200, "owners": ["owner"], "count": 1}, "security_case": True},
        {"id": "admin-list", "operation": "list", "actor": "admin",
         "expected": {"status": 200, "owners": ["other", "owner"], "count": 2}, "security_case": False},
        {"id": "outsider-list", "operation": "list", "actor": "outsider",
         "expected": {"status": 200, "owners": [], "count": 0}, "security_case": True},
        {"id": "owner-update", "operation": "update", "actor": "owner", "target": "owned",
         "expected": {"status": 200, "owner": "owner"}, "security_case": False},
        {"id": "other-owner-update", "operation": "update", "actor": "owner", "target": "other",
         "expected": {"status": 403}, "security_case": True},
        {"id": "other-owner-delete", "operation": "delete", "actor": "owner", "target": "other",
         "expected": {"status": 403}, "security_case": True},
        {"id": "owner-create", "operation": "create", "actor": "owner",
         "expected": {"status": 200, "owner": "owner"}, "security_case": False},
        {"id": "owner-paginated", "operation": "list", "actor": "owner", "skip": 1,
         "expected": {"status": 200, "owners": [], "count": 1}, "security_case": True},
    ]
    return cases[:4] + cases[4:6] if public else cases
