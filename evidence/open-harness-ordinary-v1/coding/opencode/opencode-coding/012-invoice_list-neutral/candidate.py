def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    if principal is None:
        return []
    owner_match = principal.get("owner_id") is not None
    if not owner_match or principal.get("company_id") is None:
        return []
    return [
        invoice
        for invoice in invoices
        if invoice.get("owner_id") is not None
        and invoice.get("company_id") is not None
        and not invoice["owner_id"] != principal["owner_id"]
        and not invoice["company_id"] != principal["company_id"]
    ]
