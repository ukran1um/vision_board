/* ------------------------------------------------------------------
 * VisionBoard — frontend controller
 *
 * Responsibilities:
 *   - Accept images via drag-drop, file picker, and clipboard paste
 *   - Resize + compress each image (max edge 1568px, JPEG quality 0.85)
 *   - Classify aspect ratio and place into a CSS-grid mosaic
 *   - Remove tiles (visible close button, keyboard-accessible)
 *   - POST images to /api/analyze and render reflections
 *   - Agree / Disagree / Edit actions on each reflection
 * ------------------------------------------------------------------ */

const MAX_EDGE = 1568;
const JPEG_QUALITY = 0.85;
const ACCEPTED_PREFIX = "image/";
const ANALYZE_TIMEOUT_MS = 60_000;

function getSessionToken() {
  const meta = document.querySelector('meta[name="vb-token"]');
  const val = meta ? meta.getAttribute("content") : "";
  // Guard against the server forgetting to substitute the placeholder
  if (!val || val === "__VB_TOKEN__") return "";
  return val;
}
const SESSION_TOKEN = getSessionToken();

const state = {
  images: [],      // [{ id, blob, dataUrl, ratioClass }]
  statements: [],  // [{ text, original, verdict }]
};

let nextId = 1;

// -------- DOM refs --------------------------------------------------
const $board           = document.getElementById("board");
const $mosaic          = document.getElementById("mosaic");
const $emptyHint       = document.getElementById("empty-hint");
const $btnAdd          = document.getElementById("btn-add");
const $btnAnalyze      = document.getElementById("btn-analyze");
const $fileInput       = document.getElementById("file-input");
const $reflList        = document.getElementById("reflections-list");
const $reflEmpty       = document.getElementById("reflections-empty");
const $reflSkel        = document.getElementById("reflections-skeleton");
const $toastContainer  = document.getElementById("toast-container");

// -------- Input: picker / drag-drop / paste -------------------------
$btnAdd.addEventListener("click", () => $fileInput.click());

$fileInput.addEventListener("change", (e) => {
  addImages(e.target.files);
  $fileInput.value = "";
});

let dragDepth = 0;
window.addEventListener("dragenter", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth++;
  $board.classList.add("drag-active");
});
window.addEventListener("dragover", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = "copy";
});
window.addEventListener("dragleave", (e) => {
  if (!hasFiles(e)) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) $board.classList.remove("drag-active");
});
window.addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0;
  $board.classList.remove("drag-active");
  if (e.dataTransfer?.files?.length) addImages(e.dataTransfer.files);
});

window.addEventListener("paste", (e) => {
  const items = e.clipboardData?.items;
  if (!items) return;
  const files = [];
  for (const item of items) {
    if (item.kind === "file") {
      const f = item.getAsFile();
      if (f) files.push(f);
    }
  }
  if (files.length) addImages(files);
});

function hasFiles(e) {
  if (!e.dataTransfer) return false;
  const types = e.dataTransfer.types;
  if (!types) return false;
  for (const t of types) if (t === "Files") return true;
  return false;
}

// -------- Add / resize / compress -----------------------------------
async function addImages(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;

  const accepted = [];
  const rejected = [];
  for (const f of files) {
    if (f.type && f.type.startsWith(ACCEPTED_PREFIX)) {
      accepted.push(f);
    } else {
      rejected.push(f);
    }
  }

  if (rejected.length) {
    const names = rejected.map((f) => f.name || "file").slice(0, 2).join(", ");
    showToast(
      `Can't read ${rejected.length === 1 ? names : rejected.length + " files"}. ` +
      `Try JPEG, PNG, GIF, or WebP.`,
      "error"
    );
  }

  for (const file of accepted) {
    try {
      const processed = await processFile(file);
      state.images.push(processed);
    } catch (err) {
      console.error("Failed to process", file.name, err);
      showToast(`Couldn't load ${file.name || "image"}.`, "error");
    }
  }

  renderMosaic();
  updateAnalyzeButton();
}

async function processFile(file) {
  const rawDataUrl = await readAsDataURL(file);
  const img = await loadImage(rawDataUrl);

  const w = img.naturalWidth;
  const h = img.naturalHeight;

  // Always re-encode through canvas as JPEG — normalizes format, applies
  // compression, and resizes if needed.
  const { blob, dataUrl } = await resizeAndCompress(img, w, h);

  const ratioClass = classifyRatio(w, h, state.images.length === 0);

  return {
    id: nextId++,
    blob,
    dataUrl,
    ratioClass,
    width: w,
    height: h,
  };
}

function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(fr.error);
    fr.readAsDataURL(file);
  });
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Image decode failed"));
    img.src = src;
  });
}

async function resizeAndCompress(img, w, h) {
  let targetW = w;
  let targetH = h;
  const longest = Math.max(w, h);
  if (longest > MAX_EDGE) {
    const scale = MAX_EDGE / longest;
    targetW = Math.round(w * scale);
    targetH = Math.round(h * scale);
  }

  const canvas = document.createElement("canvas");
  canvas.width = targetW;
  canvas.height = targetH;
  const ctx = canvas.getContext("2d");
  // Fill white so transparent PNGs don't come out black on JPEG
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, targetW, targetH);
  ctx.drawImage(img, 0, 0, targetW, targetH);

  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("toBlob returned null"))),
      "image/jpeg",
      JPEG_QUALITY
    );
  });
  const dataUrl = await readAsDataURL(blob);
  return { blob, dataUrl };
}

function classifyRatio(w, h, isFirst) {
  const r = w / h;
  if (isFirst)         return "hero";
  if (r >= 2.0)        return "landscape-wide";
  if (r >= 1.3)        return "landscape";
  if (r >= 0.8)        return "square";
  if (r >= 0.5)        return "portrait";
  return "portrait-tall";
}

// -------- Render mosaic ---------------------------------------------
function renderMosaic() {
  $mosaic.innerHTML = "";

  state.images.forEach((imgData) => {
    const tile = document.createElement("div");
    tile.className = `tile ${imgData.ratioClass}`;
    tile.dataset.id = imgData.id;

    const img = document.createElement("img");
    img.alt = "Vision board image";
    img.src = imgData.dataUrl;
    tile.appendChild(img);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "tile-remove";
    removeBtn.setAttribute("aria-label", "Remove image");
    removeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      removeImage(imgData.id);
    });
    tile.appendChild(removeBtn);

    $mosaic.appendChild(tile);
  });

  const hasImages = state.images.length > 0;
  $mosaic.classList.toggle("has-images", hasImages);
  $emptyHint.style.display = hasImages ? "none" : "";
}

function removeImage(id) {
  state.images = state.images.filter((img) => img.id !== id);
  // If the first image (hero) was removed, promote the new first.
  if (state.images.length && !state.images.some((i) => i.ratioClass === "hero")) {
    const first = state.images[0];
    first.ratioClass = classifyRatio(first.width, first.height, true);
  }
  renderMosaic();
  updateAnalyzeButton();
}

function updateAnalyzeButton() {
  $btnAnalyze.disabled = state.images.length === 0;
}

// -------- Analyze ---------------------------------------------------
$btnAnalyze.addEventListener("click", analyze);

async function analyze() {
  if (state.images.length === 0) {
    showToast("Add at least one image to analyze.", "info");
    return;
  }

  setLoading(true);

  const formData = new FormData();
  state.images.forEach((img, i) => {
    formData.append("images", img.blob, `image-${i}.jpg`);
  });

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);

  try {
    const headers = {};
    if (SESSION_TOKEN) headers["X-VB-Token"] = SESSION_TOKEN;

    const res = await fetch("/api/analyze", {
      method: "POST",
      body: formData,
      headers,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      let msg = `Analyze failed (${res.status})`;
      try {
        const errJson = await res.json();
        if (errJson.detail) msg = errJson.detail;
      } catch (_) { /* ignore */ }
      if (res.status === 401) {
        msg = "Your session expired. Refresh the page and try again.";
      } else if (res.status === 429) {
        msg = msg || "You're going too fast. Please wait a moment.";
      }
      throw new Error(msg);
    }

    const data = await res.json();
    if (!data || !Array.isArray(data.statements)) {
      throw new Error("Unexpected response from server");
    }

    state.statements = data.statements.map((t) => ({
      text: t,
      original: t,
      verdict: "pending",
    }));

    renderReflections();
  } catch (err) {
    const message = err.name === "AbortError"
      ? "Analysis took too long. Please try again."
      : (err.message || "Something went wrong.");
    showErrorWithRetry(message);
  } finally {
    clearTimeout(timeoutId);
    setLoading(false);
  }
}

function setLoading(loading) {
  $btnAnalyze.classList.toggle("is-loading", loading);
  $btnAnalyze.disabled = loading || state.images.length === 0;
  const label = $btnAnalyze.querySelector(".btn-label");
  label.textContent = loading ? "Analyzing your vision…" : "✨ Analyze My Vision";

  $reflSkel.hidden = !loading;
  if (loading) {
    $reflEmpty.hidden = true;
    $reflList.hidden = true;
  }
}

// -------- Render reflections ----------------------------------------
function renderReflections() {
  $reflEmpty.hidden = true;
  $reflSkel.hidden = true;
  $reflList.hidden = false;
  $reflList.innerHTML = "";

  state.statements.forEach((stmt, idx) => {
    const row = document.createElement("div");
    row.className = "reflection";
    row.dataset.idx = idx;

    const p = document.createElement("p");
    p.className = "text";
    p.textContent = stmt.text;
    row.appendChild(p);

    const actions = document.createElement("div");
    actions.className = "actions";

    const agree = makeAction("Agree", "agree", idx, row, p);
    const disagree = makeAction("Disagree", "disagree", idx, row, p);
    const edit = makeAction("Edit", "edit", idx, row, p);

    actions.append(agree, disagree, edit);
    row.appendChild(actions);
    $reflList.appendChild(row);
  });
}

function makeAction(label, kind, idx, row, p) {
  const el = document.createElement("span");
  el.className = `act act-${kind}`;
  el.textContent = label;
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  const handler = () => handleAction(kind, idx, row, p, el);
  el.addEventListener("click", handler);
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handler();
    }
  });
  return el;
}

function handleAction(kind, idx, row, p, el) {
  const stmt = state.statements[idx];

  // Clear active states
  row.querySelectorAll(".act").forEach((a) => {
    a.classList.remove("active-agree", "active-disagree", "active-edit");
    // Also restore labels (remove any checkmarks)
    const base = a.className.match(/act-(\w+)/)?.[1];
    if (base === "agree")    a.textContent = "Agree";
    if (base === "disagree") a.textContent = "Disagree";
    if (base === "edit")     a.textContent = "Edit";
  });
  row.classList.remove("disagreed", "editing");
  p.contentEditable = "false";

  if (kind === "agree") {
    stmt.verdict = "agree";
    el.classList.add("active-agree");
    el.textContent = "✓ Agree";
  } else if (kind === "disagree") {
    stmt.verdict = "disagree";
    row.classList.add("disagreed");
    el.classList.add("active-disagree");
    el.textContent = "✗ Disagree";
  } else if (kind === "edit") {
    row.classList.add("editing");
    el.classList.add("active-edit");
    el.textContent = "✎ Editing";
    p.contentEditable = "true";
    p.focus();
    placeCaretAtEnd(p);

    const finishEdit = () => {
      p.contentEditable = "false";
      const newText = p.textContent.trim();
      stmt.text = newText;
      stmt.verdict = "edited";
      p.removeEventListener("blur", finishEdit);
      p.removeEventListener("keydown", onKey);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        p.textContent = stmt.text;
        p.blur();
      } else if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        p.blur();
      }
    };
    p.addEventListener("blur", finishEdit);
    p.addEventListener("keydown", onKey);
  }
}

function placeCaretAtEnd(el) {
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
}

// -------- Toasts ----------------------------------------------------
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  const span = document.createElement("span");
  span.textContent = message;
  toast.appendChild(span);
  $toastContainer.appendChild(toast);
  setTimeout(() => dismissToast(toast), 4000);
  return toast;
}

function showErrorWithRetry(message) {
  const toast = document.createElement("div");
  toast.className = "toast error";
  const span = document.createElement("span");
  span.textContent = message;
  toast.appendChild(span);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "retry";
  btn.textContent = "Try again";
  btn.addEventListener("click", () => {
    dismissToast(toast);
    analyze();
  });
  toast.appendChild(btn);

  $toastContainer.appendChild(toast);
  setTimeout(() => dismissToast(toast), 8000);
}

function dismissToast(toast) {
  if (!toast.isConnected) return;
  toast.classList.add("dismissing");
  setTimeout(() => toast.remove(), 220);
}
