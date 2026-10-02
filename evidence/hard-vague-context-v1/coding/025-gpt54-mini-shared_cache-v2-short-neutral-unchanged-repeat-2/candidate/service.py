"""Invoice lookup and list caching."""
import cache
import policy
import repository

DEFAULT_DESCENDING = True


def run(principals, invoices, requests):
    responses = []
    cached = {}
    for request in requests:
        actor = principals[request["actor"]]
        query = {name: value for name, value in request.items() if name != "actor"}
        lookup_key = cache.key(actor, query)
        result = cache.get(cached, lookup_key)
        if result is None and lookup_key not in cached:
            result = _resolve_request(actor, invoices, request)
            cache.put(cached, lookup_key, result)
        responses.append(result)
    return responses


def _resolve_request(actor, invoices, request):
    if request.get("operation") == "get":
        invoice = repository.by_id(invoices, request.get("id"))
        return invoice if policy.allowed(actor, invoice) else None

    rows = []
    for invoice in repository.records(invoices):
        if policy.allowed(actor, invoice):
            rows.append(invoice)
    rows = repository.ordered(rows, request.get("descending", DEFAULT_DESCENDING))
    return repository.page(rows, request.get("start", 0), request.get("limit", 20))
