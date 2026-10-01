def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    if principal is None:
        return []
    identity_present = principal.get("owner_id") is not None
    if not identity_present or principal.get("company_id") is None:
        return []
    return [
        invoice
        for invoice in invoices
        if invoice.get("owner_id") is not None
        and invoice.get("company_id") is not None
        and invoice["owner_id"] == principal["owner_id"]
        and invoice["company_id"] == principal["company_id"]
    ]
