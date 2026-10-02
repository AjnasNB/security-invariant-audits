"""Invoice list view."""
import policy
import repository

DEFAULT_DESCENDING = False


def run(principals, invoices, requests):
    responses = []
    for request in requests:
        actor = principals[request["actor"]]
        rows = repository.records(invoices)
        selected = []
        for invoice in rows:
            if not policy.allowed(actor, invoice):
                continue
            selected.append(invoice)
        sorted_rows = repository.ordered(
            selected, request.get("descending", DEFAULT_DESCENDING))
        responses.append(repository.page(
            sorted_rows, request.get("start", 0), request.get("limit", 20)))
    return responses
