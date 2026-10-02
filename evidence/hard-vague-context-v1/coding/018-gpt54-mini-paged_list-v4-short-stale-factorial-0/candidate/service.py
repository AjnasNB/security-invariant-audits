"""Invoice list view."""
import policy
import repository

DEFAULT_DESCENDING = True
DEFAULT_START = 0
DEFAULT_LIMIT = 20


def run(principals, invoices, requests):
    return [list_view(principals, invoices, request) for request in requests]


def list_view(principals, invoices, request):
    actor = principals[request["actor"]]
    visible_rows = visible_invoices(actor, invoices)
    sorted_rows = repository.ordered(
        visible_rows, request.get("descending", DEFAULT_DESCENDING)
    )
    return repository.page(
        sorted_rows,
        request.get("start", DEFAULT_START),
        request.get("limit", DEFAULT_LIMIT),
    )


def visible_invoices(actor, invoices):
    return [invoice for invoice in repository.records(invoices)
            if policy.allowed(actor, invoice)]
