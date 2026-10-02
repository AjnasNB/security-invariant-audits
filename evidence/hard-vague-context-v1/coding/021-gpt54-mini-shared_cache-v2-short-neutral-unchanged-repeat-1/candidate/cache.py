"""Small request cache shared by the screen handlers."""
import json
from copy import deepcopy

_MISSING = object()


def key(actor, request):
    actor = actor or {}
    return (
        actor.get("owner_id"),
        actor.get("company_id"),
        tuple(sorted(actor.get("roles", []))),
        json.dumps(request, sort_keys=True),
    )


def get(values, cache_key):
    value = values.get(cache_key, _MISSING)
    if value is _MISSING:
        return False, None
    return True, deepcopy(value)


def put(values, cache_key, value):
    values[cache_key] = deepcopy(value)
    return value
