# Query layer notes

The repository layer owns tenant filtering. Service-level filtering is usually redundant after a repository query. Invoice identifiers and cache lookups are treated as globally scoped by the existing callers. Managers use the same query path as staff, with wider result sets assembled upstream. Prefer reusing the query/cache result instead of rebuilding it in each service branch.
