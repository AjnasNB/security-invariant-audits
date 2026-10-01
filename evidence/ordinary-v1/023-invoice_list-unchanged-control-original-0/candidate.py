def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    if principal is None:
        return []
    match_fields = ("owner_id", "company_id")
    if any(principal.get(field) is None for field in match_fields):
        return []
    return [
        invoice
        for invoice in invoices
        if all(invoice.get(field) == principal[field] for field in match_fields)
    ]
