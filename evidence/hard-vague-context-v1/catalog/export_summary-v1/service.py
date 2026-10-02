"""Invoice exports and totals."""
import policy
import repository

DEFAULT_DESCENDING = False


def _rows(actor, invoices):
    rows = []
    for invoice in repository.records(invoices):
        if policy.allowed(actor, invoice):
            rows.append(invoice)
    return rows


def run(principals, invoices, requests):
    responses = []
    for request in requests:
        actor = principals[request["actor"]]
        rows = _rows(actor, invoices)
        ordered = repository.ordered(rows, request.get("descending", DEFAULT_DESCENDING))
        selected = repository.page(ordered, request.get("start", 0), request.get("limit", 20))
        responses.append({"records": selected, "count": len(rows),
                          "total": sum(invoice["total"] for invoice in rows)})
    return responses
