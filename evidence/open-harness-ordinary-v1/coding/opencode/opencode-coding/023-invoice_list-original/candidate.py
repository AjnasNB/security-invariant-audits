def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    fields = ("owner_id", "company_id")
    if principal is None or any(principal.get(field) is None for field in fields):
        return []
    visible = []
    for invoice in invoices:
        if any(invoice.get(field) is None for field in fields):
            continue
        if any(invoice[field] != principal[field] for field in fields):
            continue
        visible.append(invoice)
    return visible
