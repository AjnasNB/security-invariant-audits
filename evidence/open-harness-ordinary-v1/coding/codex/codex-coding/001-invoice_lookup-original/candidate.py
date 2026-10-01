def _matches_invoice_scope(principal, invoice):
    """Require matching, non-null owner and company identifiers."""
    if principal is None:
        return False
    fields = ("owner_id", "company_id")
    if any(principal.get(field) is None for field in fields):
        return False
    if any(invoice.get(field) is None for field in fields):
        return False
    return all(invoice[field] == principal[field] for field in fields)


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    invoice = next((row for row in invoices if row["id"] == invoice_id), None)
    if invoice is not None and _matches_invoice_scope(principal, invoice):
        return invoice
    return None
