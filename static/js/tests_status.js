const processList = document.querySelector("#process-list");
const processCount = document.querySelector("#process-count");
const processMessage = document.querySelector("#process-message");
const refreshButton = document.querySelector("#refresh-processes");
const stopClearButton = document.querySelector("#stop-clear-all");
const cards = new Map();
const maxDisplayedOutput = 262144;

function statusLabel(status) {
  return status.replaceAll("_", " ");
}

function renderConsoleText(element, text) {
  const fragment = document.createDocumentFragment();
  const statusPattern = /\|\s*(PASS|SKIP|FAIL)\s*\|/g;
  let previousEnd = 0;
  let match;
  while ((match = statusPattern.exec(text)) !== null) {
    fragment.append(document.createTextNode(text.slice(previousEnd, match.index)));
    const status = document.createElement("span");
    status.className = `run-output-status is-${match[1].toLowerCase()}`;
    status.textContent = match[0];
    fragment.append(status);
    previousEnd = statusPattern.lastIndex;
  }
  fragment.append(document.createTextNode(text.slice(previousEnd)));
  element.replaceChildren(fragment);
}

function createProcessCard(run) {
  const card = document.createElement("article");
  card.className = "management-card";
  card.dataset.runId = run.id;

  const header = document.createElement("div");
  header.className = "management-card-header";
  const title = document.createElement("h2");
  title.textContent = run.report_name;
  const state = document.createElement("span");
  state.className = "process-state";
  header.append(title, state);

  const meta = document.createElement("div");
  meta.className = "management-card-meta";
  const id = document.createElement("span");
  id.textContent = `Run ID: ${run.id}`;
  const pid = document.createElement("span");
  const created = document.createElement("span");
  meta.append(id, pid, created);

  const progress = document.createElement("div");
  progress.className = "process-progress";
  const progressBar = document.createElement("progress");
  progressBar.max = 100;
  const progressLabel = document.createElement("span");
  progress.append(progressBar, progressLabel);

  const consoleDetails = document.createElement("details");
  consoleDetails.className = "process-console";
  const summary = document.createElement("summary");
  summary.textContent = "Show console output";
  const output = document.createElement("pre");
  output.textContent = "Open to load the saved console output.";
  consoleDetails.append(summary, output);
  consoleDetails.addEventListener("toggle", () => {
    if (consoleDetails.open && !consoleDetails.dataset.loaded) {
      consoleDetails.dataset.loaded = "true";
      loadRunOutput(run.id, output, state, progressBar, progressLabel);
    }
  });

  const actions = document.createElement("div");
  actions.className = "management-card-actions";
  const killButton = document.createElement("button");
  killButton.className = "management-button is-danger";
  killButton.type = "button";
  killButton.textContent = "Kill process";
  killButton.addEventListener("click", () => killRun(run.id));
  const deleteButton = document.createElement("button");
  deleteButton.className = "management-button";
  deleteButton.type = "button";
  deleteButton.textContent = "Delete process information";
  deleteButton.addEventListener("click", () => deleteRun(run.id));
  actions.append(killButton, deleteButton);

  card.append(header, meta, progress, consoleDetails, actions);
  const refs = { title, state, pid, created, progressBar, progressLabel, output, consoleDetails, killButton, deleteButton };
  cards.set(run.id, { card, refs });
  updateProcessCard(run);
  return card;
}

function updateProcessCard(run) {
  let entry = cards.get(run.id);
  if (!entry) {
    processList.prepend(createProcessCard(run));
    entry = cards.get(run.id);
  }
  const { refs } = entry;
  refs.title.textContent = run.report_name;
  refs.state.textContent = statusLabel(run.status);
  refs.state.className = `process-state is-${run.status}`;
  refs.pid.textContent = run.process_id ? `OS process ID: ${run.process_id}` : "OS process ID: pending";
  refs.created.textContent = `Started: ${run.started_at || run.created_at}`;
  const total = Number(run.progress_total || 0);
  const current = Number(run.progress_current || 0);
  const percent = total > 0 ? Math.min(100, Math.round(current * 100 / total)) : 0;
  refs.progressBar.value = percent;
  refs.progressLabel.textContent = `${percent}% (${current}/${total})`;
  refs.killButton.hidden = !["queued", "running"].includes(run.status);
  refs.deleteButton.hidden = ["queued", "running"].includes(run.status);
  refs.deleteButton.disabled = ["queued", "running"].includes(run.status);
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  if (response.status === 204) return null;
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || `Request failed (${response.status}).`);
  return result;
}

async function loadRunOutput(runId, output, state, progressBar, progressLabel) {
  try {
    const result = await apiRequest(`/api/runs/${encodeURIComponent(runId)}`);
    let consoleText = result.console_output || "No console output was recorded.";
    if (result.console_output_truncated) {
      consoleText = `[Showing the most recent output. Full output remains stored in the run database.]\n${consoleText}`;
    }
    renderConsoleText(output, consoleText);
    updateLiveProgress(result, state, progressBar, progressLabel);
    if (["queued", "running"].includes(result.status)) connectRunOutput(runId, output, state, progressBar, progressLabel);
  } catch (error) {
    output.textContent = error instanceof Error ? error.message : "Could not load console output.";
  }
}

function updateLiveProgress(run, state, progressBar, progressLabel) {
  if (run.status) {
    state.textContent = statusLabel(run.status);
    state.className = `process-state is-${run.status}`;
  }
  const current = Number(run.progress_current || 0);
  const total = Number(run.progress_total || 0);
  const percent = total > 0 ? Math.min(100, Math.round(current * 100 / total)) : 0;
  progressBar.value = percent;
  progressLabel.textContent = `${percent}% (${current}/${total})`;
}

function connectRunOutput(runId, output, state, progressBar, progressLabel) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws/runs/${encodeURIComponent(runId)}`);
  let outputText = output.textContent || "";
  socket.addEventListener("message", (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    if (message.type === "snapshot") {
      outputText = message.text || "";
      updateLiveProgress(message, state, progressBar, progressLabel);
    } else if (message.type === "output") {
      outputText += message.text || "";
      if (outputText.length > maxDisplayedOutput) {
        outputText = outputText.slice(-maxDisplayedOutput);
      }
    } else if (message.type === "progress" || message.type === "status") {
      updateLiveProgress(message, state, progressBar, progressLabel);
    }
    if (message.type === "snapshot" || message.type === "output") {
      renderConsoleText(output, outputText);
      output.scrollTop = output.scrollHeight;
    }
    if (message.type === "status" && !["queued", "running"].includes(message.status)) socket.close();
  });
}

async function refreshProcesses() {
  refreshButton.disabled = true;
  try {
    const runs = await apiRequest("/api/runs");
    processCount.textContent = `${runs.length} ${runs.length === 1 ? "process record" : "process records"}`;
    stopClearButton.disabled = runs.length === 0;
    const returnedIds = new Set(runs.map((run) => run.id));
    for (const run of runs) updateProcessCard(run);
    for (const [runId, entry] of cards) {
      if (!returnedIds.has(runId)) {
        entry.card.remove();
        cards.delete(runId);
      }
    }
    if (runs.length === 0) {
      processList.innerHTML = '<div class="management-empty">No Robot process history yet. Start a run from the Test browser.</div>';
    }
  } catch (error) {
    processMessage.textContent = error instanceof Error ? error.message : "Could not load process history.";
  } finally {
    refreshButton.disabled = false;
  }
}

async function killRun(runId) {
  processMessage.textContent = "Stopping Robot Framework…";
  try {
    await apiRequest(`/api/runs/${encodeURIComponent(runId)}/kill`, { method: "POST" });
    processMessage.textContent = "Process stopped. Its reports remain available on the Reports page.";
    await refreshProcesses();
  } catch (error) {
    processMessage.textContent = error instanceof Error ? error.message : "Could not stop the process.";
  }
}

async function deleteRun(runId) {
  if (!window.confirm("Delete this process record and its saved console history? Report files will be kept.")) return;
  try {
    await apiRequest(`/api/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
    processMessage.textContent = "Process information deleted. Report files were kept.";
    await refreshProcesses();
  } catch (error) {
    processMessage.textContent = error instanceof Error ? error.message : "Could not delete process information.";
  }
}

async function killAndClearAll() {
  if (!window.confirm("Stop every running Robot process and delete all process records? Reports will be kept.")) return;
  stopClearButton.disabled = true;
  try {
    const result = await apiRequest("/api/runs/stop-all-and-clear", { method: "POST" });
    processMessage.textContent = `Stopped active runs and removed ${result.removed} process records. Reports were kept.`;
    await refreshProcesses();
  } catch (error) {
    processMessage.textContent = error instanceof Error ? error.message : "Could not clear process history.";
  } finally {
    stopClearButton.disabled = false;
  }
}

refreshButton.addEventListener("click", refreshProcesses);
stopClearButton.addEventListener("click", killAndClearAll);
refreshProcesses();
window.setInterval(refreshProcesses, 2000);
