const directoryGrid = document.querySelector("#directory-grid");
const directoryCount = document.querySelector("#directory-count");
const directoriesTitle = document.querySelector("#directories-title");
const fileBrowser = document.querySelector("#file-browser");
const sectionTitle = document.querySelector("#section-title");
const fileBrowserSummary = document.querySelector("#file-browser-summary");
const testTableBody = document.querySelector("#test-table-body");
const tableMessage = document.querySelector("#table-message");
const backButton = document.querySelector("#back-button");
const variablesList = document.querySelector("#variables-list");
const variablesStatus = document.querySelector("#variables-status");
const saveVariablesButton = document.querySelector("#save-variables");
const undefinedVariablesList = document.querySelector("#undefined-variables-list");
const undefinedVariablesStatus = document.querySelector("#undefined-variables-status");
const generateRobotArgumentsButton = document.querySelector("#generate-robot-arguments");
const copyRobotCommandButton = document.querySelector("#copy-robot-command");
const undefinedVariablesResult = document.querySelector("#undefined-variables-result");
const robotCommandPreview = document.querySelector("#robot-command-preview");
const reportNameInput = document.querySelector("#run-report-name");
const runTestsButton = document.querySelector("#run-tests-button");
const runStatus = document.querySelector("#run-status");
const runArtifactLinks = document.querySelector("#run-artifact-links");
const runReportLink = document.querySelector("#run-report-link");
const runLogLink = document.querySelector("#run-log-link");
const runOutputLink = document.querySelector("#run-output-link");
const runOutput = document.querySelector("#run-output");
const tagBoard = document.querySelector("#tag-board");
const tagStatus = document.querySelector("#tag-status");
const tagLists = {
  available: document.querySelector("#available-tag-list"),
  include: document.querySelector("#include-tag-list"),
  exclude: document.querySelector("#exclude-tag-list"),
};
const refreshButton = document.querySelector("#refresh-button");
const refreshFeedback = document.querySelector("#refresh-feedback");
let currentDirectory = null;
let highlightedVariableFields = new Set();
let runInProgress = false;
let runDataReady = false;
let runOutputText = "";
let runOutputTruncated = false;
const maxRunOutputChars = 262144;

const folderIcon = `
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M3.5 6.5h6l2 2h9v9a1.5 1.5 0 0 1-1.5 1.5h-14A1.5 1.5 0 0 1 3.5 17.5z"></path>
    <path d="M3.5 9h17"></path>
  </svg>`;

function renderDirectories(directories) {
  directoryCount.textContent = `${directories.length} ${directories.length === 1 ? "section" : "sections"}`;
  directoryGrid.replaceChildren();

  if (directories.length === 0) {
    const emptyState = document.createElement("div");
    emptyState.className = "empty-state";
    emptyState.innerHTML = "<strong>No directories found</strong><span>Add a folder under <code>test/</code> and refresh.</span>";
    directoryGrid.append(emptyState);
    return;
  }

  directories.forEach((name, index) => {
    const link = document.createElement("a");
    link.className = "directory-card";
    link.id = `directory-${encodeURIComponent(name)}`;
    link.href = `#${link.id}`;
    link.setAttribute("aria-label", `Browse ${name}`);
    link.addEventListener("click", (event) => {
      event.preventDefault();
      loadRobotFiles(name);
      history.replaceState(null, "", `#${link.id}`);
    });
    link.innerHTML = `
      <span class="card-icon">${folderIcon}</span>
      <span class="card-content">
        <span class="card-kicker">SECTION ${(index + 1).toString().padStart(2, "0")}</span>
        <span class="card-title"></span>
        <span class="card-subtitle">Test directory</span>
      </span>
      <span class="card-arrow" aria-hidden="true">↗</span>`;
    link.querySelector(".card-title").textContent = name;
    directoryGrid.append(link);
  });
}

function createCheckbox(label, className) {
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = className;
  checkbox.setAttribute("aria-label", label);
  return checkbox;
}

function updateFileSelection(fileCheckbox, testCheckboxes) {
  const selectedCount = testCheckboxes.filter((checkbox) => checkbox.checked).length;
  fileCheckbox.checked = selectedCount === testCheckboxes.length && testCheckboxes.length > 0;
  fileCheckbox.indeterminate = selectedCount > 0 && selectedCount < testCheckboxes.length;
}

function moveTag(tag, zoneName) {
  tagLists[zoneName].append(tag);
  tag.dataset.zone = zoneName;
  tag.setAttribute("aria-label", `${tag.textContent}, ${zoneName} tags. Press Space to move.`);
  clearGeneratedRobotArguments();
}

function createTagChip(value) {
  const chip = document.createElement("button");
  chip.className = "tag-chip";
  chip.type = "button";
  chip.draggable = true;
  chip.textContent = value;
  chip.dataset.tag = value;
  chip.dataset.zone = "available";
  chip.setAttribute("aria-label", `${value}, available tags. Press Space to move.`);
  chip.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/plain", value);
    event.dataTransfer.effectAllowed = "move";
    chip.classList.add("is-dragging");
  });
  chip.addEventListener("dragend", () => chip.classList.remove("is-dragging"));
  chip.addEventListener("keydown", (event) => {
    if (event.key !== " ") {
      return;
    }
    event.preventDefault();
    const zones = ["available", "include", "exclude"];
    const currentIndex = zones.indexOf(chip.dataset.zone);
    moveTag(chip, zones[(currentIndex + 1) % zones.length]);
  });
  return chip;
}

function renderTags(files) {
  Object.values(tagLists).forEach((list) => list.replaceChildren());
  const uniqueTags = new Map();
  files.forEach((file) => {
    file.test_cases.forEach((testCase) => {
      testCase.tags.forEach((tag) => {
        const normalized = tag.toLocaleLowerCase();
        if (!uniqueTags.has(normalized)) {
          uniqueTags.set(normalized, tag);
        }
      });
    });
  });

  const tags = [...uniqueTags.values()].sort((first, second) => first.localeCompare(second));
  tags.forEach((tag) => tagLists.available.append(createTagChip(tag)));
  tagStatus.textContent = tags.length
    ? `${tags.length} unique ${tags.length === 1 ? "tag" : "tags"} found in this section.`
    : "No test case tags found in this section.";
  tagBoard.setAttribute("aria-busy", "false");
}

function renderRobotFiles(files) {
  testTableBody.replaceChildren();
  const count = files.reduce((total, file) => total + file.test_cases.length, 0);
  fileBrowserSummary.textContent = `${files.length} ${files.length === 1 ? "file" : "files"} · ${count} ${count === 1 ? "test case" : "test cases"}`;
  tableMessage.textContent = "";

  if (files.length === 0) {
    tableMessage.textContent = "No .robot files found in this section.";
    return;
  }

  files.forEach((file) => {
    const fileRow = document.createElement("tr");
    fileRow.className = "file-row";
    const fileNameCell = document.createElement("th");
    fileNameCell.scope = "row";
    fileNameCell.className = "item-name";
    fileNameCell.textContent = file.display_name;
    const fileCheckboxCell = document.createElement("td");
    const fileCheckbox = createCheckbox(
      `Select all tests in ${file.name}`,
      "selection-checkbox file-checkbox",
    );
    fileCheckbox.dataset.fileName = file.name;
    fileCheckboxCell.append(fileCheckbox);
    const expandCell = document.createElement("td");
    const expandButton = document.createElement("button");
    expandButton.className = "expand-button";
    expandButton.type = "button";
    expandButton.textContent = "Show tests";
    expandButton.setAttribute("aria-expanded", "false");
    expandButton.setAttribute("aria-label", `Show test cases in ${file.name}`);
    expandCell.append(expandButton);
    fileRow.append(fileNameCell, fileCheckboxCell, expandCell);
    testTableBody.append(fileRow);

    const testCheckboxes = [];
    const testRows = file.test_cases.map((testCase) => {
      const row = document.createElement("tr");
      row.className = "test-row";
      row.hidden = true;
      const nameCell = document.createElement("td");
      nameCell.className = "item-name test-name";
      nameCell.textContent = testCase.name;
      const checkboxCell = document.createElement("td");
      const checkbox = createCheckbox(
        `Select ${testCase.name} in ${file.name}`,
        "selection-checkbox test-checkbox",
      );
      checkbox.dataset.fileName = file.name;
      checkbox.dataset.testName = testCase.name;
      testCheckboxes.push(checkbox);
      checkboxCell.append(checkbox);
      const infoCell = document.createElement("td");
      if (testCase.documentation) {
        const infoButton = document.createElement("button");
        infoButton.className = "info-button";
        infoButton.type = "button";
        infoButton.textContent = "i";
        infoButton.title = testCase.documentation;
        infoButton.dataset.tooltip = testCase.documentation;
        infoButton.setAttribute("aria-label", `Documentation: ${testCase.documentation}`);
        infoCell.append(infoButton);
      }
      row.append(nameCell, checkboxCell, infoCell);
      return row;
    });

    testRows.forEach((row) => testTableBody.append(row));

    fileCheckbox.addEventListener("change", () => {
      testCheckboxes.forEach((checkbox) => {
        checkbox.checked = fileCheckbox.checked;
      });
      fileCheckbox.indeterminate = false;
    });
    testCheckboxes.forEach((checkbox) => {
      checkbox.addEventListener("change", () => updateFileSelection(fileCheckbox, testCheckboxes));
    });

    expandButton.addEventListener("click", () => {
      const expanded = expandButton.getAttribute("aria-expanded") === "true";
      expandButton.setAttribute("aria-expanded", String(!expanded));
      expandButton.textContent = expanded ? "Show tests" : "Hide tests";
      expandButton.setAttribute(
        "aria-label",
        `${expanded ? "Show" : "Hide"} test cases in ${file.name}`,
      );
      testRows.forEach((row) => {
        row.hidden = expanded;
      });
    });
  });
  updateRunControls();
}

function renderVariables(variables) {
  variablesList.replaceChildren();
  highlightedVariableFields = new Set();
  if (variables.length === 0) {
    variablesStatus.textContent = "No variables found in common.resource.";
    variablesList.append(variablesStatus);
    saveVariablesButton.disabled = true;
    return;
  }

  variables.forEach((variable) => {
    const row = document.createElement("div");
    row.className = "variable-row";
    row.dataset.variableName = variable.name;
    row.dataset.kind = variable.kind;
    row.dataset.expression = String(variable.expression);
    row.dataset.composed = String(variable.composed_from.length > 1);
    const name = document.createElement("span");
    name.className = "variable-name";
    name.textContent = variable.name.replace(/^[\$@&%]\{([^}]*)\}$/, "$1");
    const nameGroup = document.createElement("div");
    nameGroup.className = "variable-name-group";
    nameGroup.append(name);
    if (variable.composed_from.length > 1) {
      const editButton = document.createElement("button");
      editButton.className = "edit-reference-button";
      editButton.type = "button";
      editButton.textContent = "Edit";
      editButton.setAttribute(
        "aria-label",
        `Focus first referenced value in ${name.textContent}`,
      );
      editButton.title = `Focus ${variable.composed_from[0]}`;
      editButton.addEventListener("click", () => {
        highlightedVariableFields.forEach((field) => {
          field.classList.remove("is-reference-target");
        });
        const referencedRows = variable.composed_from.map((reference) => (
          Array.from(variablesList.querySelectorAll(".variable-row"))
            .find((candidate) => candidate.dataset.variableName === reference)
        ));
        const firstValue = referencedRows[0]?.querySelector(".variable-value");
        if (
          !(firstValue instanceof HTMLInputElement)
          || referencedRows.some((referencedRow) => !referencedRow)
        ) {
          variablesStatus.textContent =
            `Could not find the first referenced value (${variable.composed_from[0]}).`;
          variablesList.prepend(variablesStatus);
          return;
        }
        highlightedVariableFields = new Set(
          referencedRows.flatMap((referencedRow) => (
            Array.from(referencedRow.querySelectorAll(".variable-value, .variable-key"))
          )),
        );
        highlightedVariableFields.forEach((field) => {
          field.classList.add("is-reference-target");
        });
        firstValue.focus();
      });
      nameGroup.append(editButton);
    }
    const fields = document.createElement("div");
    fields.className = "variable-fields";
    if (variable.composed_from.length > 1) {
      const referenceList = document.createElement("span");
      referenceList.className = "composed-variable-list";
      referenceList.textContent = variable.composed_from
        .map((reference) => reference.replace(/^[\$@&%]\{([^}]*)\}$/, "$1"))
        .join(", ");
      fields.append(referenceList);
    } else {
      variable.fields.forEach((field, index) => {
        const fieldRow = document.createElement("div");
        fieldRow.className = "variable-field-row";
        if (variable.kind === "dictionary") {
          const key = document.createElement("input");
          key.className = "variable-key";
          key.type = "text";
          key.value = field.key ?? "";
          key.setAttribute("aria-label", `${name.textContent} key ${index + 1}`);
          fieldRow.append(key);
        }

        const value = document.createElement("input");
        value.className = "variable-value variable-field";
        value.type = "text";
        value.value = field.value;
        value.dataset.valueType = field.value_type;
        value.dataset.expression = String(field.expression);
        value.setAttribute("aria-label", `${name.textContent} value ${index + 1}`);
        value.autocomplete = "off";
        value.spellcheck = false;
        fieldRow.append(value);
        fields.append(fieldRow);
      });
    }
    row.append(nameGroup, fields);
    variablesList.append(row);
  });

  saveVariablesButton.disabled = false;
}

const undefinedVariableTypes = [
  ["string", "String"],
  ["integer", "Integer"],
  ["float", "Float"],
  ["boolean", "Boolean"],
  ["none", "None"],
  ["list", "List"],
  ["set", "Set"],
  ["tuple", "Tuple"],
  ["dictionary", "Dictionary"],
];

function clearGeneratedRobotArguments() {
  copyRobotCommandButton.disabled = true;
  undefinedVariablesResult.textContent = "";
  robotCommandPreview.hidden = true;
  robotCommandPreview.textContent = "";
}

function addUndefinedVariableField(fields, kind, initialValue = "", initialKey = "") {
  const fieldRow = document.createElement("div");
  fieldRow.className = "undefined-variable-field";
  if (kind === "dictionary") {
    const key = document.createElement("input");
    key.className = "undefined-variable-key";
    key.type = "text";
    key.placeholder = "Key";
    key.value = initialKey;
    key.setAttribute("aria-label", "Dictionary key");
    fieldRow.append(key);
    fieldRow.classList.add("has-key");
  }

  const value = document.createElement("input");
  value.className = "undefined-variable-value";
  value.type = "text";
  value.placeholder = kind === "scalar" ? "Value" : "Item";
  value.value = initialValue;
  value.setAttribute("aria-label", kind === "scalar" ? "Variable value" : "Collection item");
  fieldRow.append(value);

  if (kind !== "scalar") {
    const removeButton = document.createElement("button");
    removeButton.className = "remove-variable-value";
    removeButton.type = "button";
    removeButton.textContent = "Remove";
    removeButton.setAttribute("aria-label", "Remove value");
    removeButton.addEventListener("click", () => {
      fieldRow.remove();
      clearGeneratedRobotArguments();
    });
    fieldRow.append(removeButton);
  }

  fields.append(fieldRow);
}

function renderUndefinedVariables(variables) {
  undefinedVariablesList.replaceChildren();
  clearGeneratedRobotArguments();
  if (variables.length === 0) {
    undefinedVariablesStatus.textContent = "No undefined variables found in this section’s test cases.";
    undefinedVariablesList.append(undefinedVariablesStatus);
    updateRunControls();
    return;
  }

  variables.forEach((variable) => {
    const row = document.createElement("div");
    row.className = "undefined-variable-row";
    row.dataset.variableName = variable.name;

    const label = document.createElement("label");
    label.className = "undefined-variable-name";
    label.textContent = variable.name.replace(/^[$@&%]\{([^}]*)\}$/, "$1");

    const editor = document.createElement("div");
    editor.className = "undefined-variable-editor";
    const type = document.createElement("select");
    type.className = "undefined-variable-type";
    type.setAttribute("aria-label", `Type for ${label.textContent}`);
    undefinedVariableTypes.forEach(([value, title]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = title;
      type.append(option);
    });
    type.value = [
      "string", "integer", "float", "boolean", "none",
      "list", "set", "tuple", "dictionary",
    ].includes(variable.type_hint)
      ? variable.type_hint
      : "string";
    const fields = document.createElement("div");
    fields.className = "undefined-variable-fields";
    const addValueButton = document.createElement("button");
    addValueButton.className = "add-variable-value";
    addValueButton.type = "button";
    addValueButton.textContent = "Add value";
    addValueButton.hidden = type.value === "string"
      || type.value === "integer"
      || type.value === "float"
      || type.value === "boolean"
      || type.value === "none";

    const updateFields = () => {
      fields.replaceChildren();
      const kind = type.value;
      const isCollection = ["list", "set", "tuple", "dictionary"].includes(kind);
      addValueButton.hidden = !isCollection;
      addUndefinedVariableField(
        fields,
        isCollection ? kind : "scalar",
        isCollection ? "" : variable.suggested_value ?? "",
      );
    };
    type.addEventListener("change", () => {
      updateFields();
      clearGeneratedRobotArguments();
    });
    addValueButton.addEventListener("click", () => {
      addUndefinedVariableField(fields, type.value);
      clearGeneratedRobotArguments();
    });
    updateFields();

    row.append(label, editor);
    editor.append(type, fields, addValueButton);
    undefinedVariablesList.append(row);
  });

  updateRunControls();
}

async function loadUndefinedVariables(directoryName) {
  undefinedVariablesList.replaceChildren();
  undefinedVariablesStatus.textContent = "Loading undefined variables…";
  undefinedVariablesList.append(undefinedVariablesStatus);
  updateRunControls();
  const response = await fetch(
    `/api/directories/${encodeURIComponent(directoryName)}/undefined-variables`,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) {
    throw new Error(`Could not inspect undefined variables (${response.status}).`);
  }
  const variables = await response.json();
  if (
    !Array.isArray(variables)
    || !variables.every((variable) => (
      typeof variable.name === "string"
      && [
        "scalar", "string", "integer", "float", "boolean", "none",
        "list", "set", "tuple", "dictionary",
      ].includes(variable.type_hint)
      && (variable.suggested_value === null || typeof variable.suggested_value === "string")
    ))
  ) {
    throw new Error("The server returned invalid undefined-variable data.");
  }
  renderUndefinedVariables(variables);
}

function serializeRunVariables() {
  const variables = [];
  for (const row of undefinedVariablesList.querySelectorAll(".undefined-variable-row")) {
    const name = row.dataset.variableName;
    const kind = row.querySelector(".undefined-variable-type").value;
    const fields = Array.from(row.querySelectorAll(".undefined-variable-field"));
    const values = fields.map((field) => ({
      key: field.querySelector(".undefined-variable-key")?.value ?? null,
      value: field.querySelector(".undefined-variable-value").value,
      value_type: "string",
      expression: false,
    }));
    if (
      ["list", "set", "tuple"].includes(kind)
      && values.length === 1
      && values[0].value === ""
    ) {
      values.length = 0;
    }
    if (kind === "dictionary") {
      const entries = [];
      for (const field of values) {
        if (!field.key) {
          if (!field.value) {
            continue;
          }
          throw new Error(`${name} dictionary keys cannot be empty.`);
        }
        entries.push(field);
      }
      values.splice(0, values.length, ...entries);
    }
    if (["string", "integer", "float", "boolean", "none"].includes(kind)) {
      const value = fields[0]?.querySelector(".undefined-variable-value").value ?? "";
      if (kind === "integer" && !/^-?(0|[1-9]\d*)$/.test(value)) {
        throw new Error(`${name} must be a whole number.`);
      }
      if (kind === "float" && !/^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) {
        throw new Error(`${name} must be a valid number.`);
      }
      if (kind === "boolean" && !["true", "false"].includes(value.toLowerCase())) {
        throw new Error(`${name} must be true or false.`);
      }
      const scalarField = {
        key: null,
        value: kind === "none"
          ? "None"
          : kind === "boolean"
            ? value.toLowerCase() === "true" ? "True" : "False"
            : value,
        value_type: kind,
        expression: false,
      };
      variables.push({
        name,
        kind: "scalar",
        expression: false,
        composed_from: [],
        fields: [scalarField],
      });
      continue;
    }
    variables.push({
      name,
      kind,
      expression: false,
      composed_from: [],
      fields: values,
    });
  }
  return variables;
}

function serializePredefinedVariables() {
  return Array.from(
    variablesList.querySelectorAll('.variable-row[data-composed="false"]'),
    (row) => ({
      name: row.dataset.variableName,
      kind: row.dataset.kind,
      expression: row.dataset.expression === "true",
      composed_from: [],
      fields: Array.from(row.querySelectorAll(".variable-field"), (input) => {
        const keyInput = input.closest(".variable-field-row").querySelector(".variable-key");
        return {
          key: keyInput ? keyInput.value : null,
          value: input.value,
          value_type: input.dataset.valueType,
          expression: input.dataset.expression === "true",
        };
      }),
    }),
  );
}

function collectRunPayload() {
  if (!currentDirectory) {
    throw new Error("Choose a test section first.");
  }
  const files = new Map();
  testTableBody.querySelectorAll(".test-checkbox:checked").forEach((checkbox) => {
    const fileName = checkbox.dataset.fileName;
    const testName = checkbox.dataset.testName;
    if (!files.has(fileName)) {
      files.set(fileName, []);
    }
    files.get(fileName).push(testName);
  });
  if (files.size === 0) {
    throw new Error("Select at least one test case to run.");
  }
  const tagsInZone = (zoneName) => Array.from(
    tagLists[zoneName].querySelectorAll(".tag-chip"),
    (chip) => chip.dataset.tag,
  );
  return {
    directory: currentDirectory,
    files: Array.from(files, ([name, tests]) => ({ name, tests })),
    variables: serializeRunVariables(),
    predefined_variables: serializePredefinedVariables(),
    include_tags: tagsInZone("include"),
    exclude_tags: tagsInZone("exclude"),
    report_name: reportNameInput.value.trim() || null,
  };
}

function updateCommandPreview(command) {
  robotCommandPreview.textContent = command;
  robotCommandPreview.hidden = false;
  copyRobotCommandButton.disabled = false;
}

async function sendRunRequest(endpoint, payload) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(result.detail)
      ? result.detail.map((item) => item.msg).join(" ")
      : result.detail;
    throw new Error(detail || `Request failed (${response.status}).`);
  }
  return result;
}

function updateRunControls() {
  const selectedCount = testTableBody.querySelectorAll(".test-checkbox:checked").length;
  const disabled = selectedCount === 0 || runInProgress || !runDataReady;
  runTestsButton.disabled = disabled;
  generateRobotArgumentsButton.disabled = disabled;
}

async function prepareRobotCommand() {
  clearGeneratedRobotArguments();
  try {
    const result = await sendRunRequest("/api/runs/preview", collectRunPayload());
    reportNameInput.value = result.report_name;
    updateCommandPreview(result.command);
    undefinedVariablesResult.textContent =
      `Command ready. Variables are saved in tmp/variables_${result.report_name}.py.`;
  } catch (error) {
    undefinedVariablesResult.textContent = error instanceof Error
      ? error.message
      : "Could not prepare the Robot Framework command.";
  }
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function updateRunOutput(output) {
  const wasAtBottom = runOutput.scrollHeight - runOutput.scrollTop - runOutput.clientHeight < 24;
  runOutputText = output;
  runOutputTruncated = false;
  renderRunOutput(wasAtBottom);
}

function appendRunOutput(text) {
  const wasAtBottom = runOutput.scrollHeight - runOutput.scrollTop - runOutput.clientHeight < 24;
  runOutputText += text;
  if (runOutputText.length > maxRunOutputChars) {
    runOutputText = runOutputText.slice(-maxRunOutputChars);
    runOutputTruncated = true;
  }
  renderRunOutput(wasAtBottom);
}

function renderRunOutput(shouldScroll) {
  const truncatedNotice = runOutputTruncated
    ? "[Earlier console output omitted because the display buffer is full.]\n"
    : "";
  const output = truncatedNotice + (runOutputText || "Waiting for Robot Framework output…");
  const fragment = document.createDocumentFragment();
  const statusPattern = /\|\s*(PASS|SKIP|FAIL)\s*\|/g;
  let previousEnd = 0;
  let match;
  while ((match = statusPattern.exec(output)) !== null) {
    fragment.append(document.createTextNode(output.slice(previousEnd, match.index)));
    const status = document.createElement("span");
    status.className = `run-output-status is-${match[1].toLowerCase()}`;
    status.textContent = match[0];
    fragment.append(status);
    previousEnd = statusPattern.lastIndex;
  }
  fragment.append(document.createTextNode(output.slice(previousEnd)));
  runOutput.replaceChildren(fragment);
  if (shouldScroll) {
    runOutput.scrollTop = runOutput.scrollHeight;
  }
}

function connectRunOutput(runId) {
  return new Promise((resolve, reject) => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      `${protocol}//${window.location.host}/ws/runs/${encodeURIComponent(runId)}`,
    );
    let receivedSnapshot = false;

    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === "snapshot") {
        receivedSnapshot = true;
        runOutputText = message.text || "";
        runOutputTruncated = Boolean(message.truncated);
        renderRunOutput(true);
        resolve(socket);
      } else if (message.type === "output") {
        appendRunOutput(message.text || "");
      }
    });
    socket.addEventListener("error", () => {
      if (!receivedSnapshot) {
        reject(new Error("Could not connect to the live Robot Framework output stream."));
      }
    });
    socket.addEventListener("close", () => {
      if (!receivedSnapshot) {
        reject(new Error("The live Robot Framework output stream closed before connecting."));
      }
    });
  });
}

function updateRunArtifactLinks(result) {
  const links = [
    [runReportLink, result.report_url, `Open report: ${result.report_name}`],
    [runLogLink, result.log_url, "Open log"],
    [runOutputLink, result.output_url, "Open output.xml"],
  ];
  links.forEach(([link, url, label]) => {
    link.hidden = !url;
    if (url) {
      link.href = url;
      link.textContent = label;
    }
  });
  runArtifactLinks.hidden = links.every(([, url]) => !url);
}

async function watchRobotRun(runId) {
  while (true) {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`, {
      headers: { Accept: "application/json" },
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || `Could not check run status (${response.status}).`);
    }
    if (result.status === "queued" || result.status === "running") {
      runStatus.textContent = result.status === "queued"
        ? "Your tests are queued…"
        : "Robot Framework is running…";
      await wait(1000);
      continue;
    }
    runStatus.textContent = result.message || "Robot Framework run finished.";
    if (result.exit_code !== null && result.exit_code !== 0) {
      runStatus.textContent += " Open the report to see the results.";
    }
    updateRunArtifactLinks(result);
    return;
  }
}

async function runSelectedTests() {
  let outputSocket;
  runInProgress = true;
  runTestsButton.textContent = "Starting…";
  runStatus.textContent = "Preparing your test run…";
  runArtifactLinks.hidden = true;
  updateRunOutput("");
  clearGeneratedRobotArguments();
  updateRunControls();
  try {
    const result = await sendRunRequest("/api/runs", collectRunPayload());
    reportNameInput.value = result.report_name;
    updateCommandPreview(result.command);
    undefinedVariablesResult.textContent =
      `Command used for this run. Variables are saved in tmp/variables_${result.report_name}.py.`;
    runStatus.textContent = "Your tests are queued…";
    try {
      outputSocket = await connectRunOutput(result.run_id);
    } catch (error) {
      runStatus.textContent = error instanceof Error
        ? error.message
        : "Could not connect to the live command output.";
    }
    await watchRobotRun(result.run_id);
  } catch (error) {
    runStatus.textContent = error instanceof Error
      ? error.message
      : "Could not start Robot Framework.";
  } finally {
    runInProgress = false;
    outputSocket?.close();
    runTestsButton.textContent = "Run selected tests";
    updateRunControls();
  }
}

generateRobotArgumentsButton.addEventListener("click", prepareRobotCommand);
runTestsButton.addEventListener("click", runSelectedTests);
undefinedVariablesList.addEventListener("input", clearGeneratedRobotArguments);
undefinedVariablesList.addEventListener("change", clearGeneratedRobotArguments);
reportNameInput.addEventListener("input", clearGeneratedRobotArguments);
testTableBody.addEventListener("change", (event) => {
  if (event.target instanceof Element && event.target.matches(".selection-checkbox")) {
    clearGeneratedRobotArguments();
    updateRunControls();
  }
});
copyRobotCommandButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(robotCommandPreview.textContent);
    undefinedVariablesResult.textContent = "Robot Framework command copied.";
  } catch (error) {
    undefinedVariablesResult.textContent =
      "Could not copy automatically. Select and copy the command above.";
  }
});

variablesList.addEventListener("focusin", (event) => {
  if (!highlightedVariableFields.has(event.target)) {
    highlightedVariableFields.forEach((field) => {
      field.classList.remove("is-reference-target");
    });
    highlightedVariableFields.clear();
  }
});

async function loadVariables(directoryName) {
  variablesList.replaceChildren();
  variablesStatus.textContent = "Loading variables…";
  variablesList.append(variablesStatus);
  saveVariablesButton.disabled = true;
  undefinedVariablesList.replaceChildren();
  undefinedVariablesStatus.textContent = "Loading undefined variables…";
  undefinedVariablesList.append(undefinedVariablesStatus);
  updateRunControls();
  clearGeneratedRobotArguments();

  const response = await fetch(
    `/api/directories/${encodeURIComponent(directoryName)}/variables`,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) {
    throw new Error(`Could not load common.resource (${response.status}).`);
  }

  const variables = await response.json();
  if (
    !Array.isArray(variables)
    || !variables.every((variable) => (
      typeof variable.name === "string"
      && ["scalar", "dictionary", "list", "set", "tuple"].includes(variable.kind)
      && typeof variable.expression === "boolean"
      && Array.isArray(variable.composed_from)
      && variable.composed_from.every((name) => typeof name === "string")
      && Array.isArray(variable.fields)
      && variable.fields.every((field) => (
        typeof field.value === "string"
        && ["string", "integer", "float", "boolean", "none"].includes(field.value_type)
        && typeof field.expression === "boolean"
        && (field.key === null || typeof field.key === "string")
      ))
    ))
  ) {
    throw new Error("The server returned invalid variable data.");
  }
  renderVariables(variables);
}

async function saveVariables() {
  if (!currentDirectory) {
    return;
  }

  saveVariablesButton.disabled = true;
  saveVariablesButton.textContent = "Saving…";
  variablesStatus.textContent = "Saving changes…";

  try {
    const variables = Array.from(
      variablesList.querySelectorAll('.variable-row[data-composed="false"]'),
      (row) => ({
        name: row.dataset.variableName,
        kind: row.dataset.kind,
        expression: row.dataset.expression === "true",
        fields: Array.from(row.querySelectorAll(".variable-field"), (input) => {
          const keyInput = input.closest(".variable-field-row").querySelector(".variable-key");
          return {
            key: keyInput ? keyInput.value : null,
            value: input.value,
            value_type: input.dataset.valueType,
            expression: input.dataset.expression === "true",
          };
        }),
      }),
    );
    const response = await fetch(
      `/api/directories/${encodeURIComponent(currentDirectory)}/variables`,
      {
        method: "PUT",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ variables }),
      },
    );
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || `Save failed (${response.status}).`);
    }
    renderVariables(result);
    variablesStatus.textContent = "Variables saved to common.resource.";
    variablesList.prepend(variablesStatus);
  } catch (error) {
    variablesStatus.textContent = error instanceof Error
      ? error.message
      : "Could not save variables.";
    variablesList.prepend(variablesStatus);
    saveVariablesButton.disabled = false;
  } finally {
    saveVariablesButton.textContent = "Save variables";
  }
}

async function loadRobotFiles(directoryName) {
  currentDirectory = directoryName;
  runDataReady = false;
  updateRunControls();
  runStatus.textContent = "";
  runArtifactLinks.hidden = true;
  updateRunOutput("Robot Framework output will appear here when a run starts.");
  clearGeneratedRobotArguments();
  directoryGrid.hidden = true;
  fileBrowser.hidden = false;
  directoriesTitle.textContent = "Section contents";
  sectionTitle.textContent = directoryName;
  fileBrowserSummary.textContent = "Loading Robot files…";
  tableMessage.textContent = "";
  testTableBody.replaceChildren();
  directoryCount.textContent = "";
  variablesList.replaceChildren();
  variablesStatus.textContent = "Loading variables…";
  variablesList.append(variablesStatus);
  saveVariablesButton.disabled = true;
  updateRunControls();
  Object.values(tagLists).forEach((list) => list.replaceChildren());
  tagStatus.textContent = "Loading test case tags…";
  tagBoard.setAttribute("aria-busy", "true");

  try {
    const response = await fetch(
      `/api/directories/${encodeURIComponent(directoryName)}/files`,
      { headers: { Accept: "application/json" } },
    );
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }

    const files = await response.json();
    if (
      !Array.isArray(files)
      || !files.every((file) => (
        typeof file.name === "string"
        && typeof file.display_name === "string"
        && Array.isArray(file.test_cases)
        && file.test_cases.every((testCase) => (
          typeof testCase.name === "string"
          && typeof testCase.documentation === "string"
          && Array.isArray(testCase.tags)
          && testCase.tags.every((tag) => typeof tag === "string")
        ))
      ))
    ) {
      throw new Error("The server returned invalid Robot file data.");
    }
    renderRobotFiles(files);
    renderTags(files);
  } catch (error) {
    fileBrowserSummary.textContent = "Could not load section contents.";
    tableMessage.textContent = error instanceof Error ? error.message : "An unexpected error occurred.";
    tagStatus.textContent = "Could not load test case tags.";
    tagBoard.setAttribute("aria-busy", "false");
  }

  let variableDataLoaded = true;
  try {
    await loadVariables(directoryName);
  } catch (error) {
    variableDataLoaded = false;
    variablesStatus.textContent = error instanceof Error
      ? error.message
      : "Could not load common.resource.";
    variablesList.replaceChildren(variablesStatus);
  }

  try {
    await loadUndefinedVariables(directoryName);
  } catch (error) {
    variableDataLoaded = false;
    undefinedVariablesStatus.textContent = error instanceof Error
      ? error.message
      : "Could not load undefined variables.";
    undefinedVariablesList.replaceChildren(undefinedVariablesStatus);
  }
  runDataReady = variableDataLoaded;
  updateRunControls();
}

function showDirectories() {
  currentDirectory = null;
  fileBrowser.hidden = true;
  directoryGrid.hidden = false;
  directoriesTitle.textContent = "Browse sections";
  directoryCount.textContent = `${directoryGrid.querySelectorAll(".directory-card").length} sections`;
  history.replaceState(null, "", window.location.pathname);
}

async function loadDirectories() {
  refreshButton.disabled = true;
  refreshButton.classList.add("is-loading");
  refreshFeedback.textContent = "Updating directory list…";
  directoryGrid.setAttribute("aria-busy", "true");

  try {
    const response = await fetch("/api/directories", { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }

    const directories = await response.json();
    if (!Array.isArray(directories) || !directories.every((name) => typeof name === "string")) {
      throw new Error("The server returned an invalid directory list.");
    }

    renderDirectories(directories);
    refreshFeedback.textContent = `Updated at ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    directoryCount.textContent = "Unavailable";
    directoryGrid.replaceChildren();
    const errorState = document.createElement("div");
    errorState.className = "empty-state error-state";
    errorState.innerHTML = "<strong>Could not load directories</strong><span>Check that the server is running, then try again.</span>";
    directoryGrid.append(errorState);
    refreshFeedback.textContent = error instanceof Error ? error.message : "An unexpected error occurred.";
  } finally {
    directoryGrid.setAttribute("aria-busy", "false");
    refreshButton.disabled = false;
    refreshButton.classList.remove("is-loading");
  }
}

refreshButton.addEventListener("click", loadDirectories);
backButton.addEventListener("click", showDirectories);
saveVariablesButton.addEventListener("click", saveVariables);
document.querySelectorAll(".tag-zone").forEach((zone) => {
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    zone.classList.add("is-drop-target");
  });
  zone.addEventListener("dragleave", (event) => {
    if (!zone.contains(event.relatedTarget)) {
      zone.classList.remove("is-drop-target");
    }
  });
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-drop-target");
    const tag = event.dataTransfer.getData("text/plain");
    const chip = Array.from(document.querySelectorAll(".tag-chip"))
      .find((item) => item.dataset.tag === tag);
    if (chip) {
      moveTag(chip, zone.dataset.tagZone);
    }
  });
});
loadDirectories();