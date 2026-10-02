"""Small request cache shared by the screen handlers."""
import json
from copy import deepcopy


def key(actor, request):
    actor = actor or {}
    return (actor.get("owner_id"), actor.get("company_id"),
            tuple(sorted(actor.get("roles", []))),
            json.dumps(request, sort_keys=True))


def contains(values, cache_key):
    """Return whether a key is cached, including cached ``None`` values."""
    return cache_key in values


def get(values, cache_key):
    """Return a cached value, or ``None`` when the key is absent.

    Callers that need to distinguish a miss from a cached ``None`` should use
    :func:`contains` first.
    """
    return deepcopy(values[cache_key]) if cache_key in values else None


def put(values, cache_key, value):
    values[cache_key] = deepcopy(value)
    return value
