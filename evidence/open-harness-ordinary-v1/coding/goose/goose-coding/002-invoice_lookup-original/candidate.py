def _matches_identity(principal, invoice):
    """Require matching, non-null owner and company identifiers."""
    return all(
        principal.get(key) is not None
        and invoice.get(key) is not None
        and invoice[key] == principal[key]
        for key in ("owner_id", "company_id")
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    invoice = next((row for row in invoices if row["id"] == invoice_id), None)
    if invoice is None or principal is None:
        return None
    return invoice if _matches_identity(principal, invoice) else None
