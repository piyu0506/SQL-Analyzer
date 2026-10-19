const samples = {
  valid: "SELECT username, age\nFROM users\nWHERE age >= 18;",
  syntax: "SELECT FROM users WHERE age > 18;",
  schema: "SELECT nickname\nFROM users\nWHERE age >= 18;",
  security: "SELECT id FROM users WHERE id = 1 OR 1 = 1;",
  optimize: "SELECT id FROM users WHERE age > 18 AND TRUE AND age > 18;"
};

const input = document.querySelector("#query-input");
const exampleQuery = document.querySelector("#example-query");
const analyzeButton = document.querySelector("#analyze-button");
const clearButton = document.querySelector("#reset-button");
const requestError = document.querySelector("#request-error");

input.value = samples.valid;
updateLineCount();

exampleQuery.addEventListener("change", () => {
  const query = samples[exampleQuery.value];
  if (!query) return;
  input.value = query;
  updateLineCount();
  markReportStale("Example loaded · click Analyze Query");
  input.focus();
});

input.addEventListener("input", () => {
  updateLineCount();
  markReportStale("Query changed · click Analyze Query");
});

clearButton.addEventListener("click", () => {
  input.value = "";
  exampleQuery.value = "";
  requestError.hidden = true;
  updateLineCount();
  markReportStale("Awaiting query");
  input.focus();
});

analyzeButton.addEventListener("click", runAnalysis);

function updateLineCount() {
  const count = input.value.split("\n").length;
  document.querySelector("#line-count").textContent =
    `${count} ${count === 1 ? "line" : "lines"}`;
}

function setRunLabel(message) {
  document.querySelector("#run-label").textContent = message;
}

function markReportStale(message) {
  document.querySelector("#analysis-report").hidden = true;
  document.querySelector("#overview-message").hidden = false;
  setRunLabel(message);
}

async function runAnalysis() {
  requestError.hidden = true;
  if (!input.value.trim()) {
    requestError.textContent = "Enter a SQL query before starting the analysis.";
    requestError.hidden = false;
    return;
  }
  analyzeButton.disabled = true;
  analyzeButton.textContent = "Running pipeline…";
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: input.value })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
    renderResults(result, input.value);
    setRunLabel(overallStatusLabel(result.overall_status));
    document.querySelector("#analysis-report").scrollIntoView({
      behavior: "smooth", block: "start"
    });
  } catch (error) {
    requestError.textContent = error.message || "Could not connect to the analyzer.";
    requestError.hidden = false;
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.innerHTML =
      '<span class="button-icon" aria-hidden="true">▶</span> Analyze Query';
  }
}

function overallStatusLabel(status) {
  const labels = {
    passed: "PASS · all applicable stages completed",
    lexical_error: "ERROR · lexical analysis failed",
    syntax_error: "ERROR · syntax analysis failed",
    semantic_error: "INVALID · semantic validation failed"
  };
  return labels[status] || "Analysis complete";
}

function renderResults(result, original) {
  const statuses = result.pipeline_status || {};
  document.querySelector("#analysis-report").hidden = false;
  document.querySelector("#overview-message").hidden = true;
  renderOverallStatus(result.overall_status, statuses);
  renderPipeline(statuses);
  renderSyntaxResults(result.errors, statuses);
  renderTokens(result.tokens || [], statuses);
  renderAst(result.parse_tree, statuses);
  renderSemantics(result.semantic_analysis, statuses);
  renderSecurity(result.security_findings || [], statuses);
  renderRules(
    result.optimization_explanations || [],
    statuses,
    result.semantic_analysis
  );
  renderSqlComparison(result, original, statuses);
}

function renderOverallStatus(overallStatus, statuses) {
  const container = document.querySelector("#overall-status");
  container.replaceChildren();
  const label = document.createElement("strong");
  label.className = overallStatus === "passed" ? "semantic-good" : "semantic-bad";
  label.textContent = overallStatusLabel(overallStatus);
  container.append(label);
  if (overallStatus !== "passed") {
    const explanation = document.createElement("p");
    explanation.className = "muted";
    explanation.textContent = getFailureSummary(overallStatus, statuses);
    container.append(explanation);
  }
}

function getFailureSummary(status, statuses) {
  if (status === "lexical_error") {
    return "The lexer could not produce a complete token stream. Later parsing and validation stages were not run.";
  }
  if (status === "syntax_error") {
    return "No valid AST was produced. Semantic analysis and optimization were not run; independent security checks were still performed.";
  }
  if (status === "semantic_error") {
    return "The query parsed successfully, but schema or type checks failed. Security checks were performed; optimization was withheld.";
  }
  if (statuses.optimization === "blocked") {
    return "Optimization was blocked because its required validation stages did not pass.";
  }
  return "Review the stage results below.";
}

function renderPipeline(statuses) {
  document.querySelectorAll(".stage").forEach((stage) => {
    const status = statuses[stage.dataset.stage] || "pending";
    stage.dataset.status = status;
    stage.querySelector(".stage-state").textContent = status.toUpperCase();
  });
}

function stageLabel(status) {
  return {
    passed: "PASS",
    failed: "ERROR",
    blocked: "NOT RUN",
    pending: "NOT RUN"
  }[status] || status.toUpperCase();
}

function renderSyntaxResults(errors, statuses) {
  const container = document.querySelector("#syntax-results");
  container.replaceChildren();
  const stages = [
    ["Lexical analysis", statuses.lexical_analysis],
    ["Syntax", statuses.syntax_analysis],
    ["AST construction", statuses.ast_construction]
  ];
  stages.forEach(([name, status]) => {
    const summary = document.createElement("p");
    summary.className = status === "passed" ? "semantic-good" :
      status === "failed" ? "semantic-bad" : "muted";
    summary.textContent = `${name}: ${stageLabel(status)}`;
    container.append(summary);
  });
  [
    ["Lexical error", errors?.lexical],
    ["Syntax error", errors?.syntax]
  ].forEach(([stage, error]) => {
    if (!error) return;
    const item = document.createElement("div");
    item.className = "error-item";
    item.textContent =
      `${stage}: ${error.message} (line ${error.line}, column ${error.column})`;
    container.append(item);
  });
  if (!errors?.lexical && !errors?.syntax &&
      statuses.lexical_analysis === "passed" &&
      statuses.syntax_analysis === "passed") {
    appendMessage(container, "muted", "No lexical or syntax errors.");
  }
}

function renderTokens(tokens, statuses) {
  const rows = document.querySelector("#token-rows");
  rows.replaceChildren();
  document.querySelector("#token-count").textContent = `(${tokens.length})`;
  document.querySelector("#token-empty").hidden = tokens.length > 0;
  if (statuses.lexical_analysis !== "passed") return;
  tokens.forEach((token) => {
    const row = document.createElement("tr");
    [token.type, String(token.value), token.line, token.column].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    });
    rows.append(row);
  });
}

function renderAst(tree, statuses) {
  const container = document.querySelector("#ast-tree");
  container.replaceChildren();
  if (!tree) {
    const reason = statuses.syntax_analysis === "failed"
      ? "NOT RUN — syntax analysis failed; no valid AST was constructed."
      : "NOT RUN — lexical analysis failed; a complete token stream is unavailable.";
    appendMessage(container, "muted", reason);
    return;
  }
  container.append(buildAstNode(tree));
}

function buildAstNode(value, key = null) {
  const wrapper = document.createElement("div");
  wrapper.className = "ast-node";
  const label = document.createElement("div");
  label.className = "ast-label";
  if (key) {
    const keySpan = document.createElement("span");
    keySpan.className = "ast-key";
    keySpan.textContent = `${key}: `;
    label.append(keySpan);
  }
  if (value === null || typeof value !== "object") {
    const valueSpan = document.createElement("span");
    valueSpan.className = "ast-value";
    valueSpan.textContent = value === null ? "null" : String(value);
    label.append(valueSpan);
    wrapper.append(label);
    return wrapper;
  }
  if (value.type) {
    const typeSpan = document.createElement("span");
    typeSpan.className = "ast-key";
    typeSpan.textContent = value.type;
    label.append(typeSpan);
    wrapper.append(label);
  }
  Object.entries(value).forEach(([childKey, childValue]) => {
    if (childKey === "type") return;
    if (Array.isArray(childValue)) {
      const group = document.createElement("div");
      group.className = "ast-node";
      const groupLabel = document.createElement("div");
      groupLabel.className = "ast-label ast-key";
      groupLabel.textContent = `${childKey}:`;
      group.append(groupLabel);
      childValue.forEach((item) => group.append(buildAstNode(item)));
      wrapper.append(group);
    } else {
      wrapper.append(buildAstNode(childValue, childKey));
    }
  });
  return wrapper;
}

function renderSemantics(semantic, statuses) {
  const container = document.querySelector("#semantic-results");
  container.replaceChildren();
  if (statuses.semantic_analysis === "blocked" || semantic?.valid === null) {
    appendMessage(
      container,
      "muted",
      `NOT RUN — ${statuses.lexical_analysis !== "passed"
        ? "lexical analysis failed."
        : "syntax analysis failed; no valid AST is available."}`
    );
    return;
  }
  if (semantic?.valid) {
    appendMessage(container, "semantic-good", "PASS — all referenced tables and columns are valid.");
    return;
  }
  appendMessage(container, "semantic-bad", "ERROR — semantic validation failed.");
  (semantic?.errors || []).forEach((message) => {
    const item = document.createElement("div");
    item.className = "finding";
    const text = document.createElement("p");
    text.textContent = message;
    item.append(text);
    container.append(item);
  });
}

function renderSecurity(findings, statuses) {
  const container = document.querySelector("#security-results");
  container.replaceChildren();
  if (statuses.security_analysis !== "passed") {
    appendMessage(
      container,
      "muted",
      "NOT RUN — lexical analysis did not produce tokens for security checks."
    );
    return;
  }
  appendMessage(container, "semantic-good", "Security analysis completed.");
  if (!findings.length) {
    appendMessage(container, "muted", "No configured suspicious patterns were detected.");
    return;
  }
  findings.forEach((finding) => {
    const item = document.createElement("article");
    item.className = "finding";
    const severity = document.createElement("span");
    severity.className = `severity severity-${finding.severity.toLowerCase()}`;
    severity.textContent = finding.severity;
    const title = document.createElement("h4");
    title.textContent = finding.finding;
    const explanation = document.createElement("p");
    explanation.textContent = finding.explanation;
    const recommendation = document.createElement("p");
    recommendation.className = "recommendation";
    recommendation.textContent = `Recommended fix: ${finding.recommendation}`;
    item.append(severity, title, explanation, recommendation);
    container.append(item);
  });
}

function renderRules(rules, statuses, semantic) {
  const container = document.querySelector("#optimization-results");
  container.replaceChildren();
  if (statuses.optimization !== "passed") {
    appendMessage(
      container,
      "muted",
      `NOT RUN — ${getOptimizationBlockedMessage(statuses)}`
    );
    return;
  }
  appendMessage(container, "semantic-good", "Optimization completed on the validated AST.");
  if (!rules.length) {
    appendMessage(
      container,
      "muted",
      semantic?.valid
        ? "No optimization rules were needed."
        : "No optimization rules were applied."
    );
    return;
  }
  rules.forEach((rule) => {
    const item = document.createElement("article");
    item.className = "rule";
    const title = document.createElement("h4");
    title.textContent = rule.rule;
    const explanation = document.createElement("p");
    explanation.textContent = rule.explanation;
    item.append(title, explanation);
    container.append(item);
  });
}

function getOptimizationBlockedMessage(statuses) {
  if (statuses.lexical_analysis !== "passed") {
    return "lexical analysis failed, so no valid token stream or SQL syntax tree is available.";
  }
  if (statuses.syntax_analysis !== "passed") {
    return "SQL syntax failed; optimization cannot run on an invalid AST.";
  }
  if (statuses.semantic_analysis !== "passed") {
    return "semantic validation failed; optimized SQL cannot be presented as validated.";
  }
  return "the optimization stage did not complete.";
}

function renderSqlComparison(result, original, statuses) {
  document.querySelector("#original-sql").textContent = original;
  const optimized = document.querySelector("#optimized-sql");
  const valid = statuses.semantic_analysis === "passed" &&
    statuses.optimization === "passed" &&
    result.optimized_sql !== null;
  const card = optimized.closest(".optimized-result");
  card.classList.toggle("withheld", !valid);
  document.querySelector("#optimization-label").textContent =
    valid ? "Optimized SQL · validated" : "Optimization not run";
  optimized.textContent = valid
    ? result.optimized_sql
    : `NOT RUN — ${getOptimizationBlockedMessage(statuses)}`;
}

function appendMessage(container, className, message) {
  const element = document.createElement("p");
  element.className = className;
  element.textContent = message;
  container.append(element);
}
