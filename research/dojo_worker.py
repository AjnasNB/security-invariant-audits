"""Execute original AgentDojo banking tool code against its author environment.

Dependency markers are mapped to direct calls, no external model/network required.
This is an author-code smoke, not a complete benchmark or attack-success measure.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path
import yaml

sys.path.insert(0, "/task/src")
runtime = types.ModuleType("agentdojo.functions_runtime")
runtime.Depends = lambda field: field
sys.modules["agentdojo.functions_runtime"] = runtime

source_path = "/task/src/agentdojo/default_suites/v1/tools/banking_client.py"
spec = importlib.util.spec_from_file_location("original_banking", source_path)
banking = importlib.util.module_from_spec(spec)
spec.loader.exec_module(banking)
data = yaml.safe_load(Path("/task/src/agentdojo/data/suites/banking/environment.yaml").read_text())
account = banking.BankAccount.model_validate(data["bank_account"])
checks = []


def check(label, observed, expected):
    checks.append({"id": label, "observed": observed, "expected": expected, "passed": observed == expected})


check("author-environment-iban", banking.get_iban(account), data["bank_account"]["iban"])
before = len(account.transactions)
banking.send_money(account, "UK12345678901234567890", 98.70, "synthetic author bill smoke", "2022-01-01")
check("original-send-money-appends", len(account.transactions), before + 1)
check("original-send-money-recipient", account.transactions[-1].recipient, "UK12345678901234567890")
check("original-next-id", banking.next_id(account), max(transaction.id for transaction in account.transactions + account.scheduled_transactions) + 1)
print(json.dumps({
    "kind": "actual-AgentDojo-tool-and-environment-smoke", "checks": checks,
    "passed": all(row["passed"] for row in checks),
    "source_path": "src/agentdojo/default_suites/v1/tools/banking_client.py",
    "limits": [
        "Original tool module and original author data, direct dependency injection.",
        "No banking network/service is contacted; only the synthetic in-memory account changes.",
        "Not AgentDojo end-to-end LLM or prompt-injection accuracy reproduction.",
    ],
}))
