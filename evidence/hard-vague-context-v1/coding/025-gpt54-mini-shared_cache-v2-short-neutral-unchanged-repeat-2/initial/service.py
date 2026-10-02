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
        if result is not None:
            responses.append(result)
            continue
        if request.get("operation") == "get":
            invoice = repository.by_id(invoices, request.get("id"))
            if policy.allowed(actor, invoice):
                result = invoice
            else:
                result = None
        else:
            rows = []
            for invoice in repository.records(invoices):
                if policy.allowed(actor, invoice):
                    rows.append(invoice)
            rows = repository.ordered(rows, request.get("descending", DEFAULT_DESCENDING))
            result = repository.page(rows, request.get("start", 0), request.get("limit", 20))
        cache.put(cached, lookup_key, result)
        responses.append(result)
    return responses
