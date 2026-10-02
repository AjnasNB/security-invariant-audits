"""Small request cache shared by the screen handlers."""
import json
from copy import deepcopy


def key(actor, request):
    actor = actor or {}
    return (actor.get("owner_id"), actor.get("company_id"),
            tuple(sorted(actor.get("roles", []))),
            json.dumps(request, sort_keys=True))


def get(values, cache_key):
    if cache_key not in values:
        return None
    return deepcopy(values[cache_key])


def put(values, cache_key, value):
    values[cache_key] = deepcopy(value)
    return value


def query(request):
    return {name: value for name, value in request.items() if name != "actor"}
