def _has_identity(record):
    """Check that both authorization identifiers are present."""
    return record.get("owner_id") is not None and record.get("company_id") is not None


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    for invoice in invoices:
        if invoice["id"] != invoice_id:
            continue
        if principal is None:
            return None
        if not _has_identity(principal) or not _has_identity(invoice):
            return None
        if invoice["owner_id"] != principal["owner_id"]:
            return None
        if invoice["company_id"] != principal["company_id"]:
            return None
        return invoice
    return None
