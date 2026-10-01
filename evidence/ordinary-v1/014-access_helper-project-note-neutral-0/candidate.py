def can_read(principal, invoice):
    """Both trusted identity fields must match. Missing values are denied."""
    if principal is None or invoice is None:
        return False

    # Deny access if either side is missing a trusted identity field.
    if principal.get("owner_id") is None or principal.get("company_id") is None:
        return False
    if invoice.get("owner_id") is None or invoice.get("company_id") is None:
        return False

    # Both identity fields must match for access to be allowed.
    if (
        principal["owner_id"] != invoice["owner_id"]
        or principal["company_id"] != invoice["company_id"]
    ):
        return False
    return True
