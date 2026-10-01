def _matches_principal(principal, invoice):
    """Require matching, non-null owner and company IDs."""
    if principal is None:
        return False
    for key in ("owner_id", "company_id"):
        if principal.get(key) is None or invoice.get(key) is None:
            return False
        if invoice[key] != principal[key]:
            return False
    return True


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    for invoice in invoices:
        if invoice["id"] == invoice_id:
            return invoice if _matches_principal(principal, invoice) else None
    return None
