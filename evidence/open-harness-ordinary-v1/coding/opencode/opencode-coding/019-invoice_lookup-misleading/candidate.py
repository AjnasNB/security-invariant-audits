def _matches_scope(principal, invoice):
    return principal is not None and all(
        principal.get(field) is not None
        and invoice.get(field) == principal[field]
        for field in ("owner_id", "company_id")
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    for invoice in invoices:
        if invoice["id"] == invoice_id:
            return invoice if _matches_scope(principal, invoice) else None
    return None
