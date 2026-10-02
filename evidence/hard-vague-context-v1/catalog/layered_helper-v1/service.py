"""Shared helpers for invoice actions."""
import policy
import repository

DEFAULT_DESCENDING = False


def _decision(actor, invoice):
    if actor is None or invoice is None:
        return False
    if not policy.allowed(actor, invoice):
        return False
    return True


def run(principals, invoices, requests):
    responses = []
    for request in requests:
        actor = principals[request["actor"]]
        invoice = repository.by_id(invoices, request.get("id"))
        responses.append(_decision(actor, invoice))
    return responses
