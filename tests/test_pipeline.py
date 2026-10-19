from analyzer.pipeline import analyze_query


def test_pipeline_returns_all_successful_stage_results():
    result = analyze_query("SELECT id FROM users WHERE age > 18 AND TRUE")
    assert result["overall_status"] == "passed"
    assert result["pipeline_status"]["syntax_analysis"] == "passed"
    assert result["pipeline_status"]["ast_construction"] == "passed"
    assert result["pipeline_status"]["semantic_analysis"] == "passed"
    assert result["optimized_sql"] == "SELECT id FROM users WHERE age > 18;"
    assert result["parse_tree"]["type"] == "SelectStatement"


def test_syntax_failure_blocks_semantics_and_optimization():
    result = analyze_query("SELECT FROM users")
    assert result["overall_status"] == "syntax_error"
    assert result["pipeline_status"]["syntax_analysis"] == "failed"
    assert result["pipeline_status"]["ast_construction"] == "failed"
    assert result["pipeline_status"]["semantic_analysis"] == "blocked"
    assert result["pipeline_status"]["optimization"] == "blocked"
    assert result["optimized_sql"] is None
    assert result["errors"]["syntax"]["line"] == 1


def test_semantic_failure_blocks_optimization():
    result = analyze_query("SELECT nickname FROM users WHERE age > 18 AND TRUE")
    assert result["overall_status"] == "semantic_error"
    assert result["pipeline_status"]["syntax_analysis"] == "passed"
    assert result["pipeline_status"]["semantic_analysis"] == "failed"
    assert result["pipeline_status"]["optimization"] == "blocked"
    assert result["optimized_sql"] is None
    assert result["optimization_explanations"] == []


def test_syntax_error_does_not_hide_independent_token_security_findings():
    result = analyze_query("SELECT FROM users; DROP TABLE users")
    assert result["pipeline_status"]["syntax_analysis"] == "failed"
    assert result["pipeline_status"]["security_analysis"] == "passed"
    assert any("DROP" in finding["finding"]
               for finding in result["security_findings"])


def test_lexical_failure_marks_later_stages_not_run():
    result = analyze_query("SELECT @")
    assert result["overall_status"] == "lexical_error"
    assert result["pipeline_status"]["semantic_analysis"] == "blocked"
    assert result["pipeline_status"]["security_analysis"] == "blocked"
    assert result["pipeline_status"]["optimization"] == "blocked"


def test_flask_api_validation_and_health():
    from app import app

    client = app.test_client()
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/analyze", json={"query": " "}).status_code == 400
    response = client.post("/api/analyze", json={
        "query": "SELECT id FROM users"
    })
    assert response.status_code == 200
    assert response.json["pipeline_status"]["ast_construction"] == "passed"

    invalid_semantics = client.post("/api/analyze", json={
        "query": "SELECT nickname FROM users WHERE age > 18 AND TRUE"
    }).json
    assert invalid_semantics["semantic_analysis"]["valid"] is False
    assert invalid_semantics["pipeline_status"]["optimization"] == "blocked"
    assert invalid_semantics["optimized_sql"] is None


def test_frontend_has_one_report_without_category_tabs():
    from app import app

    page = app.test_client().get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    for section in ("Try an example", "Analyze Query", "SQL syntax validation",
                    "Tokens", "Abstract syntax tree", "Semantic analysis",
                    "Security findings", "Optimization results",
                    "Original SQL versus optimized SQL"):
        assert section in html
    assert 'role="tab"' not in html
    assert "data-tab=" not in html
    assert 'id="example-query"' in html
    for result_id in ("overall-status", "syntax-results", "token-rows",
                      "ast-tree", "semantic-results", "security-results",
                      "optimization-results"):
        assert f'id="{result_id}"' in html
