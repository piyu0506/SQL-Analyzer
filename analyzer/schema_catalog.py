"""Schema catalog for semantic checks.

The runtime prefers the SQLite workspace metadata so user-created tables are
reflected immediately without restarting the application.
"""

from .workspace_db import load_schema_catalog


def get_current_schema():
    return load_schema_catalog()
