_AUTHORIZATION_FIELDS = ("owner_id", "company_id")


def _matches_principal(principal, invoice):
    if any(invoice.get(field) is None for field in _AUTHORIZATION_FIELDS):
        return False
    return not any(
        invoice[field] != principal[field] for field in _AUTHORIZATION_FIELDS
    )


def list_invoices(principal, invoices):
    """Return only authorized invoices, preserving input order."""
    if principal is None or any(
        principal.get(field) is None for field in _AUTHORIZATION_FIELDS
    ):
        return []
    return [invoice for invoice in invoices if _matches_principal(principal, invoice)]
