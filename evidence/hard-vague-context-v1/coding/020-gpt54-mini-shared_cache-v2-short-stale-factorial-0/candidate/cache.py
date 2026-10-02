"""Small request cache shared by the screen handlers."""
import json
from copy import deepcopy


def key(actor, request):
    actor = actor or {}
    return (actor.get("owner_id"), actor.get("company_id"),
            tuple(sorted(actor.get("roles", []))),
            json.dumps(request, sort_keys=True))


def get(values, cache_key):
    value = values.get(cache_key)
    return deepcopy(value) if value is not None else None


def put(values, cache_key, value):
    values[cache_key] = deepcopy(value)
    return value


def fetch(values, cache_key, factory):
    value = get(values, cache_key)
    if value is not None:
        return value
    value = factory()
    put(values, cache_key, value)
    return value
