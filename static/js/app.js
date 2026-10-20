const samples = {
  valid: "SELECT username, age\nFROM users\nWHERE age >= 18;",
  syntax: "SELECT FROM users WHERE age > 18;",
  schema: "SELECT nickname\nFROM users\nWHERE age >= 18;",
  security: "SELECT id FROM users WHERE id = 1 OR 1 = 1;",
  optimize: "SELECT id FROM users WHERE age > 18 AND TRUE AND age > 18;"
};

const state = {
  workspace: { tables: [] },
  selectedTable: null,
  editingTable: null,
  randomPreview: null,
};

const input = document.querySelector("#query-input");
const exampleQuery = document.querySelector("#example-query");
const analyzeButton = document.querySelector("#analyze-button");
const runQueryButton = document.querySelector("#run-query-button");
const clearButton = document.querySelector("#reset-button");
const requestError = document.querySelector("#request-error");
const queryResultPanel = document.querySelector("#query-result-panel");
const queryResultTable = document.querySelector("#query-result-table");

const tableList = document.querySelector("#table-list");
const tableForm = document.querySelector("#table-form");
const tableNameInput = document.querySelector("#table-name-input");
const columnBuilder = document.querySelector("#column-builder");
const addColumnButton = document.querySelector("#add-column-button");
const schemaDdl = document.querySelector("#schema-ddl");
const tablePreview = document.querySelector("#table-preview");
const rowsPerTableInput = document.querySelector("#rows-per-table");
const workspaceMessage = document.querySelector("#workspace-message");
const activeSchemaHint = document.querySelector("#active-schema-hint");
const newTableButton = document.querySelector("#new-table-button");
const resetWorkspaceButton = document.querySelector("#reset-workspace-button");
const refreshSchemaButton = document.querySelector("#refresh-schema");
const generateSampleDataButton = document.querySelector("#generate-sample-data-button");
const deleteTableButton = document.querySelector("#delete-table-button");
const recordForm = document.querySelector("#record-form");
const randomTheme = document.querySelector("#random-theme");
const randomTableCount = document.querySelector("#random-table-count");
const randomColumnsCount = document.querySelector("#random-columns-count");
const randomMode = document.querySelector("#random-mode");
const randomRelationships = document.querySelector("#random-relationships");
const randomSampleData = document.querySelector("#random-sample-data");
const randomRowsCount = document.querySelector("#random-rows-count");
const randomPreviewContainer = document.querySelector("#random-schema-preview");
const previewRandomButton = document.querySelector("#preview-random-schema");
const createRandomButton = document.querySelector("#create-random-schema");

input.value = samples.valid;
updateLineCount();
initializeWorkspace();

exampleQuery.addEventListener("change", () => {
  const query = samples[exampleQuery.value];
  if (!query) return;
  input.value = query;
  queryResultPanel.hidden = true;
  updateLineCount();
  markReportStale("Example loaded · click Analyze Query");
  input.focus();
});

input.addEventListener("input", () => {
  updateLineCount();
  queryResultPanel.hidden = true;
  markReportStale("Query changed · click Analyze Query");
});

clearButton.addEventListener("click", () => {
  input.value = "";
  exampleQuery.value = "";
  requestError.hidden = true;
  queryResultPanel.hidden = true;
  updateLineCount();
  markReportStale("Awaiting query");
  input.focus();
});

analyzeButton.addEventListener("click", runAnalysis);
runQueryButton.addEventListener("click", runSelectedQuery);
newTableButton.addEventListener("click", resetTableForm);
refreshSchemaButton.addEventListener("click", () => fetchWorkspace(true));
resetWorkspaceButton.addEventListener("click", resetWorkspace);
addColumnButton.addEventListener("click", () => addColumnRow());
generateSampleDataButton.addEventListener("click", generateSampleData);
deleteTableButton.addEventListener("click", deleteSelectedTable);
tableForm.addEventListener("submit", saveTable);
recordForm.addEventListener("submit", insertManualRecord);
previewRandomButton.addEventListener("click", previewRandomSchema);
createRandomButton.addEventListener("click", createRandomSchema);
randomMode.addEventListener("change", () => {
  state.randomPreview = null;
  createRandomButton.disabled = true;
  randomPreviewContainer.replaceChildren();
});
[
  randomTheme,
  randomTableCount,
  randomColumnsCount,
  randomRelationships,
].forEach((control) => control.addEventListener("change", () => {
  state.randomPreview = null;
  createRandomButton.disabled = true;
  randomPreviewContainer.replaceChildren();
}));
randomSampleData.addEventListener("change", () => {
  randomRowsCount.disabled = !randomSampleData.checked;
});

function updateLineCount() {
  const count = input.value.split("\n").length;
  document.querySelector("#line-count").textContent = `${count} ${count === 1 ? "line" : "lines"}`;
}

function setRunLabel(message) {
  document.querySelector("#run-label").textContent = message;
}

function markReportStale(message) {
  document.querySelector("#analysis-report").hidden = true;
  document.querySelector("#overview-message").hidden = false;
  setRunLabel(message);
}

async function fetchWorkspace(showMessage = false) {
  try {
    const response = await fetch("/api/workspace");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load the workspace.");
    state.workspace = result;
    if (!state.selectedTable && result.tables.length) {
      state.selectedTable = result.tables[0].name;
    }
    if (state.selectedTable && !result.tables.some((table) => table.name === state.selectedTable)) {
      state.selectedTable = result.tables[0]?.name || null;
    }
    if (!state.editingTable && state.selectedTable) {
      state.editingTable = state.selectedTable;
    }
    renderWorkspace(result, showMessage);
  } catch (error) {
    setWorkspaceMessage(error.message || "Workspace could not be refreshed.", "error");
  }
}

function renderWorkspace(data, showMessage = false) {
  renderTableList(data.tables || []);
  renderTableDetails(data.tables || []);
  const selected = (data.tables || []).find((table) => table.name === state.selectedTable);
  if (selected && state.editingTable === selected.name) {
    fillTableForm(selected);
  }
  if (data.tables && data.tables.length) {
    const names = data.tables.map((table) => table.name).join(" · ");
    activeSchemaHint.textContent = `Schema: ${names}`;
  } else {
    activeSchemaHint.textContent = "Schema: no tables yet";
  }
  if (typeof showMessage === "string") {
    setWorkspaceMessage(showMessage, "success");
  } else if (showMessage) {
    setWorkspaceMessage("Schema refreshed.", "success");
  }
}

function renderTableList(tables) {
  tableList.replaceChildren();
  if (!tables.length) {
    const empty = document.createElement("li");
    empty.className = "empty-list-item";
    empty.textContent = "No tables yet";
    tableList.append(empty);
    return;
  }

  tables.forEach((table) => {
    const item = document.createElement("li");
    item.className = "table-list-item" + (state.selectedTable === table.name ? " selected" : "");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "table-list-button";
    button.textContent = `${table.name} (${table.row_count ?? 0})`;
    button.addEventListener("click", () => {
      state.selectedTable = table.name;
      state.editingTable = table.name;
      renderTableList(tables);
      renderTableDetails(tables);
      fillTableForm(table);
    });
    item.append(button);
    tableList.append(item);
  });
}

function renderTableDetails(tables) {
  const selected = tables.find((table) => table.name === state.selectedTable) || tables[0] || null;
  if (!selected) {
    schemaDdl.textContent = "-- No tables available";
    tablePreview.innerHTML = "<p class=\"muted\">Choose a table to preview the schema and rows.</p>";
    renderRecordForm(null);
    return;
  }
  const ddl = selected.ddl || `-- ${selected.name} has no saved DDL`;
  schemaDdl.textContent = ddl;
  renderRecordForm(selected);
  const rows = selected.preview || [];
  if (!rows.length) {
    tablePreview.innerHTML = `<p class="muted">No rows yet for ${selected.name}.</p>`;
    return;
  }
  const columns = (selected.columns || []).map((column) => column.name);
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const headerRow = head.insertRow();
  columns.forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column;
    headerRow.append(th);
  });
  const actionsHeader = document.createElement("th");
  actionsHeader.textContent = "Actions";
  headerRow.append(actionsHeader);
  table.append(head);
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.dataset.rowid = String(row.__workspace_rowid);
    tr.dataset.primaryKey = selected.primary_key || "";
    if (selected.primary_key) {
      tr.dataset.primaryKeyValue = String(row[selected.primary_key]);
    }
    columns.forEach((column) => {
      const td = document.createElement("td");
      td.dataset.column = column;
      td.dataset.value = row[column] == null ? "" : String(row[column]);
      td.textContent = row[column] == null ? "NULL" : String(row[column]);
      tr.append(td);
    });
    const actions = document.createElement("td");
    actions.className = "record-actions";
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "button button-secondary small-button";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => editRecordRow(tr, columns, selected));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "button button-secondary small-button danger-button";
    remove.textContent = "Delete";
    remove.addEventListener("click", () => deleteRecordRow(tr, selected));
    actions.append(edit, remove);
    tr.append(actions);
    body.append(tr);
  });
  table.append(body);
  tablePreview.replaceChildren(table);
}

function renderRecordForm(table) {
  recordForm.replaceChildren();
  if (!table) {
    document.querySelector("#record-form-heading").textContent = "Insert a record";
    recordForm.innerHTML = '<p class="muted">Select or create a table to add records.</p>';
    return;
  }
  document.querySelector("#record-form-heading").textContent = `Insert a record into ${table.name}`;
  (table.columns || []).forEach((column) => {
    const wrapper = document.createElement("label");
    wrapper.className = "record-field";
    wrapper.textContent = `${column.name} · ${column.type}${column.primary_key ? " · PK" : ""}`;
    let field;
    if (column.type === "BOOLEAN") {
      field = document.createElement("select");
      field.innerHTML = '<option value="">Select…</option><option value="true">true</option><option value="false">false</option>';
    } else {
      field = document.createElement("input");
      field.type = column.type === "INTEGER" ? "number" :
        ["DECIMAL", "REAL"].includes(column.type) ? "number" :
          column.type === "DATE" ? "date" : "text";
      if (["DECIMAL", "REAL"].includes(column.type)) field.step = "any";
    }
    field.name = column.name;
    field.dataset.primaryKey = String(column.primary_key);
    if (column.not_null && !(column.primary_key && column.type === "INTEGER")) {
      field.required = true;
    }
    if (column.primary_key && column.type === "INTEGER") {
      field.placeholder = "Generated automatically if blank";
    }
    if (column.references) {
      field.title = `References ${column.references}`;
    }
    wrapper.append(field);
    recordForm.append(wrapper);
  });
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "button button-primary small-button";
  submit.textContent = "Insert Record";
  recordForm.append(submit);
}

function editRecordRow(row, columns, table) {
  const actionCell = row.lastElementChild;
  actionCell.replaceChildren();
  columns.forEach((column) => {
    const cell = row.querySelector(`[data-column="${CSS.escape(column)}"]`);
    const inputField = document.createElement("input");
    inputField.type = ["INTEGER", "DECIMAL", "REAL"].includes(columnType(table, column))
      ? "number" : columnType(table, column) === "DATE" ? "date" : "text";
    if (["DECIMAL", "REAL"].includes(columnType(table, column))) inputField.step = "any";
    inputField.value = cell.dataset.value;
    cell.replaceChildren(inputField);
  });
  const save = document.createElement("button");
  save.type = "button";
  save.className = "button button-primary small-button";
  save.textContent = "Save";
  save.addEventListener("click", () => saveRecordRow(row, columns, table));
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "button button-secondary small-button";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", () => fetchWorkspace());
  actionCell.append(save, cancel);
}

function columnType(table, name) {
  return table.columns.find((column) => column.name === name)?.type || "TEXT";
}

async function saveRecordRow(row, columns, table) {
  const values = {};
  columns.forEach((column) => {
    values[column] = row.querySelector(`[data-column="${CSS.escape(column)}"] input`).value;
  });
  const locator = table.primary_key
    ? { [table.primary_key]: row.dataset.primaryKeyValue }
    : { rowid: Number(row.dataset.rowid) };
  if (!table.primary_key) locator.rowid = Number(row.dataset.rowid);
  try {
    const response = await fetch(`/api/workspace/tables/${encodeURIComponent(table.name)}/records`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locator, values }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Record could not be updated.");
    setWorkspaceMessage(result.message, "success");
    await fetchWorkspace();
  } catch (error) {
    setWorkspaceMessage(error.message || "Could not update record.", "error");
  }
}

async function deleteRecordRow(row, table) {
  if (!window.confirm(`Delete this record from '${table.name}'?`)) return;
  const locator = table.primary_key
    ? { [table.primary_key]: row.dataset.primaryKeyValue }
    : { rowid: Number(row.dataset.rowid) };
  if (!table.primary_key) locator.rowid = Number(row.dataset.rowid);
  try {
    const response = await fetch(`/api/workspace/tables/${encodeURIComponent(table.name)}/records`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locator, confirm_delete: true }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Record could not be deleted.");
    setWorkspaceMessage(result.message, "success");
    await fetchWorkspace();
  } catch (error) {
    setWorkspaceMessage(error.message || "Could not delete record.", "error");
  }
}

async function insertManualRecord(event) {
  event.preventDefault();
  if (!state.selectedTable) {
    setWorkspaceMessage("Select a table before inserting a record.", "error");
    return;
  }
  const values = {};
  recordForm.querySelectorAll("[name]").forEach((field) => {
    if (field.value !== "") values[field.name] = field.value;
  });
  try {
    const response = await fetch(`/api/workspace/tables/${encodeURIComponent(state.selectedTable)}/records`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Record could not be inserted.");
    setWorkspaceMessage(result.message, "success");
    await fetchWorkspace();
    renderRecordForm(state.workspace.tables.find((table) => table.name === state.selectedTable));
  } catch (error) {
    setWorkspaceMessage(error.message || "Could not insert record.", "error");
  }
}

function fillTableForm(table) {
  tableNameInput.value = table.name;
  state.editingTable = table.name;
  columnBuilder.replaceChildren();
  (table.columns || []).forEach((column) => {
    addColumnRow({
      name: column.name,
      type: column.type,
      primary_key: column.primary_key || false,
      not_null: column.not_null || false,
      unique: column.unique || false,
      references: column.references || "",
    });
  });
  if (!table.columns || !table.columns.length) {
    addColumnRow();
  }
}

function resetTableForm() {
  tableNameInput.value = "";
  state.editingTable = null;
  columnBuilder.replaceChildren();
  addColumnRow();
  setWorkspaceMessage("New table form ready.", "success");
}

function addColumnRow(values = {}) {
  const row = document.createElement("div");
  row.className = "column-row";
  row.innerHTML = `
    <input type="text" class="column-name" placeholder="column_name" value="${escapeHtml(values.name || "")}" />
    <select class="column-type">
      <option value="INTEGER" ${values.type === "INTEGER" ? "selected" : ""}>INTEGER</option>
      <option value="VARCHAR" ${values.type === "VARCHAR" ? "selected" : ""}>VARCHAR</option>
      <option value="TEXT" ${values.type === "TEXT" ? "selected" : ""}>TEXT</option>
      <option value="DECIMAL" ${values.type === "DECIMAL" ? "selected" : ""}>DECIMAL</option>
      <option value="REAL" ${values.type === "REAL" ? "selected" : ""}>REAL</option>
      <option value="BOOLEAN" ${values.type === "BOOLEAN" ? "selected" : ""}>BOOLEAN</option>
      <option value="DATE" ${values.type === "DATE" ? "selected" : ""}>DATE</option>
    </select>
    <label><input type="checkbox" class="column-primary" ${values.primary_key ? "checked" : ""} /> PK</label>
    <label><input type="checkbox" class="column-notnull" ${values.not_null ? "checked" : ""} /> NOT NULL</label>
    <label><input type="checkbox" class="column-unique" ${values.unique ? "checked" : ""} /> UNIQUE</label>
    <input type="text" class="column-reference" placeholder="fk.table.column" value="${escapeHtml(values.references || "")}" />
    <button type="button" class="button button-secondary small-button remove-column-button">Remove</button>
  `;
  row.querySelector(".remove-column-button").addEventListener("click", () => {
    if (columnBuilder.querySelectorAll(".column-row").length > 1) {
      row.remove();
    }
  });
  columnBuilder.append(row);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function collectTableColumns() {
  return [...document.querySelectorAll(".column-row")].map((row) => {
    const name = row.querySelector(".column-name").value.trim();
    const type = row.querySelector(".column-type").value;
    const primaryKey = row.querySelector(".column-primary").checked;
    const notNull = row.querySelector(".column-notnull").checked;
    const unique = row.querySelector(".column-unique").checked;
    const references = row.querySelector(".column-reference").value.trim();
    if (!name) return null;
    return {
      name,
      type,
      primary_key: primaryKey,
      not_null: notNull,
      unique,
      references: references || null,
    };
  }).filter(Boolean);
}

async function saveTable(event) {
  event.preventDefault();
  const tableName = tableNameInput.value.trim();
  const columns = collectTableColumns();
  if (!tableName) {
    setWorkspaceMessage("Enter a table name before saving.", "error");
    return;
  }
  if (!columns.length) {
    setWorkspaceMessage("Add at least one column to the table.", "error");
    return;
  }
  try {
    const payload = {
      name: tableName,
      columns,
      update_existing: !!state.editingTable,
      original_name: state.editingTable || null,
    };
    const response = await fetch("/api/workspace/tables", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Table could not be saved.");
    state.selectedTable = tableName;
    state.editingTable = tableName;
    setWorkspaceMessage(result.message || `Table '${tableName}' saved.`, "success");
    await fetchWorkspace();
  } catch (error) {
    setWorkspaceMessage(error.message || "Could not save the table.", "error");
  }
}

async function deleteSelectedTable() {
  const name = state.selectedTable || tableNameInput.value.trim();
  if (!name) {
    setWorkspaceMessage("Select a table to delete.", "error");
    return;
  }
  if (!window.confirm(`Delete table '${name}' and all of its rows?`)) {
    return;
  }
  try {
    const response = await fetch(`/api/workspace/tables/${encodeURIComponent(name)}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm_delete: true }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The table could not be deleted.");
    state.selectedTable = null;
    state.editingTable = null;
    setWorkspaceMessage(result.message || `Table '${name}' deleted.`, "success");
    resetTableForm();
    await fetchWorkspace();
  } catch (error) {
    setWorkspaceMessage(error.message || "Could not delete the table.", "error");
  }
}

async function resetWorkspace() {
  if (!window.confirm("Reset only the playground database? This removes all user-created tables and sample rows.")) {
    return;
  }
  try {
    const response = await fetch("/api/workspace/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm_reset: true }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The workspace could not be reset.");
    state.selectedTable = null;
    state.editingTable = null;
    resetTableForm();
    setWorkspaceMessage(result.message || "The workspace was reset.", "success");
    await fetchWorkspace();
  } catch (error) {
    setWorkspaceMessage(error.message || "Could not reset the workspace.", "error");
  }
}

async function generateSampleData() {
  const selectedTables = state.selectedTable ? [state.selectedTable] : (state.workspace.tables || []).map((table) => table.name);
  if (!selectedTables.length) {
    setWorkspaceMessage("Create or select a table before generating sample data.", "error");
    return;
  }
  try {
    const response = await fetch("/api/workspace/sample-data", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tables: selectedTables,
        rows_per_table: Number(rowsPerTableInput.value || 10),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Sample data could not be generated.");
    setWorkspaceMessage(result.message || "Sample data generated successfully.", "success");
    await fetchWorkspace(result.message || "Sample data generated successfully.");
  } catch (error) {
    setWorkspaceMessage(error.message || "Could not generate sample data.", "error");
  }
}

async function previewRandomSchema() {
  createRandomButton.disabled = true;
  randomPreviewContainer.replaceChildren();
  try {
    const response = await fetch("/api/workspace/random-schema/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        theme: randomTheme.value,
        table_count: Number(randomTableCount.value),
        columns_per_table: Number(randomColumnsCount.value),
        relationships: randomRelationships.checked,
        mode: randomMode.value,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Schema preview could not be generated.");
    state.randomPreview = result;
    renderRandomSchemaPreview(result);
    createRandomButton.disabled = false;
  } catch (error) {
    randomPreviewContainer.textContent = error.message || "Could not preview the generated schema.";
    randomPreviewContainer.className = "random-schema-preview error";
  }
}

function renderRandomSchemaPreview(preview) {
  randomPreviewContainer.replaceChildren();
  randomPreviewContainer.className = "random-schema-preview";
  const intro = document.createElement("p");
  intro.className = "muted";
  intro.textContent = preview.mode === "replace"
    ? "Replace mode will delete all current playground tables and records after confirmation."
    : "Add mode preserves all current tables and records. Conflicting names are assigned a unique suffix.";
  randomPreviewContainer.append(intro);
  if (Object.keys(preview.renamed_conflicts || {}).length) {
    const renamed = document.createElement("p");
    renamed.className = "workspace-message success";
    renamed.textContent = `Name conflicts resolved: ${Object.entries(preview.renamed_conflicts)
      .map(([original, actual]) => `${original} → ${actual}`).join(", ")}`;
    randomPreviewContainer.append(renamed);
  }
  preview.tables.forEach((table) => {
    const card = document.createElement("article");
    card.className = "random-table-card";
    const heading = document.createElement("h4");
    heading.textContent = table.name;
    const list = document.createElement("ul");
    table.columns.forEach((column) => {
      const item = document.createElement("li");
      const constraints = [
        column.primary_key ? "PRIMARY KEY" : "",
        column.not_null ? "NOT NULL" : "",
        column.unique ? "UNIQUE" : "",
        column.references ? `REFERENCES ${column.references}` : "",
      ].filter(Boolean);
      item.textContent = `${column.name} ${column.type}${constraints.length ? ` · ${constraints.join(" · ")}` : ""}`;
      list.append(item);
    });
    card.append(heading, list);
    randomPreviewContainer.append(card);
  });
}

async function createRandomSchema() {
  if (!state.randomPreview) {
    setWorkspaceMessage("Preview the random schema before creating it.", "error");
    return;
  }
  const replacing = randomMode.value === "replace";
  const confirmReplace = replacing && window.confirm(
    "Replace the entire playground schema?\n\nThis permanently deletes every current table and record, including manually created data."
  );
  if (replacing && !confirmReplace) return;
  createRandomButton.disabled = true;
  try {
    const response = await fetch("/api/workspace/random-schema/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tables: state.randomPreview.tables,
        mode: state.randomPreview.mode,
        confirm_replace: confirmReplace,
        generate_samples: randomSampleData.checked,
        rows_per_table: Number(randomRowsCount.value),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The generated schema could not be saved.");
    state.selectedTable = result.tables[0] || null;
    state.editingTable = result.tables[0] || null;
    state.randomPreview = null;
    randomPreviewContainer.replaceChildren();
    setWorkspaceMessage(result.message || "Random schema created.", "success");
    await fetchWorkspace();
  } catch (error) {
    setWorkspaceMessage(error.message || "Could not create the random schema.", "error");
    createRandomButton.disabled = false;
  }
}

function setWorkspaceMessage(message, type = "success") {
  workspaceMessage.textContent = message;
  workspaceMessage.className = `workspace-message ${type}`;
}

async function initializeWorkspace() {
  resetTableForm();
  await fetchWorkspace();
}

async function runSelectedQuery() {
  requestError.hidden = true;
  requestError.classList.remove("request-success");
  queryResultPanel.hidden = true;
  const query = input.value.trim();
  if (!query) {
    requestError.textContent = "Enter a SQL query before running it.";
    requestError.hidden = false;
    return;
  }
  runQueryButton.disabled = true;
  try {
    const response = await fetch("/api/run-query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const result = await response.json();
    if (!response.ok) {
      if (result.analysis) {
        renderResults(result.analysis, query);
        setRunLabel(`BLOCKED · ${overallStatusLabel(result.analysis.overall_status)}`);
      }
      const message = result.error || "Query execution was blocked.";
      requestError.textContent = message;
      requestError.hidden = false;
      return;
    }
    renderResults(result.analysis, query);
    renderQueryResult(result.result);
    requestError.textContent = `Query executed successfully · ${result.result.row_count || 0} row(s) returned.`;
    requestError.classList.add("request-success");
    requestError.hidden = false;
    setRunLabel("EXECUTED · result set returned");
  } catch (error) {
    requestError.textContent = error.message || "Could not run the query.";
    requestError.hidden = false;
  } finally {
    runQueryButton.disabled = false;
  }
}

function renderQueryResult(result) {
  queryResultTable.replaceChildren();
  queryResultPanel.hidden = false;
  const columns = result.columns || [];
  const rows = result.rows || [];
  if (!columns.length) {
    appendMessage(queryResultTable, "muted", "Query completed with no result rows.");
    return;
  }
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const header = head.insertRow();
  columns.forEach((column) => {
    const cell = document.createElement("th");
    cell.textContent = column;
    header.append(cell);
  });
  table.append(head);
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = body.insertRow();
    columns.forEach((column) => {
      const cell = tr.insertCell();
      cell.textContent = row[column] == null ? "NULL" : String(row[column]);
    });
  });
  table.append(body);
  queryResultTable.append(table);
  if (result.truncated) {
    appendMessage(
      queryResultTable,
      "muted",
      `Showing the first ${result.row_limit} rows. Refine the query for more specific results.`
    );
  }
}

async function runAnalysis() {
  requestError.hidden = true;
  requestError.classList.remove("request-success");
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
    analyzeButton.innerHTML = '<span class="button-icon" aria-hidden="true">▶</span> Analyze Query';
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
    summary.className = status === "passed" ? "semantic-good" : status === "failed" ? "semantic-bad" : "muted";
    summary.textContent = `${name}: ${stageLabel(status)}`;
    container.append(summary);
  });
  [["Lexical error", errors?.lexical], ["Syntax error", errors?.syntax]].forEach(([stage, error]) => {
    if (!error) return;
    const item = document.createElement("div");
    item.className = "error-item";
    item.textContent = `${stage}: ${error.message} (line ${error.line}, column ${error.column})`;
    container.append(item);
  });
  if (!errors?.lexical && !errors?.syntax && statuses.lexical_analysis === "passed" && statuses.syntax_analysis === "passed") {
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
      semantic?.valid ? "No optimization rules were needed." : "No optimization rules were applied."
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
  document.querySelector("#optimization-label").textContent = valid ? "Optimized SQL · validated" : "Optimization not run";
  optimized.textContent = valid ? result.optimized_sql : `NOT RUN — ${getOptimizationBlockedMessage(statuses)}`;
}

function appendMessage(container, className, message) {
  const element = document.createElement("p");
  element.className = className;
  element.textContent = message;
  container.append(element);
}
