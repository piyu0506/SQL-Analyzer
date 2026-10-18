from analyzer.pipeline import analyze_query


def test_pipeline_returns_all_successful_stage_results():
    result = analyze_query("SELECT id FROM users WHERE age > 18 AND TRUE")
    assert result["pipeline_status"]["syntax_analysis"] == "passed"
    assert result["pipeline_status"]["semantic_analysis"] == "passed"
    assert result["optimized_sql"] == "SELECT id FROM users WHERE age > 18;"
    assert result["parse_tree"]["type"] == "SelectStatement"


def test_syntax_failure_blocks_semantics_and_optimization():
    result = analyze_query("SELECT FROM users")
    assert result["pipeline_status"]["syntax_analysis"] == "failed"
    assert result["pipeline_status"]["semantic_analysis"] == "blocked"
    assert result["pipeline_status"]["optimization"] == "blocked"
    assert result["optimized_sql"] is None
    assert result["errors"]["syntax"]["line"] == 1


def test_syntax_error_does_not_hide_token_security_analysis():
    result = analyze_query("DELETE FROM users")
    assert result["pipeline_status"]["syntax_analysis"] == "failed"
    assert any("DELETE without" in finding["finding"]
               for finding in result["security_findings"])


def test_flask_api_validation_and_health():
    from app import app

    client = app.test_client()
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/analyze", json={"query": " "}).status_code == 400
    assert client.post("/api/analyze", json={
        "query": "SELECT id FROM users"
    }).status_code == 200
