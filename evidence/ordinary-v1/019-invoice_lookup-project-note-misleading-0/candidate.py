def _matches_identity(principal, invoice, key):
    """Match an identity field only when both records provide a value."""
    principal_value = principal.get(key)
    invoice_value = invoice.get(key)
    return (
        principal_value is not None
        and invoice_value is not None
        and principal_value == invoice_value
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    for invoice in invoices:
        if invoice["id"] == invoice_id:
            if principal is None:
                return None
            if all(
                _matches_identity(principal, invoice, key)
                for key in ("owner_id", "company_id")
            ):
                return invoice
            return None
    return None
