"""Small illustration of the recorded ERP failure, not the 94-case ERP replay.

This deliberately broken example is researcher-written. It demonstrates the
same missing-helper mechanism; the original generated file is retained under
evidence/hard-vague-context-v1.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Invoice:
    name: str
    company: str


def original_get(invoices, name, allowed_company):
    invoice = invoices.get(name)
    if invoice is None:
        raise LookupError("Invoice does not exist")
    if invoice.company != allowed_company:
        raise PermissionError("Invoice belongs to another company")
    return invoice


def refactored_get(invoices, name, allowed_company):
    # Intentionally absent: the generated ERP file made the same kind of call.
    invoice = _get_doc(invoices, name)
    if invoice.company != allowed_company:
        raise PermissionError("Invoice belongs to another company")
    return invoice


def main():
    invoices = {"INV-001": Invoice("INV-001", "Company A")}
    print("Illustration only: no Azure, Docker, or real customer data.")
    invoice = original_get(invoices, "INV-001", "Company A")
    print(f"Original: {invoice.name} loaded.")
    try:
        refactored_get(invoices, "INV-001", "Company A")
    except NameError as error:
        print(f"Refactor: {type(error).__name__}: {error}")
        print("Result: functional failure; access outcome unknown, not a demonstrated leak.")
    else:
        raise AssertionError("The intentionally missing helper unexpectedly resolved")


if __name__ == "__main__":
    main()
