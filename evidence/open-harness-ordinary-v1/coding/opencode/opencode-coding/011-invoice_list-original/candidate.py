def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    match_keys = ("owner_id", "company_id")
    if principal is None or any(principal.get(key) is None for key in match_keys):
        return []
    return [
        invoice
        for invoice in invoices
        if all(invoice.get(key) is not None for key in match_keys)
        and all(invoice[key] == principal[key] for key in match_keys)
    ]
