def _matches_field(principal, invoice, field):
    return (
        principal.get(field) is not None
        and invoice.get(field) is not None
        and invoice[field] == principal[field]
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    for invoice in invoices:
        if invoice["id"] == invoice_id:
            if principal is not None and all(
                _matches_field(principal, invoice, field)
                for field in ("owner_id", "company_id")
            ):
                return invoice
            return None
    return None
