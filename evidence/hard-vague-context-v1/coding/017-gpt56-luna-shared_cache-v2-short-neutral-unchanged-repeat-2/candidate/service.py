"""Invoice lookup and list caching."""
import cache
import policy
import repository

DEFAULT_DESCENDING = True


def _query(request):
    return {name: value for name, value in request.items() if name != "actor"}


def _lookup(actor, invoices, request):
    if request.get("operation") == "get":
        invoice = repository.by_id(invoices, request.get("id"))
        return invoice if policy.allowed(actor, invoice) else None

    rows = [invoice for invoice in repository.records(invoices)
            if policy.allowed(actor, invoice)]
    rows = repository.ordered(rows, request.get("descending", DEFAULT_DESCENDING))
    return repository.page(rows, request.get("start", 0), request.get("limit", 20))


def run(principals, invoices, requests):
    cached = {}
    responses = []
    for request in requests:
        actor = principals[request["actor"]]
        responses.append(cache.get_or_set(
            cached, actor, _query(request),
            lambda: _lookup(actor, invoices, request)))
    return responses
