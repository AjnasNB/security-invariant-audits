def _is_authorized(principal, invoice):
    if invoice is None or principal is None:
        return False
    return all(
        principal.get(field) is not None
        and invoice.get(field) is not None
        and invoice[field] == principal[field]
        for field in ("owner_id", "company_id")
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    invoice = next((row for row in invoices if row["id"] == invoice_id), None)
    return invoice if _is_authorized(principal, invoice) else None
