"""Invoice lookup and list caching."""
import cache
import policy
import repository

DEFAULT_DESCENDING = True


def _invoice_list(actor, invoices):
    rows = []
    for invoice in repository.records(invoices):
        if policy.allowed(actor, invoice):
            rows.append(invoice)
    return rows


def _resolve(actor, invoices, request):
    if request.get("operation") == "get":
        invoice = repository.by_id(invoices, request.get("id"))
        return invoice if policy.allowed(actor, invoice) else None

    rows = repository.ordered(
        _invoice_list(actor, invoices),
        request.get("descending", DEFAULT_DESCENDING),
    )
    return repository.page(rows, request.get("start", 0), request.get("limit", 20))


def run(principals, invoices, requests):
    responses = []
    cached = {}
    for request in requests:
        actor = principals[request["actor"]]
        lookup_key = cache.key(actor, cache.query(request))
        result = cache.get(cached, lookup_key)
        if result is None:
            result = _resolve(actor, invoices, request)
            cache.put(cached, lookup_key, result)
        responses.append(result)
    return responses
