"""Request-scoped caching for invoice queries."""
import json
from copy import deepcopy


def key(actor, request):
    """Build a cache key from the caller's security context and query."""
    actor = actor or {}
    return (
        actor.get("owner_id"),
        actor.get("company_id"),
        tuple(sorted(actor.get("roles", []))),
        json.dumps(request, sort_keys=True),
    )


class RequestCache:
    """Cache query results for one invocation of the invoice service.

    Values are copied at the cache boundary so one response cannot mutate a
    later response. Membership, rather than the value itself, determines a hit;
    this allows denied lookups (whose result is ``None``) to be cached too.
    """

    def __init__(self):
        self._values = {}

    def resolve(self, actor, request, load):
        cache_key = key(actor, request)
        if cache_key in self._values:
            return deepcopy(self._values[cache_key])

        value = load()
        self._values[cache_key] = deepcopy(value)
        return value


# Compatibility helpers for callers that manage their own cache mapping.
def get(values, cache_key):
    value = values.get(cache_key)
    return deepcopy(value) if value is not None else None


def put(values, cache_key, value):
    values[cache_key] = deepcopy(value)
    return value
