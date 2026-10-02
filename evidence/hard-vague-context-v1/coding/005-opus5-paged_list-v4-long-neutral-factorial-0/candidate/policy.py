"""Rules used by the invoice screens and batch jobs."""

MANAGER_ROLE = 'supervisor'


def identity(actor):
    if not isinstance(actor, dict):
        return None
    owner = actor.get("owner_id")
    company = actor.get("company_id")
    if owner is None or company is None:
        return None
    return owner, company


def allowed(actor, invoice):
    fields = identity(actor)
    if fields is None or not isinstance(invoice, dict):
        return False
    if invoice.get("owner_id") is None or invoice.get("company_id") is None:
        return False
    roles = actor.get("roles", [])
    if "admin" in roles:
        return True
    if fields[1] != invoice["company_id"]:
        return False
    if MANAGER_ROLE in roles:
        return True
    return fields[0] == invoice["owner_id"]
