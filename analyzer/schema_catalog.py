"""The in-memory schema used for semantic checks; no database is contacted."""


SCHEMA = {
    "users": {
        "id": "INTEGER",
        "username": "VARCHAR",
        "email": "VARCHAR",
        "age": "INTEGER",
        "role": "VARCHAR",
    },
    "orders": {
        "id": "INTEGER",
        "user_id": "INTEGER",
        "total": "DECIMAL",
        "status": "VARCHAR",
    },
}
