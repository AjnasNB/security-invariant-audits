def _matches_field(principal, invoice, field):
    return (
        principal.get(field) is not None
        and invoice.get(field) is not None
        and invoice[field] == principal[field]
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    invoice = next((row for row in invoices if row["id"] == invoice_id), None)
    if invoice is None or principal is None:
        return None
    if all(_matches_field(principal, invoice, field) for field in ("owner_id", "company_id")):
        return invoice
    return None
