"""Application service for the invoice list view."""

import policy
import repository

DEFAULT_DESCENDING = True
DEFAULT_PAGE_SIZE = 20


def _visible_invoices(actor, invoices):
    """Return repository rows the actor is permitted to see."""
    return [invoice for invoice in repository.records(invoices) if policy.allowed(actor, invoice)]


def _list_invoices(actor, invoices, request):
    """Apply the list request's ordering and pagination options."""
    rows = _visible_invoices(actor, invoices)
    rows = repository.ordered(rows, request.get("descending", DEFAULT_DESCENDING))
    return repository.page(
        rows,
        start=request.get("start", 0),
        limit=request.get("limit", DEFAULT_PAGE_SIZE),
    )


def run(principals, invoices, requests):
    """Execute invoice list requests in input order."""
    return [
        _list_invoices(principals[request["actor"]], invoices, request)
        for request in requests
    ]
