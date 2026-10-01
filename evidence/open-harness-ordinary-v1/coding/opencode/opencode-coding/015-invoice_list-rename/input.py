def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    if principal is None:
        return []
    identity_present = principal.get("owner_id") is not None
    if not identity_present or principal.get("company_id") is None:
        return []
    visible = []
    for invoice in invoices:
        if invoice.get("owner_id") is None or invoice.get("company_id") is None:
            continue
        if invoice["owner_id"] != principal["owner_id"]:
            continue
        if invoice["company_id"] != principal["company_id"]:
            continue
        visible.append(invoice)
    return visible
