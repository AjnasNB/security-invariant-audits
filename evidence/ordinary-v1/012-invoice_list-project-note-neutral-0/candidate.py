def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    if principal is None:
        return []
    authorization_fields = ("owner_id", "company_id")
    if any(principal.get(field) is None for field in authorization_fields):
        return []
    return [
        invoice
        for invoice in invoices
        if not any(invoice.get(field) is None for field in authorization_fields)
        and all(
            invoice[field] == principal[field] for field in authorization_fields
        )
    ]
