"""Invoice lookup and list caching."""
import cache
import policy
import repository

DEFAULT_DESCENDING = True


def _execute(actor, invoices, request):
    if request.get("operation") == "get":
        invoice = repository.by_id(invoices, request.get("id"))
        return invoice if policy.allowed(actor, invoice) else None

    rows = [invoice for invoice in repository.records(invoices) if policy.allowed(actor, invoice)]
    rows = repository.ordered(rows, request.get("descending", DEFAULT_DESCENDING))
    return repository.page(rows, request.get("start", 0), request.get("limit", 20))


def run(principals, invoices, requests):
    responses = []
    request_cache = cache.RequestCache()

    for request in requests:
        actor = principals[request["actor"]]
        query = {name: value for name, value in request.items() if name != "actor"}
        result = request_cache.resolve(actor, query, lambda: _execute(actor, invoices, request))
        responses.append(result)

    return responses
