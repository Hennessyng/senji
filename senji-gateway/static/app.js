const root = document.documentElement;
const themeToggle = document.getElementById("theme-toggle");
const errorBanner = document.getElementById("error-banner");
const errorMessage = document.getElementById("error-message");
const resultsSection = document.getElementById("results-area");
const resultsHeading = document.getElementById("results-heading");
const resultsMeta = document.getElementById("result-metadata");
const markdownOutput = document.getElementById("markdown-output");
const copyButton = document.getElementById("copy-btn");
const downloadButton = document.getElementById("download-btn");
const urlInput = document.getElementById("url-input");
const urlConvertButton = document.getElementById("url-convert-btn");
const urlIngestBtn = document.getElementById('url-ingest-btn');
const uploadIngestBtn = document.getElementById('upload-ingest-btn');
const jobStatusSection = document.getElementById('job-status');
const jobStatusText = document.getElementById('job-status-text');
const jobStatusIcon = document.getElementById('job-status-icon');
const jobIdDisplay = document.getElementById('job-id-display');

const tabs = [
  document.getElementById("url-tab"),
  document.getElementById("upload-tab"),
  document.getElementById("paste-tab"),
];

const panels = [
  document.getElementById("url-panel"),
  document.getElementById("upload-panel"),
  document.getElementById("paste-panel"),
];

const THEME_KEY = "senji_theme";
const TOKEN_KEY = "senji_token";

let currentMarkdown = "";
let currentTitle = "markdown-result";
let authToken = readToken();

if (!authToken) {
  const promptedToken = window.prompt("Enter your Senji bearer token:");
  if (promptedToken && promptedToken.trim()) {
    authToken = promptedToken.trim();
    localStorage.setItem(TOKEN_KEY, authToken);
  }
} else {
  localStorage.setItem(TOKEN_KEY, authToken);
}

initializeTheme();
initializeTabs();
initializeResultsActions();
urlConvertButton.addEventListener("click", handleUrlConvert);
urlIngestBtn.addEventListener('click', handleUrlIngest);
uploadIngestBtn.addEventListener('click', handleFileIngest);
checkUrlJobParam();

function initializeTheme() {
  const storedTheme = localStorage.getItem(THEME_KEY);
  const theme = storedTheme === "dark" ? "dark" : "light";
  applyTheme(theme);

  themeToggle.addEventListener("click", () => {
    const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
  });
}

function applyTheme(theme) {
  root.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
  themeToggle.textContent = theme === "dark" ? "☀️" : "🌙";
  themeToggle.setAttribute("aria-pressed", String(theme === "dark"));
  themeToggle.setAttribute(
    "aria-label",
    theme === "dark" ? "Switch to light mode" : "Switch to dark mode",
  );
}

function initializeTabs() {
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => setActiveTab(tab.id));
  });
}

function setActiveTab(activeId) {
  tabs.forEach((tab, index) => {
    const isActive = tab.id === activeId;
    tab.setAttribute("aria-selected", String(isActive));
    panels[index].style.display = isActive ? "block" : "none";
  });
}

function initializeResultsActions() {
  copyButton.addEventListener("click", async () => {
    if (!currentMarkdown) {
      return;
    }

    try {
      await navigator.clipboard.writeText(currentMarkdown);
      hideError();
    } catch (error) {
      showError(readErrorMessage(error, "Clipboard write failed."));
    }
  });

  downloadButton.addEventListener("click", () => {
    if (!currentMarkdown) {
      return;
    }

    const blob = new Blob([currentMarkdown], { type: "text/markdown;charset=utf-8" });
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `${slugify(currentTitle || "senji-export")}.md`;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
  });
}

async function handleUrlConvert() {
  hideError();

  const url = urlInput.value.trim();
  if (!url) {
    showError("Enter a URL before converting.");
    urlInput.focus();
    return;
  }

  const token = ensureToken();
  if (!token) {
    showError("Bearer token required to call Senji API.");
    return;
  }

  setLoadingState(true);

  try {
    const response = await fetch("/api/convert/url", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ url }),
    });

    const payload = await parseJson(response);
    if (!response.ok) {
      throw new Error(getApiErrorMessage(payload, response.status));
    }

    renderResults(payload);
  } catch (error) {
    showError(readErrorMessage(error, "Conversion failed."));
  } finally {
    setLoadingState(false);
  }
}

function renderResults(payload) {
  currentMarkdown = typeof payload.markdown === "string" ? payload.markdown : "";
  currentTitle = typeof payload.title === "string" && payload.title.trim() ? payload.title.trim() : "markdown-result";

  markdownOutput.textContent = currentMarkdown;
  resultsHeading.textContent = currentTitle;

  const mediaCount = Array.isArray(payload.media) ? payload.media.length : 0;
  const source = payload.source || urlInput.value.trim();
  resultsMeta.textContent = `Source: ${source} · Media items: ${mediaCount}`;
  resultsSection.style.display = "block";
}

function setLoadingState(isLoading) {
  urlConvertButton.disabled = isLoading;
  urlInput.disabled = isLoading;
  urlConvertButton.classList.toggle("loading", isLoading);
  urlConvertButton.textContent = isLoading ? "Converting" : "Convert";
}

async function handleUrlIngest() {
  hideError();
  const url = urlInput.value.trim();
  if (!url) { showError('Enter a URL before saving.'); urlInput.focus(); return; }
  const token = ensureToken();
  if (!token) { showError('Bearer token required.'); return; }
  urlIngestBtn.disabled = true;
  try {
    const response = await fetch('/api/ingest/url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ url }),
    });
    const payload = await parseJson(response);
    if (!response.ok) throw new Error(getApiErrorMessage(payload, response.status));
    startJobPolling(payload.job_id, token);
  } catch (error) {
    showError(readErrorMessage(error, 'Ingest failed.'));
  } finally {
    urlIngestBtn.disabled = false;
  }
}

async function handleFileIngest() {
  if (!selectedFile) return;
  const token = ensureToken();
  if (!token) { showError('Bearer token required.'); return; }
  uploadIngestBtn.disabled = true;
  try {
    const formData = new FormData();
    formData.append('file', selectedFile);
    const response = await fetch('/api/ingest/file', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const payload = await parseJson(response);
    if (!response.ok) throw new Error(getApiErrorMessage(payload, response.status));
    startJobPolling(payload.job_id, token);
  } catch (error) {
    showError(readErrorMessage(error, 'Ingest failed.'));
  } finally {
    uploadIngestBtn.disabled = false;
  }
}

function startJobPolling(jobId, token) {
  jobIdDisplay.textContent = jobId;
  showJobStatus('queued');
  let attempts = 0;
  const MAX = 60;
  const id = setInterval(async () => {
    if (++attempts > MAX) { clearInterval(id); showJobStatus('timeout'); return; }
    try {
      const r = await fetch(`/api/ingest/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const job = await parseJson(r);
      showJobStatus(job.status, job);
      if (job.status === 'complete' || job.status === 'failed') clearInterval(id);
    } catch { }
  }, 2000);
}

function checkUrlJobParam() {
  const params = new URLSearchParams(window.location.search);
  const jobId = params.get('job');
  if (!jobId) return;
  const token = ensureToken();
  if (!token) return;
  window.history.replaceState({}, '', window.location.pathname);
  startJobPolling(jobId, token);
}

function showJobStatus(status, job = null) {
  const icons = { queued: '⏳', processing: '⚙️', complete: '✅', failed: '❌', timeout: '⚠️' };
  const texts = {
    queued: 'Queued — waiting to process...',
    processing: 'Processing — converting and generating wiki...',
    complete: `Saved to vault${job?.files_written?.length ? ' — ' + job.files_written.join(', ') : ''}`,
    failed: `Failed${job?.error_detail ? ': ' + job.error_detail : ''}`,
    timeout: 'Timed out — check server logs',
  };
  jobStatusIcon.textContent = icons[status] ?? '⏳';
  jobStatusText.textContent = texts[status] ?? status;
  jobStatusSection.dataset.status = status;
  jobStatusSection.style.display = 'block';
}

function showError(message) {
  errorMessage.textContent = message;
  errorBanner.style.display = "block";
}

function hideError() {
  errorBanner.style.display = "none";
  errorMessage.textContent = "";
}

function ensureToken() {
  if (authToken) {
    return authToken;
  }

  const promptedToken = window.prompt("Enter your Senji bearer token:");
  if (!promptedToken || !promptedToken.trim()) {
    return "";
  }

  authToken = promptedToken.trim();
  localStorage.setItem(TOKEN_KEY, authToken);
  return authToken;
}

function readToken() {
  const storedToken = localStorage.getItem(TOKEN_KEY);
  if (storedToken && storedToken.trim()) {
    return storedToken.trim();
  }

  const metaToken = document.querySelector('meta[name="senji-token"]')?.content;
  if (metaToken && metaToken.trim()) {
    return metaToken.trim();
  }

  const tokenCookie = document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith("SENJI_TOKEN=") || value.startsWith("senji_token="));

  if (!tokenCookie) {
    return "";
  }

  const [, tokenValue = ""] = tokenCookie.split("=");
  return decodeURIComponent(tokenValue).trim();
}

async function parseJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function getApiErrorMessage(payload, status) {
  const pieces = [];

  if (payload && typeof payload.error === "string" && payload.error.trim()) {
    pieces.push(payload.error.trim());
  }

  if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
    pieces.push(payload.detail.trim());
  }

  if (!pieces.length) {
    pieces.push(`Request failed with status ${status}`);
  }

  return pieces.join(" — ");
}

function readErrorMessage(error, fallbackMessage) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallbackMessage;
}

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "senji-export";
}

// --- Upload Tab ---
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const fileInfo = document.getElementById("file-info");
const fileNameDisplay = document.getElementById("file-name");
const fileSizeDisplay = document.getElementById("file-size");
const fileConvertBtn = document.getElementById("upload-convert-btn");

const ALLOWED_EXTENSIONS = new Set([".pdf", ".docx", ".pptx"]);
const MAX_FILE_BYTES = 50 * 1024 * 1024;
let selectedFile = null;

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") fileInput.click();
});
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) setSelectedFile(file);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) setSelectedFile(fileInput.files[0]);
});
fileConvertBtn.addEventListener("click", handleFileConvert);

function setSelectedFile(file) {
  const ext = "." + file.name.split(".").pop().toLowerCase();
  if (!ALLOWED_EXTENSIONS.has(ext)) {
    showError("Unsupported format. Please upload a PDF, DOCX, or PPTX file.");
    return;
  }
  if (file.size > MAX_FILE_BYTES) {
    showError("File exceeds the 50 MB limit. Please upload a smaller file.");
    return;
  }
  selectedFile = file;
  fileNameDisplay.textContent = file.name;
  fileSizeDisplay.textContent = `${(file.size / 1024 / 1024).toFixed(1)} MB`;
  fileInfo.style.display = "block";
  fileConvertBtn.style.display = "block";
  fileConvertBtn.disabled = false;
  uploadIngestBtn.style.display = 'block';
  uploadIngestBtn.disabled = false;
  hideError();
}

async function handleFileConvert() {
  if (!selectedFile) return;
  const token = ensureToken();
  if (!token) {
    showError("Bearer token required to call Senji API.");
    return;
  }
  setLoadingState(true);
  try {
    const formData = new FormData();
    formData.append("file", selectedFile);
    const response = await fetch("/api/convert/file", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const payload = await parseJson(response);
    if (!response.ok) throw new Error(getApiErrorMessage(payload, response.status));
    renderResults(payload);
  } catch (error) {
    showError(readErrorMessage(error, "Conversion failed."));
  } finally {
    setLoadingState(false);
  }
}

// --- Paste Tab ---
const pasteInput = document.getElementById("paste-input");
const pasteConvertBtn = document.getElementById("paste-convert-btn");

pasteConvertBtn.addEventListener("click", handlePasteConvert);

async function handlePasteConvert() {
  hideError();
  const html = pasteInput.value.trim();
  if (!html) {
    showError("Paste some HTML before converting.");
    pasteInput.focus();
    return;
  }
  const token = ensureToken();
  if (!token) {
    showError("Bearer token required to call Senji API.");
    return;
  }
  setLoadingState(true);
  try {
    const response = await fetch("/api/convert/html", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ html }),
    });
    const payload = await parseJson(response);
    if (!response.ok) throw new Error(getApiErrorMessage(payload, response.status));
    renderResults(payload);
  } catch (error) {
    showError(readErrorMessage(error, "Conversion failed."));
  } finally {
    setLoadingState(false);
  }
}

// --- Clear Button ---
const resultsArea = document.getElementById("results-area");
const resultsContent = document.getElementById("results-content");
const clearButton = document.getElementById("clear-btn");

clearButton.addEventListener("click", clearAll);

function clearAll() {
  urlInput.value = "";
  pasteInput.value = "";
  selectedFile = null;
  fileNameDisplay.textContent = "";
  fileSizeDisplay.textContent = "";
  fileInfo.style.display = "none";
  fileConvertBtn.style.display = "none";
  fileConvertBtn.disabled = true;
  uploadIngestBtn.style.display = 'none';
  jobStatusSection.style.display = 'none';
  resultsArea.style.display = "none";
  markdownOutput.textContent = "";
  currentMarkdown = "";
  currentTitle = "markdown-result";
  hideError();
}

// --- Keyboard shortcut: Cmd/Ctrl+Enter to submit active tab ---
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (!(e.metaKey || e.ctrlKey)) return;
  const activeTab = document.querySelector('.tab-button[aria-selected="true"]');
  if (!activeTab) return;
  if (activeTab.id === "url-tab") handleUrlConvert();
  else if (activeTab.id === "paste-tab") pasteConvertBtn.click();
  else if (activeTab.id === "upload-tab" && selectedFile) fileConvertBtn.click();
});

// --- Focus management: auto-focus on tab switch ---
document.querySelectorAll(".tab-button").forEach((tab) => {
  tab.addEventListener("click", () => {
    if (tab.id === "url-tab") setTimeout(() => urlInput.focus(), 10);
    else if (tab.id === "paste-tab") setTimeout(() => pasteInput.focus(), 10);
  });
});
