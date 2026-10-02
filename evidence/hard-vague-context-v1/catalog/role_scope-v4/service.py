"""Invoice detail and role-based views."""
import policy
import repository

DEFAULT_DESCENDING = True


def run(principals, invoices, requests):
    responses = []
    for request in requests:
        actor = principals[request["actor"]]
        if request.get("operation") == "get":
            invoice = repository.by_id(invoices, request.get("id"))
            if invoice is None:
                responses.append(None)
                continue
            if not policy.allowed(actor, invoice):
                responses.append(None)
                continue
            responses.append(invoice)
            continue
        visible = []
        for invoice in repository.records(invoices):
            if policy.allowed(actor, invoice):
                visible.append(invoice)
        visible = repository.ordered(visible, request.get("descending", DEFAULT_DESCENDING))
        responses.append(repository.page(visible, request.get("start", 0), request.get("limit", 20)))
    return responses
