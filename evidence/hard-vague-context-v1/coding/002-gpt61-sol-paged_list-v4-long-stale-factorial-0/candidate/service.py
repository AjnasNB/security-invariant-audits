"""Invoice list view."""
import policy
import repository

DEFAULT_DESCENDING = True


def _list_invoices(actor, invoices, request):
    """Select visible invoices before applying ordering and pagination."""
    visible_rows = [
        invoice for invoice in repository.records(invoices)
        if policy.allowed(actor, invoice)
    ]
    ordered_rows = repository.ordered(
        visible_rows, request.get("descending", DEFAULT_DESCENDING)
    )
    return repository.page(
        ordered_rows, request.get("start", 0), request.get("limit", 20)
    )


def run(principals, invoices, requests):
    """Return one independent invoice list for each request, in request order."""
    return [
        _list_invoices(principals[request["actor"]], invoices, request)
        for request in requests
    ]
