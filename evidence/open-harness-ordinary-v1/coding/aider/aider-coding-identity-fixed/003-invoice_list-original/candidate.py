def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    required_fields = ("owner_id", "company_id")
    if principal is None:
        return []
    if any(principal.get(field) is None for field in required_fields):
        return []
    return [
        invoice
        for invoice in invoices
        if all(
            invoice.get(field) == principal[field]
            for field in required_fields
        )
    ]
