

def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    if principal is None:
        return []
    ownership_fields = ("owner_id", "company_id")
    if any(principal.get(field) is None for field in ownership_fields):
        return []
    return [
        invoice
        for invoice in invoices
        if all(invoice.get(field) is not None for field in ownership_fields)
        and not any(
            invoice[field] != principal[field] for field in ownership_fields
        )
    ]

