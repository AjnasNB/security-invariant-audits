def _has_identity(record):
    """Check that both authorization identifiers are present."""
    return all(record.get(key) is not None for key in ("owner_id", "company_id"))


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    invoice = next((row for row in invoices if row["id"] == invoice_id), None)
    if invoice is None or principal is None:
        return None
    if not _has_identity(principal) or not _has_identity(invoice):
        return None
    if all(invoice[key] == principal[key] for key in ("owner_id", "company_id")):
        return invoice
    return None
