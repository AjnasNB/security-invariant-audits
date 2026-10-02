"""Batch document lookup."""
import policy
import repository

DEFAULT_DESCENDING = False


def run(principals, invoices, requests):
    responses = []
    for request in requests:
        actor = principals[request["actor"]]
        records = []
        missing = []
        for invoice_id in request.get("ids", []):
            invoice = repository.by_id(invoices, invoice_id)
            if invoice is None:
                missing.append(invoice_id)
                continue
            if not policy.allowed(actor, invoice):
                missing.append(invoice_id)
                continue
            records.append(invoice)
        responses.append({"records": records, "missing": missing})
    return responses
