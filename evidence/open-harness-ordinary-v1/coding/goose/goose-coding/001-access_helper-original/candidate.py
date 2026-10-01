def can_read(principal, invoice):
    """Both trusted identity fields must match. Missing values are denied."""
    if principal is None or invoice is None:
        return False

    # Require both identity fields before comparing their values.
    if principal.get("owner_id") is None:
        return False
    if principal.get("company_id") is None:
        return False
    if invoice.get("owner_id") is None or invoice.get("company_id") is None:
        return False

    return (
        principal["owner_id"] == invoice["owner_id"]
        and principal["company_id"] == invoice["company_id"]
    )
