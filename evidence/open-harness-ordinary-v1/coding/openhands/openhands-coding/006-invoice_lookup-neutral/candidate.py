def _is_authorized(principal, invoice):
    if principal is None or invoice is None:
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
    return invoice if _is_authorized(principal, invoice) else None
