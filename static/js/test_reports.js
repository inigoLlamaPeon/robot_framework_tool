const reportList = document.querySelector("#report-list");
const reportCount = document.querySelector("#report-count");
const reportMessage = document.querySelector("#report-message");
const refreshButton = document.querySelector("#refresh-reports");
const mergeButton = document.querySelector("#merge-reports");
const downloadButton = document.querySelector("#download-reports");
const mergeNameInput = document.querySelector("#merge-name");
let currentReports = [];

function selectedReportNames() {
  return Array.from(
    reportList.querySelectorAll(".report-select:checked"),
    (checkbox) => checkbox.dataset.reportName,
  );
}

function updateSelectionControls() {
  const names = selectedReportNames();
  downloadButton.disabled = names.length === 0;
  mergeButton.disabled = names.length < 2 || !mergeNameInput.value.trim();
}

function createReportCard(report) {
  const card = document.createElement("article");
  card.className = "management-card";

  const header = document.createElement("div");
  header.className = "management-card-header";
  const select = document.createElement("input");
  select.className = "report-select";
  select.type = "checkbox";
  select.dataset.reportName = report.name;
  select.setAttribute("aria-label", `Select report ${report.name}`);
  select.addEventListener("change", updateSelectionControls);
  const title = document.createElement("h2");
  title.textContent = report.name;
  header.append(select, title);

  const meta = document.createElement("div");
  meta.className = "management-card-meta";
  const created = document.createElement("span");
  created.textContent = `Updated: ${new Date(report.created_at).toLocaleString()}`;
  meta.append(created);

  const links = document.createElement("div");
  links.className = "report-links";
  [
    [report.report_url, "View report"],
    [report.log_url, "View log"],
    [report.output_url, "Open output.xml"],
  ].forEach(([url, text]) => {
    if (!url) return;
    const link = document.createElement("a");
    link.className = "report-link";
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = text;
    links.append(link);
  });

  const actions = document.createElement("div");
  actions.className = "management-card-actions";
  const deleteButton = document.createElement("button");
  deleteButton.className = "management-button is-danger";
  deleteButton.type = "button";
  deleteButton.textContent = "Delete report";
  deleteButton.addEventListener("click", () => deleteReport(report.name));
  actions.append(deleteButton);
  card.append(header, meta, links, actions);
  return card;
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

async function loadReports() {
  refreshButton.disabled = true;
  try {
    currentReports = await apiRequest("/api/reports");
    reportList.replaceChildren();
    reportCount.textContent = `${currentReports.length} ${currentReports.length === 1 ? "report" : "reports"}`;
    if (!currentReports.length) {
      const empty = document.createElement("div");
      empty.className = "management-empty";
      empty.textContent = "No Robot Framework reports found. Run selected tests to create one.";
      reportList.append(empty);
    } else {
      currentReports.forEach((report) => reportList.append(createReportCard(report)));
    }
    updateSelectionControls();
  } catch (error) {
    reportMessage.textContent = error instanceof Error ? error.message : "Could not load reports.";
  } finally {
    refreshButton.disabled = false;
  }
}

async function deleteReport(reportName) {
  if (!window.confirm(`Delete the report, log, and output.xml for "${reportName}"?`)) return;
  try {
    await apiRequest(`/api/reports/${encodeURIComponent(reportName)}`, { method: "DELETE" });
    reportMessage.textContent = `${reportName} and its report files were deleted. Process history is unchanged.`;
    await loadReports();
  } catch (error) {
    reportMessage.textContent = error instanceof Error ? error.message : "Could not delete report.";
  }
}

async function mergeReports() {
  const names = selectedReportNames();
  const reportName = mergeNameInput.value.trim();
  if (names.length < 2 || !reportName) return;
  mergeButton.disabled = true;
  reportMessage.textContent = "Merging selected Robot output files…";
  try {
    const report = await apiRequest("/api/reports/merge", {
      method: "POST",
      body: JSON.stringify({ report_names: names, report_name: reportName }),
    });
    reportMessage.textContent = `Merged report created: ${report.name}. Original reports were kept.`;
    mergeNameInput.value = "";
    await loadReports();
  } catch (error) {
    reportMessage.textContent = error instanceof Error ? error.message : "Could not merge reports.";
  } finally {
    updateSelectionControls();
  }
}

async function downloadReports() {
  const names = selectedReportNames();
  if (!names.length) return;
  downloadButton.disabled = true;
  reportMessage.textContent = "Preparing ZIP download…";
  try {
    const response = await fetch("/api/reports/archive", {
      method: "POST",
      headers: { Accept: "application/zip", "Content-Type": "application/json" },
      body: JSON.stringify({ report_names: names }),
    });
    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.detail || `Request failed (${response.status}).`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const filename = disposition.match(/filename="([^"]+)"/)?.[1] || "robot-reports.zip";
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(objectUrl);
    reportMessage.textContent = `Downloaded ${names.length} report${names.length === 1 ? "" : "s"} in ${filename}.`;
  } catch (error) {
    reportMessage.textContent = error instanceof Error ? error.message : "Could not download reports.";
  } finally {
    updateSelectionControls();
  }
}

refreshButton.addEventListener("click", loadReports);
mergeButton.addEventListener("click", mergeReports);
downloadButton.addEventListener("click", downloadReports);
mergeNameInput.addEventListener("input", updateSelectionControls);
loadReports();
