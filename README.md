# SQL Query Security Analyzer and Optimizer

A beginner-friendly Flask application demonstrating a real compiler pipeline for a deliberately small SQL dialect. SQL input is tokenized, parsed into an abstract syntax tree, checked against a sample schema, inspected for suspicious patterns, simplified on the AST only after successful semantic validation, and generated back into readable SQL.

The project also includes a SQLite-backed playground workspace. A new or previously initialized but empty workspace starts with `users` and `orders` tables and a few sample records, so valid demonstration queries can be executed immediately; intentionally invalid or blocked examples remain useful for analysis. Users can also define tables and enter records manually, or preview and generate a themed random schema with optional related sample records. All modes use the same persistent local database, and the compiler reads the live SQLite schema for semantic checks.

## Requirements and setup (Windows PowerShell)

Use Python 3.10 or newer. From this project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python app.py
```

If PowerShell blocks virtual-environment activation, run this in the current terminal and then activate:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

Open **http://127.0.0.1:5000**. Health check: **http://127.0.0.1:5000/api/health**.

The playground database is stored in `playground.sqlite3` in the project root and is ignored by Git. Use **Create Manually** to create or edit tables and manage records. Use **Generate Random Schema** to configure and preview a schema before saving it. Add mode preserves existing tables and records; replace mode requires a separate confirmation before removing them. Reset also asks for confirmation and clears the playground tables; a deliberate reset remains empty on restart.

The PowerShell commands to start the application and run all tests are:

```powershell
python -m pytest -q
python app.py
```

## Demonstration queries

| Example | Query | Expected behavior |
| --- | --- | --- |
| Valid query | `SELECT username, age FROM users WHERE age >= 18;` | Parses, validates against `users`, and returns consistently formatted SQL. |
| Syntax error | `SELECT FROM users WHERE age > 18;` | Reports a syntax error with its line and column; semantic analysis and optimization are blocked. |
| Unknown column | `SELECT nickname FROM users;` | Parses, then reports `nickname` as an unknown column in semantic analysis. |
| Suspicious condition | `SELECT id FROM users WHERE id = 1 OR 1 = 1;` | Flags the constant tautology and its suspicious `OR` use; does not claim that this proves injection. |
| Optimizable query | `SELECT id FROM users WHERE age > 18 AND TRUE AND age > 18;` | Removes `AND TRUE` and the repeated predicate, listing both rules. |

## Supported grammar

The parser supports `SELECT` with named columns or `*`, one table in `FROM`, optional `WHERE`, optional `ORDER BY` with `ASC`/`DESC`, and optional integer `LIMIT`. Conditions support comparisons (`=`, `!=`, `<>`, `<`, `>`, `<=`, `>=`), `AND`, `OR`, `NOT`, parentheses, boolean constants and `IS [NOT] NULL`. String literals use single quotes; escape a quote by doubling it (`'it''s'`). SQL comments, joins, aliases, functions, and other dialect features are outside this grammar and are reported rather than treated as valid.

## Compiler stages and files

- **Lexer:** `analyzer/lexer.py` creates typed tokens with source positions and reports invalid characters and unterminated strings.
- **AST and parser:** `analyzer/ast_nodes.py` defines genuine AST node types; `analyzer/parser.py` is a recursive-descent parser with `NOT` > `AND` > `OR` precedence.
- **Workspace and semantic analyzer:** `analyzer/workspace_db.py` stores workspace tables and records in SQLite and exposes live metadata; `analyzer/schema_catalog.py` and `analyzer/semantic_analyzer.py` validate against the actual current schema.
- **Security analyzer:** `analyzer/security_analyzer.py` reports suspicious tautologies, `SELECT *`, unfiltered `DELETE`/`UPDATE`, `DROP`, and multiple statements. Its findings are indicators for review, not proof of exploitability. Parameterized queries are the recommended defense against SQL injection in applications.
- **Optimizer and SQL generator:** `analyzer/optimizer.py` applies boolean simplifications and safe duplicate-`AND` removal directly to the AST; `analyzer/sql_generator.py` emits normalized SQL.
- **Pipeline and web API:** `analyzer/pipeline.py` coordinates compiler stages, reports an overall status, keeps independently available security findings on syntax errors, and withholds optimization output when syntax or semantic validation fails. `app.py` provides analysis, workspace management, random-schema preview/creation, and read-only SELECT execution endpoints.
- **Frontend:** `templates/index.html`, `static/css/style.css`, and `static/js/app.js` implement the responsive dashboard. Example selection only fills the editor; analysis results appear together in one vertically scrollable report without category tabs.
- **Tests:** `tests/` contains focused pytest coverage for the lexer, parser, semantic and security analysis, optimizer, and pipeline/API.

## API

`POST /api/analyze` accepts `{"query":"SELECT id FROM users"}` and returns tokens, AST, semantic results, security findings, optimization output/rules, per-stage status, and stage-specific errors. `POST /api/workspace/random-schema/preview` builds a non-persistent preview; `POST /api/workspace/random-schema/create` saves the preview, requiring `confirm_replace: true` for replace mode. `POST /api/workspace/tables/<table>/records` adds a validated record. `POST /api/run-query` runs only a query that passes the compiler checks, and the playground execution path is restricted to SELECT statements. Invalid request bodies receive a `4xx` response.
