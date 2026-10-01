def _matches_scope(principal, invoice):
    """Require matching, non-null owner and company IDs."""
    fields = ("owner_id", "company_id")
    return (
        all(principal.get(field) is not None for field in fields)
        and all(invoice.get(field) is not None for field in fields)
        and all(invoice[field] == principal[field] for field in fields)
    )


def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    for invoice in invoices:
        if invoice["id"] == invoice_id:
            return (
                invoice
                if principal is not None and _matches_scope(principal, invoice)
                else None
            )
    return None
