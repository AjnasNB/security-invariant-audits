def _matches_scope(principal, invoice):
    fields = ("owner_id", "company_id")
    if any(principal.get(field) is None for field in fields):
        return False
    if any(invoice.get(field) is None for field in fields):
        return False
    return all(invoice[field] == principal[field] for field in fields)


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    invoice = next((row for row in invoices if row["id"] == invoice_id), None)
    if invoice is None or principal is None:
        return None
    return invoice if _matches_scope(principal, invoice) else None
