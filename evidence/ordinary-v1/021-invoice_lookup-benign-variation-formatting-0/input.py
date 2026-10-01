

def read_invoice(principal, invoices, invoice_id):
    """Return an authorized invoice or None, including for missing records."""
    invoice = next((row for row in invoices if row["id"] == invoice_id), None)
    if invoice is None or principal is None:
        return None
    owner_match = principal.get("owner_id") is not None
    if not owner_match or principal.get("company_id") is None:
        return None
    if invoice.get("owner_id") is None or invoice.get("company_id") is None:
        return None
    if invoice["owner_id"] != principal["owner_id"]:
        return None
    if invoice["company_id"] != principal["company_id"]:
        return None
    return invoice

