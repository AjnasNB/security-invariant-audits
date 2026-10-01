def _is_authorized(principal, invoice):
    """Require matching, non-null owner and company IDs."""
    if principal is None or invoice is None:
        return False
    return all(
        principal.get(key) is not None
        and invoice.get(key) is not None
        and invoice[key] == principal[key]
        for key in ("owner_id", "company_id")
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    invoice = next((row for row in invoices if row["id"] == invoice_id), None)
    return invoice if _is_authorized(principal, invoice) else None
