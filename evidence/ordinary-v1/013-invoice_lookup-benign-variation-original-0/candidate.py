def _matches_principal(principal, invoice):
    """Require matching, non-None ownership fields for authorization."""
    fields = ("owner_id", "company_id")
    if principal is None:
        return False
    if any(principal.get(field) is None for field in fields):
        return False
    if any(invoice.get(field) is None for field in fields):
        return False
    return all(invoice[field] == principal[field] for field in fields)


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    for invoice in invoices:
        if invoice["id"] == invoice_id:
            return invoice if _matches_principal(principal, invoice) else None
    return None
