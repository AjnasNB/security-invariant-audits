def _matches_field(principal, invoice, field):
    """Check that both records have the field and its values match."""
    return (
        principal.get(field) is not None
        and invoice.get(field) is not None
        and principal[field] == invoice[field]
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    for invoice in invoices:
        if invoice["id"] == invoice_id:
            if principal is None:
                return None
            if all(
                _matches_field(principal, invoice, field)
                for field in ("owner_id", "company_id")
            ):
                return invoice
            return None
    return None
