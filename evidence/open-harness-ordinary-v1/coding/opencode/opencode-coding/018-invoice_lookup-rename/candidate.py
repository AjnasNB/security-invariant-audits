def _is_authorized(principal, invoice):
    if principal is None:
        return False
    return all(
        principal.get(key) is not None
        and invoice.get(key) is not None
        and invoice[key] == principal[key]
        for key in ("owner_id", "company_id")
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    for invoice in invoices:
        if invoice["id"] == invoice_id:
            return invoice if _is_authorized(principal, invoice) else None
    return None
