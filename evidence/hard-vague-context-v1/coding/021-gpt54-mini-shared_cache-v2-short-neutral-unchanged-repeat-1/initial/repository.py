"""In-memory repository used by application callers."""
from copy import deepcopy


def records(invoices):
    return deepcopy(invoices)


def by_id(invoices, invoice_id):
    return next((row for row in records(invoices) if row["id"] == invoice_id), None)


def ordered(rows, descending=False):
    return sorted(rows, key=lambda row: (row["total"], row["id"]), reverse=descending)


def page(rows, start=0, limit=20):
    return rows[max(0, start):max(0, start) + max(0, limit)]
