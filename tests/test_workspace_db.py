import pytest

from analyzer import workspace_db


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_db, "WORKSPACE_DB_PATH", tmp_path / "playground.sqlite3")
    workspace_db._initialise_workspace()
    workspace_db.reset_workspace()
    return workspace_db


def columns(*items):
    return list(items)


def test_default_workspace_supports_the_provided_example_queries():
    from analyzer.pipeline import analyze_query

    db = workspace_db
    assert db.list_tables() == ["orders", "users"]
    users = db.execute_select_query(
        "SELECT username, age FROM users WHERE age >= 18;"
    )
    assert users["row_count"] == 2
    assert {row["username"] for row in users["rows"]} == {"alice", "casey"}

    orders = db.execute_select_query(
        "SELECT id, user_id, total, status FROM orders WHERE total > 100;"
    )
    assert orders["row_count"] == 1

    analysis = analyze_query(
        "SELECT id FROM users WHERE age > 18 AND TRUE AND age > 18;"
    )
    assert analysis["semantic_analysis"]["valid"] is True
    assert analysis["optimized_sql"] == "SELECT id FROM users WHERE age > 18;"


def test_legacy_empty_workspace_gets_default_tables_and_sample_rows(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.sqlite3"
    monkeypatch.setattr(workspace_db, "WORKSPACE_DB_PATH", database_path)
    with workspace_db._connect() as connection:
        connection.execute(
            "CREATE TABLE __workspace_metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO __workspace_metadata (key, value) VALUES ('initialized', 'true')"
        )

    workspace_db._initialise_workspace()

    assert workspace_db.list_tables() == ["orders", "users"]
    assert workspace_db.get_table_definition("users")["row_count"] == 3


def test_manual_table_records_and_schema_edit_preserve_data(isolated_workspace):
    db = isolated_workspace
    db.create_table("Employees", columns(
        {"name": "employee_id", "type": "INTEGER", "primary_key": True, "not_null": True},
        {"name": "email", "type": "VARCHAR", "not_null": True, "unique": True},
        {"name": "age", "type": "INTEGER", "not_null": True},
    ))

    db.insert_record("Employees", {
        "employee_id": 14,
        "email": "ava@example.test",
        "age": 31,
    })
    with pytest.raises(ValueError, match="unique or primary-key"):
        db.insert_record("Employees", {
            "employee_id": 15,
            "email": "ava@example.test",
            "age": 29,
        })
    with pytest.raises(ValueError, match="constraint would be violated"):
        db.update_table("Employees", columns(
            {"name": "employee_id", "type": "INTEGER", "primary_key": True},
            {"name": "email", "type": "VARCHAR", "not_null": True, "unique": True},
            {"name": "age", "type": "INTEGER", "not_null": True},
            {"name": "required_new_value", "type": "TEXT", "not_null": True},
        ))
    assert db.get_table_rows("Employees")["rows"][0]["email"] == "ava@example.test"

    db.update_table("Employees", columns(
        {"name": "employee_id", "type": "INTEGER", "primary_key": True, "not_null": True},
        {"name": "email", "type": "VARCHAR", "not_null": True, "unique": True},
        {"name": "age", "type": "INTEGER", "not_null": True},
        {"name": "active", "type": "BOOLEAN"},
    ))
    assert db.get_table_rows("Employees")["rows"][0]["email"] == "ava@example.test"


def test_manual_record_update_and_delete_respect_constraints(isolated_workspace):
    db = isolated_workspace
    db.create_table("Tags", columns(
        {"name": "tag_id", "type": "INTEGER", "primary_key": True},
        {"name": "label", "type": "TEXT", "not_null": True, "unique": True},
    ))
    db.insert_record("Tags", {"tag_id": 1, "label": "first"})
    with pytest.raises(ValueError, match="cannot be empty"):
        db.insert_record("Tags", {"tag_id": 2, "label": ""})

    db.update_record("Tags", {"tag_id": 1}, {"label": "updated"})
    assert db.get_table_rows("Tags")["rows"][0]["label"] == "updated"
    db.delete_record("Tags", {"tag_id": 1})
    assert db.get_table_rows("Tags")["rows"] == []


def test_random_schema_samples_obey_relationships_and_coexists_with_manual_data(isolated_workspace):
    db = isolated_workspace
    db.create_table("Students", columns(
        {"name": "student_id", "type": "INTEGER", "primary_key": True},
        {"name": "student_name", "type": "TEXT", "not_null": True},
    ))
    db.insert_record("Students", {"student_id": 7, "student_name": "Manual student"})
    preview = db.preview_random_schema(
        theme="university",
        table_count=3,
        columns_per_table=4,
        relationships=True,
        mode="add",
    )
    assert preview["renamed_conflicts"]["Students"] == "Students_2"

    result = db.create_random_schema(
        preview["tables"],
        mode="add",
        rows_per_table=4,
        generate_samples=True,
    )
    assert len(result["tables"]) == 3
    assert db.get_table_rows("Students")["rows"][0]["student_name"] == "Manual student"
    assert db.get_table_definition("Enrollments")["row_count"] == 4
    assert db.get_table_definition("Enrollments")["columns"][1]["references"] == "Courses.id"
    from analyzer.pipeline import analyze_query

    generated_analysis = analyze_query("SELECT name FROM Students_2 WHERE name = 'Alice'")
    assert generated_analysis["semantic_analysis"]["valid"] is True
    assert len(db.execute_select_query("SELECT name FROM Students_2")["rows"]) == 4
    course_ids = {row["id"] for row in db.get_table_rows("Courses")["rows"]}
    assert all(
        row["students_2_id"] in {row["id"] for row in db.get_table_rows("Students_2")["rows"]}
        for row in db.get_table_rows("Courses")["rows"]
    )
    assert all(
        row["course_id"] in course_ids
        for row in db.get_table_rows("Enrollments")["rows"]
    )
    generated = db.get_table_definition("Students_2")
    db.update_table("Students_2", [
        {"name": "id", "type": "INTEGER", "primary_key": True, "not_null": True},
        {"name": "name", "type": "VARCHAR", "not_null": True},
        {"name": "created_date", "type": "DATE", "not_null": True},
        {"name": "active", "type": "BOOLEAN", "not_null": True},
        {"name": "cohort", "type": "TEXT"},
    ])
    assert db.get_table_definition("Students_2")["row_count"] == generated["row_count"]


def test_random_add_preserves_existing_records_and_duplicate_names_are_safe(isolated_workspace):
    db = isolated_workspace
    db.create_table("Assets", columns(
        {"name": "id", "type": "INTEGER", "primary_key": True},
        {"name": "label", "type": "TEXT"},
    ))
    db.insert_record("Assets", {"id": 4, "label": "keep"})
    proposed = [
        {"name": "Assets", "columns": [
            {"name": "id", "type": "INTEGER", "primary_key": True},
            {"name": "name", "type": "TEXT"},
        ]}
    ]
    with pytest.raises(ValueError, match="conflict"):
        db.create_random_schema(proposed, mode="add")
    assert db.get_table_rows("Assets")["rows"][0]["label"] == "keep"


def test_replace_requires_confirmation_and_rolls_back_failed_generation(isolated_workspace):
    db = isolated_workspace
    db.create_table("KeepMe", columns(
        {"name": "id", "type": "INTEGER", "primary_key": True},
        {"name": "label", "type": "TEXT"},
    ))
    db.insert_record("KeepMe", {"id": 1, "label": "still here"})
    proposed = [
        {"name": "Broken", "columns": [
            {"name": "id", "type": "INTEGER", "primary_key": True},
            {"name": "missing_id", "type": "INTEGER", "not_null": True, "references": "NoParent.id"},
        ]}
    ]
    with pytest.raises(ValueError, match="confirmation"):
        db.create_random_schema(proposed, mode="replace")
    with pytest.raises(ValueError, match="target table"):
        db.create_random_schema(proposed, mode="replace", confirm_replace=True)
    assert db.list_tables() == ["KeepMe"]
    assert db.get_table_rows("KeepMe")["rows"][0]["label"] == "still here"

    impossible_samples = [{
        "name": "Fresh",
        "columns": [
            {"name": "id", "type": "INTEGER", "primary_key": True},
            {"name": "flag", "type": "BOOLEAN", "not_null": True, "unique": True},
        ],
    }]
    with pytest.raises(ValueError, match="more than two unique BOOLEAN"):
        db.create_random_schema(
            impossible_samples,
            mode="replace",
            confirm_replace=True,
            rows_per_table=3,
            generate_samples=True,
        )
    assert db.list_tables() == ["KeepMe"]
    assert db.get_table_rows("KeepMe")["rows"][0]["label"] == "still here"


def test_random_sample_generation_is_atomic_and_unique_across_batches(isolated_workspace):
    db = isolated_workspace
    db.create_table("Parent", columns(
        {"name": "id", "type": "INTEGER", "primary_key": True},
        {"name": "label", "type": "TEXT", "not_null": True, "unique": True},
    ))
    db.create_table("Child", columns(
        {"name": "id", "type": "INTEGER", "primary_key": True},
        {"name": "parent_id", "type": "INTEGER", "not_null": True, "references": "Parent.id"},
    ))
    with pytest.raises(ValueError, match="no records"):
        db.generate_sample_data(["Child"], rows_per_table=2)
    assert db.get_table_definition("Child")["row_count"] == 0

    db.generate_sample_data(["Parent"], rows_per_table=3)
    db.generate_sample_data(["Parent"], rows_per_table=3)
    assert db.get_table_definition("Parent")["row_count"] == 6
    db.generate_sample_data(["Child"], rows_per_table=2)
    assert db.get_table_definition("Child")["row_count"] == 2


def test_reset_removes_related_tables_without_reseeding_on_restart(isolated_workspace):
    db = isolated_workspace
    db.create_table("Parent", columns(
        {"name": "id", "type": "INTEGER", "primary_key": True},
    ))
    db.create_table("Child", columns(
        {"name": "id", "type": "INTEGER", "primary_key": True},
        {"name": "parent_id", "type": "INTEGER", "references": "Parent.id"},
    ))
    db.insert_record("Parent", {"id": 1})
    db.insert_record("Child", {"id": 1, "parent_id": 1})

    db.reset_workspace()
    db._initialise_workspace()
    assert db.list_tables() == []


def test_manual_and_generated_schema_are_available_to_compiler_and_runner(isolated_workspace):
    from analyzer.pipeline import analyze_query

    db = isolated_workspace
    db.create_table("Employees", columns(
        {"name": "employee_id", "type": "INTEGER", "primary_key": True},
        {"name": "name", "type": "TEXT", "not_null": True},
        {"name": "age", "type": "INTEGER", "not_null": True},
    ))
    db.insert_record("Employees", {"employee_id": 1, "name": "Jo", "age": 35})
    analysis = analyze_query("SELECT employee_id, name FROM Employees WHERE age > 18")
    assert analysis["semantic_analysis"]["valid"] is True
    assert analysis["optimized_sql"] == "SELECT employee_id, name FROM Employees WHERE age > 18;"
    assert db.execute_select_query("SELECT employee_id, name FROM Employees WHERE age > 18")["rows"] == [
        {"employee_id": 1, "name": "Jo"}
    ]
    assert db.execute_select_query(
        "SELECT employee_id, name FROM Employees WHERE name = ';'"
    )["columns"] == ["employee_id", "name"]
    assert analyze_query("SELECT salary FROM Employees")["semantic_analysis"]["valid"] is False
    db.create_random_schema(
        db.preview_random_schema(
            theme="company",
            table_count=1,
            columns_per_table=3,
            relationships=False,
            mode="add",
        )["tables"],
        mode="add",
    )
    assert analyze_query("SELECT name FROM Employees")["semantic_analysis"]["valid"] is True


def test_flask_manual_insert_and_random_replace_confirmation(isolated_workspace):
    from app import app

    client = app.test_client()
    created = client.post("/api/workspace/tables", json={
        "name": "Project",
        "columns": [
            {"name": "id", "type": "INTEGER", "primary_key": True},
            {"name": "name", "type": "TEXT", "not_null": True},
        ],
    })
    assert created.status_code == 200
    duplicate = client.post("/api/workspace/tables", json={
        "name": "project",
        "columns": [{"name": "id", "type": "INTEGER", "primary_key": True}],
    })
    assert duplicate.status_code == 400
    inserted = client.post("/api/workspace/tables/Project/records", json={
        "values": {"id": 1, "name": "Keep"},
    })
    assert inserted.status_code == 200
    blocked = client.post("/api/run-query", json={
        "query": "SELECT id FROM Project WHERE id = 1 OR 1 = 1",
    })
    assert blocked.status_code == 400
    assert any(
        item["severity"] == "HIGH"
        for item in blocked.json["analysis"]["security_findings"]
    )
    assert client.delete("/api/workspace/tables/Project").status_code == 400
    assert client.post("/api/workspace/reset").status_code == 400
    assert client.get("/api/workspace/table/Project").status_code == 200

    preview = client.post("/api/workspace/random-schema/preview", json={
        "theme": "library",
        "table_count": 2,
        "columns_per_table": 3,
        "mode": "replace",
    })
    assert preview.status_code == 200
    rejected = client.post("/api/workspace/random-schema/create", json={
        "tables": preview.json["tables"],
        "mode": "replace",
        "generate_samples": False,
    })
    assert rejected.status_code == 400
    assert client.get("/api/workspace/table/Project").status_code == 200
    accepted = client.post("/api/workspace/random-schema/create", json={
        "tables": preview.json["tables"],
        "mode": "replace",
        "confirm_replace": True,
        "generate_samples": True,
        "rows_per_table": 2,
    })
    assert accepted.status_code == 200
    assert "Project" not in [table["name"] for table in client.get("/api/workspace").json["tables"]]
