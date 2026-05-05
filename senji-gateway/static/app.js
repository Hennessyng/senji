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

initializeTheme();
initializeTabs();
initializeResultsActions();
initializeTokenModal();
initializeBookmarklet();
urlConvertButton.addEventListener("click", handleUrlConvert);
urlIngestBtn.addEventListener('click', handleUrlIngest);
uploadIngestBtn.addEventListener('click', handleFileIngest);
checkUrlJobParam();

// --- Token Modal ---

let _tokenModalResolve = null;

function initializeTokenModal() {
  const submitBtn = document.getElementById('token-modal-submit');
  const input = document.getElementById('token-modal-input');

  function submitToken() {
    const val = input.value.trim();
    if (!val) return;
    authToken = val;
    localStorage.setItem(TOKEN_KEY, authToken);
    hideTokenModal();
    if (_tokenModalResolve) {
      _tokenModalResolve(authToken);
      _tokenModalResolve = null;
    }
  }

  submitBtn.addEventListener('click', submitToken);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitToken(); });
}

function showTokenModal() {
  return new Promise((resolve) => {
    _tokenModalResolve = resolve;
    const modal = document.getElementById('token-modal');
    const input = document.getElementById('token-modal-input');
    modal.style.display = 'flex';
    input.value = '';
    setTimeout(() => input.focus(), 50);
  });
}

function hideTokenModal() {
  document.getElementById('token-modal').style.display = 'none';
}

// --- Bookmarklet ---

function initializeBookmarklet() {
  const url = `javascript:void(location.href='${window.location.origin}/?clipurl='+encodeURIComponent(location.href))`;
  const display = document.getElementById('bookmarklet-url');
  const copyBtn = document.getElementById('copy-bookmarklet-btn');
  if (display) display.textContent = url;
  if (copyBtn) copyBtn.addEventListener('click', () => copyToClipboard(url));
}

// --- Theme ---

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

// --- Tabs ---

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

// --- Results Actions ---

function initializeResultsActions() {
  copyButton.addEventListener("click", async () => {
    if (!currentMarkdown) return;
    try {
      await copyToClipboard(currentMarkdown);
      hideError();
    } catch (error) {
      showError(readErrorMessage(error, "Clipboard write failed."));
    }
  });

  downloadButton.addEventListener("click", () => {
    if (!currentMarkdown) return;
    downloadMarkdown(currentMarkdown, currentTitle);
  });
}

async function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (_) {}
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none';
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

function downloadMarkdown(markdown, title) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  if (isIOS) {
    window.open(objectUrl, '_blank');
    setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
  } else {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `${slugify(title || "senji-export")}.md`;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
  }
}

// --- URL Convert ---

async function handleUrlConvert() {
  hideError();

  const url = urlInput.value.trim();
  if (!url) {
    showError("Enter a URL before converting.");
    urlInput.focus();
    return;
  }

  const token = await ensureToken();
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

// --- URL Ingest ---

async function handleUrlIngest() {
  hideError();
  const url = urlInput.value.trim();
  if (!url) { showError('Enter a URL before saving.'); urlInput.focus(); return; }
  const token = await ensureToken();
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

// --- File Ingest ---

async function handleFileIngest() {
  if (!selectedFile) return;
  const token = await ensureToken();
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

// --- Job Polling ---

function startJobPolling(jobId, token) {
  jobIdDisplay.textContent = jobId;
  showJobStatus('queued');
  const TERMINAL = new Set(['completed', 'completed_raw_only', 'failed']);
  const MAX_ERRORS = 5;
  let consecutiveErrors = 0;
  const id = setInterval(async () => {
    try {
      const r = await fetch(`/api/ingest/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) {
        if (++consecutiveErrors >= MAX_ERRORS) { clearInterval(id); showJobStatus('timeout'); }
        return;
      }
      consecutiveErrors = 0;
      const job = await parseJson(r);
      showJobStatus(job.status, job);
      if (TERMINAL.has(job.status)) clearInterval(id);
    } catch {
      if (++consecutiveErrors >= MAX_ERRORS) { clearInterval(id); showJobStatus('timeout'); }
    }
  }, 2000);
}

// --- URL/Job Param Check (bookmarklet entry point) ---

async function checkUrlJobParam() {
  const params = new URLSearchParams(window.location.search);
  const jobId = params.get('job');
  const clipUrl = params.get('clipurl');
  window.history.replaceState({}, '', window.location.pathname);
  if (jobId) {
    const token = await ensureToken();
    if (!token) return;
    startJobPolling(jobId, token);
  } else if (clipUrl) {
    tabs[0].click();
    let decodedUrl = clipUrl;
    try { decodedUrl = decodeURIComponent(clipUrl); } catch (_) {}
    urlInput.value = decodedUrl;
    await handleUrlIngest();
  }
}

// --- Job Status Display ---

function showJobStatus(status, job = null) {
  const icons = { queued: '⏳', processing: '⚙️', completed: '✅', completed_raw_only: '✅', failed: '❌', timeout: '⚠️' };
  const texts = {
    queued: 'Queued — waiting to process...',
    processing: 'Processing — converting and generating wiki...',
    completed: `Saved to vault${job?.files_written?.length ? ' — ' + job.files_written.join(', ') : ''}`,
    completed_raw_only: `Saved to vault (no wiki)${job?.files_written?.length ? ' — ' + job.files_written.join(', ') : ''}`,
    failed: `Failed${job?.error_detail ? ': ' + job.error_detail : ''}`,
    timeout: 'Timed out — check server logs',
  };
  jobStatusIcon.textContent = icons[status] ?? '⏳';
  jobStatusText.textContent = texts[status] ?? status;
  jobStatusSection.dataset.status = status;
  jobStatusSection.style.display = 'block';
}

// --- Error Display ---

function showError(message) {
  errorMessage.textContent = message;
  errorBanner.style.display = "block";
}

function hideError() {
  errorBanner.style.display = "none";
  errorMessage.textContent = "";
}

// --- Token Management ---

async function ensureToken() {
  if (authToken) return authToken;
  return await showTokenModal();
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

// --- Helpers ---

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
  const token = await ensureToken();
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
  const token = await ensureToken();
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

// --- Keyboard shortcut: Cmd/Ctrl+Enter ---
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (!(e.metaKey || e.ctrlKey)) return;
  const activeTab = document.querySelector('.tab-button[aria-selected="true"]');
  if (!activeTab) return;
  if (activeTab.id === "url-tab") handleUrlConvert();
  else if (activeTab.id === "paste-tab") pasteConvertBtn.click();
  else if (activeTab.id === "upload-tab" && selectedFile) fileConvertBtn.click();
});

// --- Focus management ---
document.querySelectorAll(".tab-button").forEach((tab) => {
  tab.addEventListener("click", () => {
    if (tab.id === "url-tab") setTimeout(() => urlInput.focus(), 10);
    else if (tab.id === "paste-tab") setTimeout(() => pasteInput.focus(), 10);
  });
});
