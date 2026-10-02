"""Small request cache shared by the screen handlers."""
import json
from copy import deepcopy

_MISSING = object()


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


def get_or_set(values, actor, request, factory):
    """Return a cached request result, computing and storing missing results."""
    cache_key = key(actor, request)
    value = values.get(cache_key, _MISSING)
    if value is not _MISSING:
        return deepcopy(value)
    value = factory()
    values[cache_key] = deepcopy(value)
    return value
