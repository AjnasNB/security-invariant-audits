"""Run actual django-multitenant manager/viewset using SQLite research fixtures.

This is a library integration smoke test, not its PostgreSQL/Citus test suite.
"""
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, "/task")
from django.conf import settings

settings.configure(
    SECRET_KEY="synthetic-research-only",
    INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes", "rest_framework"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    USE_TZ=True, DEFAULT_AUTO_FIELD="django.db.models.AutoField",
    TENANT_USE_ASGIREF=False, CITUS_EXTENSION_INSTALLED=False, USE_CITUS=False,
)
import django
django.setup()
from django.db import connection, models
from django_multitenant.models import TenantModel
from django_multitenant.utils import set_current_tenant
from django_multitenant import views


class Company(TenantModel):
    tenant_id = "id"
    name = models.CharField(max_length=60)

    class Meta:
        app_label = "research_tenant"


class Invoice(TenantModel):
    tenant_id = "company_id"
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    owner_id = models.IntegerField()
    title = models.CharField(max_length=60)

    class Meta:
        app_label = "research_tenant"


with connection.schema_editor() as editor:
    editor.create_model(Company)
    editor.create_model(Invoice)

set_current_tenant(None)
alpha = Company.objects.create(id=1, name="Alpha")
beta = Company.objects.create(id=2, name="Beta")
Invoice.objects.create(id=11, company=alpha, owner_id=7, title="Alpha owner 7")
Invoice.objects.create(id=12, company=beta, owner_id=7, title="Beta owner 7")
Invoice.objects.create(id=13, company=alpha, owner_id=9, title="Alpha owner 9")
checks = []


def check(label, actual, expected):
    checks.append({"id": label, "actual": actual, "expected": expected, "passed": actual == expected})


set_current_tenant(alpha)
check("tenant-manager-alpha", list(Invoice.objects.values_list("id", flat=True)), [11, 13])
set_current_tenant(beta)
check("tenant-manager-beta-overlapping-owner", list(Invoice.objects.values_list("id", flat=True)), [12])
set_current_tenant(alpha)
check("explicit-owner-and-tenant", list(Invoice.objects.filter(owner_id=7).values_list("id", flat=True)), [11])


class InvoiceView(views.TenantModelViewSet):
    model_class = Invoice


views.get_tenant = lambda request: request.company
view = InvoiceView()
view.request = types.SimpleNamespace(user=types.SimpleNamespace(is_anonymous=False), company=beta)
check("actual-upstream-viewset-beta", list(view.get_queryset().values_list("id", flat=True)), [12])
view.request = types.SimpleNamespace(user=types.SimpleNamespace(is_anonymous=True), company=alpha)
check("actual-upstream-viewset-anonymous", list(view.get_queryset().values_list("id", flat=True)), [])
set_current_tenant(None)
print(json.dumps({
    "kind": "actual-django-multitenant-library-integration",
    "django_version": django.get_version(), "database": "SQLite in-memory",
    "checks": checks, "passed": all(row["passed"] for row in checks),
    "limits": [
        "Not the author's complete PostgreSQL/Citus test suite.",
        "TenantModel/manager/viewset are upstream; Company/Invoice instances are research-created.",
        "Library scopes company, not owner automatically; explicit owner filter supplies the second check.",
        "No coding-agent edit in this integration test.",
    ],
}))
