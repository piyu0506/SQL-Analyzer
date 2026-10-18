const samples = {
  valid: "SELECT username, age\nFROM users\nWHERE age >= 18;",
  syntax: "SELECT FROM users WHERE age > 18;",
  schema: "SELECT nickname\nFROM users\nWHERE age >= 18;",
  security: "SELECT id FROM users WHERE id = 1 OR 1 = 1;",
  optimize: "SELECT id FROM users WHERE age > 18 AND TRUE AND age > 18;"
};

const input = document.querySelector("#query-input");
const analyzeButton = document.querySelector("#analyze-button");
const resetButton = document.querySelector("#reset-button");
const requestError = document.querySelector("#request-error");

input.value = samples.valid;
updateLineCount();

document.querySelectorAll("[data-sample]").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = samples[button.dataset.sample];
    updateLineCount();
    input.focus();
  });
});

input.addEventListener("input", updateLineCount);
resetButton.addEventListener("click", () => {
  input.value = "";
  updateLineCount();
  requestError.hidden = true;
  input.focus();
});
analyzeButton.addEventListener("click", runAnalysis);

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});

function updateLineCount() {
  const count = input.value.split("\n").length;
  document.querySelector("#line-count").textContent = `${count} ${count === 1 ? "line" : "lines"}`;
}

function activateTab(name) {
  document.querySelectorAll(".tab-button").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.id !== `panel-${name}`;
  });
}

async function runAnalysis() {
  requestError.hidden = true;
  if (!input.value.trim()) {
    requestError.textContent = "Enter a SQL query before starting the analysis.";
    requestError.hidden = false;
    return;
  }
  analyzeButton.disabled = true;
  analyzeButton.textContent = "Analyzing…";
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: input.value })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
    renderResults(result, input.value);
    activateTab("overview");
    document.querySelector("#run-label").textContent = "Analysis complete";
  } catch (error) {
    requestError.textContent = error.message || "Could not connect to the analyzer.";
    requestError.hidden = false;
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.innerHTML = '<span class="button-icon" aria-hidden="true">▶</span> Analyze query';
  }
}

function renderResults(result, original) {
  renderPipeline(result.pipeline_status);
  renderErrors(result.errors);
  document.querySelector("#original-sql").textContent = original;
  document.querySelector("#optimized-sql").textContent =
    result.optimized_sql ?? "Not generated: the query has a syntax error.";
  document.querySelector("#sql-comparison").hidden = false;
  document.querySelector("#overview-message").hidden = true;
  renderTokens(result.tokens || []);
  renderAst(result.parse_tree);
  renderSemantics(result.semantic_analysis);
  renderSecurity(result.security_findings || []);
  renderRules(result.optimization_explanations || []);
}

function renderPipeline(statuses) {
  document.querySelectorAll(".stage").forEach((stage) => {
    const status = statuses[stage.dataset.stage] || "pending";
    stage.dataset.status = status;
    stage.querySelector(".stage-state").textContent =
      status.charAt(0).toUpperCase() + status.slice(1);
  });
}

function renderErrors(errors) {
  const container = document.querySelector("#overview-errors");
  container.replaceChildren();
  const entries = [];
  for (const [stage, error] of Object.entries(errors || {})) {
    if (Array.isArray(error)) {
      error.forEach((message) => entries.push([stage, message]));
    } else if (error) {
      entries.push([stage, `${error.message} (line ${error.line}, column ${error.column})`]);
    }
  }
  entries.forEach(([stage, message]) => {
    const item = document.createElement("div");
    item.className = "error-item";
    item.textContent = `${stage.toUpperCase()}: ${message}`;
    container.append(item);
  });
  container.hidden = entries.length === 0;
}

function renderTokens(tokens) {
  const rows = document.querySelector("#token-rows");
  rows.replaceChildren();
  document.querySelector("#token-count").textContent = tokens.length;
  document.querySelector("#token-empty").hidden = tokens.length > 0;
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

function renderAst(tree) {
  const container = document.querySelector("#ast-tree");
  container.replaceChildren();
  if (!tree) {
    container.innerHTML = '<p class="muted">No AST: syntax analysis did not produce a valid statement.</p>';
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
    } else if (childValue !== null && typeof childValue === "object") {
      wrapper.append(buildAstNode(childValue, childKey));
    } else {
      wrapper.append(buildAstNode(childValue, childKey));
    }
  });
  return wrapper;
}

function renderSemantics(semantic) {
  const container = document.querySelector("#semantic-results");
  container.replaceChildren();
  if (!semantic || semantic.valid === null) {
    const skipped = document.createElement("p");
    skipped.className = "muted";
    skipped.textContent = "Semantic checks were not run because parsing failed.";
    container.append(skipped);
    return;
  }
  const valid = semantic && semantic.valid;
  const summary = document.createElement("p");
  summary.className = valid ? "semantic-good" : "semantic-bad";
  summary.textContent = valid ? "✓ All referenced tables and columns are valid." : "✕ Semantic checks found issues.";
  container.append(summary);
  (semantic?.errors || []).forEach((message) => {
    const item = document.createElement("div");
    item.className = "finding";
    const text = document.createElement("p");
    text.textContent = message;
    item.append(text);
    container.append(item);
  });
}

function renderSecurity(findings) {
  const container = document.querySelector("#security-results");
  container.replaceChildren();
  if (!findings.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No configured suspicious patterns were detected.";
    container.append(empty);
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
    recommendation.textContent = `Recommendation: ${finding.recommendation}`;
    item.append(severity, title, explanation, recommendation);
    container.append(item);
  });
}

function renderRules(rules) {
  const container = document.querySelector("#optimization-results");
  container.replaceChildren();
  if (!rules.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No optimization rules were needed for this query.";
    container.append(empty);
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
