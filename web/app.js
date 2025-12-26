const state = {
  releases: [],
  nzbs: [],
  releasePage: 1,
  nzbPage: 1,
  releasePageSize: 20,
  nzbPageSize: 20,
};

function basePath() {
  const parts = window.location.pathname.split("/");
  if (parts.length > 1 && parts[1] === "tricerapost") {
    return "/tricerapost";
  }
  return "";
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

function qs(id) {
  return document.getElementById(id);
}

function formatMeta(item) {
  const meta = [];
  if (item.type && item.type !== "unknown") meta.push(item.type);
  if (item.quality) meta.push(item.quality);
  if (item.source) meta.push(item.source);
  if (item.codec) meta.push(item.codec);
  if (item.audio) meta.push(item.audio);
  if (item.subtitles) meta.push("subs");
  if (Array.isArray(item.languages) && item.languages.length) meta.push(item.languages.join(", "));
  return meta;
}

function renderReleasePagination(total) {
  const info = qs("release-info");
  const prev = qs("release-prev");
  const next = qs("release-next");
  if (!info || !prev || !next) return;

  const totalPages = Math.max(Math.ceil(total / state.releasePageSize), 1);
  state.releasePage = Math.min(state.releasePage, totalPages);

  info.textContent = `Page ${state.releasePage} of ${totalPages}`;
  prev.disabled = state.releasePage <= 1;
  next.disabled = state.releasePage >= totalPages;
}

function renderNzbPagination(total) {
  const info = qs("nzb-info");
  const prev = qs("nzb-prev");
  const next = qs("nzb-next");
  if (!info || !prev || !next) return;

  const totalPages = Math.max(Math.ceil(total / state.nzbPageSize), 1);
  state.nzbPage = Math.min(state.nzbPage, totalPages);

  info.textContent = `Page ${state.nzbPage} of ${totalPages}`;
  prev.disabled = state.nzbPage <= 1;
  next.disabled = state.nzbPage >= totalPages;
}

function renderReleases(list) {
  const container = qs("release-list");
  const status = qs("release-status");
  if (!container || !status) return;

  container.innerHTML = "";
  if (!list.length) {
    status.textContent = "No complete releases yet.";
    renderReleasePagination(0);
    return;
  }

  status.textContent = `${list.length} releases found.`;
  renderReleasePagination(list.length);

  const start = (state.releasePage - 1) * state.releasePageSize;
  const pageItems = list.slice(start, start + state.releasePageSize);

  pageItems.forEach((item) => {
    const card = document.createElement("div");
    card.className = "release-card";
    if (item.nzb_created) card.classList.add("nzb-created");

    const title = document.createElement("div");
    title.className = "release-title";
    title.textContent = item.filename_guess || item.name || "(untitled)";

    const metaRow = document.createElement("div");
    metaRow.className = "release-meta";

    const size = document.createElement("span");
    size.className = "badge";
    size.textContent = item.size_human || "size ?";

    const parts = document.createElement("span");
    parts.className = "badge";
    parts.textContent = `${item.parts_received}/${item.parts_expected || "?"}`;

    metaRow.append(size, parts);
    formatMeta(item).forEach((value) => {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = value;
      metaRow.appendChild(badge);
    });

    const groupLine = document.createElement("div");
    groupLine.className = "release-meta";
    const groups = Array.isArray(item.groups) ? item.groups.join(", ") : "";
    groupLine.textContent = groups ? `Groups: ${groups}` : "";

    const statusLine = document.createElement("div");
    statusLine.className = "release-meta";
    statusLine.textContent = item.nzb_created ? "NZB created" : "NZB pending";

    card.append(title, metaRow, groupLine, statusLine);
    container.appendChild(card);
  });
}

function renderNzbs(list) {
  const container = qs("nzb-list");
  const status = qs("nzb-status");
  if (!container || !status) return;

  container.innerHTML = "";
  if (!list.length) {
    status.textContent = "No NZBs yet.";
    renderNzbPagination(0);
    return;
  }

  status.textContent = `${list.length} NZBs ready.`;
  renderNzbPagination(list.length);

  const start = (state.nzbPage - 1) * state.nzbPageSize;
  const pageItems = list.slice(start, start + state.nzbPageSize);

  pageItems.forEach((item) => {
    const card = document.createElement("div");
    card.className = "release-card";

    const title = document.createElement("div");
    title.className = "release-title";
    title.textContent = item.name || "(untitled)";

    const metaRow = document.createElement("div");
    metaRow.className = "release-meta";

    const source = document.createElement("span");
    source.className = "badge";
    source.textContent = item.source || "unknown";

    const size = document.createElement("span");
    size.className = "badge";
    size.textContent = item.bytes ? `${(item.bytes / (1024 * 1024)).toFixed(1)} MB` : "size ?";

    metaRow.append(source, size);

    const groupLine = document.createElement("div");
    groupLine.className = "release-meta";
    groupLine.textContent = item.group ? `Group: ${item.group}` : "";

    const link = document.createElement("a");
    link.className = "nzb-link";
    const prefix = basePath();
    link.href = `${prefix}/api/nzb/file?key=${encodeURIComponent(item.key)}`;
    link.textContent = "Download NZB";

    card.append(title, metaRow, groupLine, link);
    container.appendChild(card);
  });
}

async function loadReleases() {
  try {
    const prefix = basePath();
    state.releases = await fetchJson(`${prefix}/api/releases`);
    renderReleases(state.releases);
  } catch (err) {
    const status = qs("release-status");
    if (status) status.textContent = `Failed to load releases: ${err.message}`;
  }
}

async function loadNzbs() {
  try {
    const prefix = basePath();
    state.nzbs = await fetchJson(`${prefix}/api/nzbs`);
    renderNzbs(state.nzbs);
  } catch (err) {
    const status = qs("nzb-status");
    if (status) status.textContent = `Failed to load NZBs: ${err.message}`;
  }
}

function initPage() {
  const releasePrev = qs("release-prev");
  const releaseNext = qs("release-next");
  if (releasePrev) {
    releasePrev.addEventListener("click", () => {
      state.releasePage = Math.max(1, state.releasePage - 1);
      renderReleases(state.releases);
    });
  }
  if (releaseNext) {
    releaseNext.addEventListener("click", () => {
      state.releasePage += 1;
      renderReleases(state.releases);
    });
  }

  const nzbPrev = qs("nzb-prev");
  const nzbNext = qs("nzb-next");
  if (nzbPrev) {
    nzbPrev.addEventListener("click", () => {
      state.nzbPage = Math.max(1, state.nzbPage - 1);
      renderNzbs(state.nzbs);
    });
  }
  if (nzbNext) {
    nzbNext.addEventListener("click", () => {
      state.nzbPage += 1;
      renderNzbs(state.nzbs);
    });
  }

  const saveAllBtn = qs("save-all-nzbs");
  if (saveAllBtn) {
    saveAllBtn.addEventListener("click", async () => {
      const status = qs("save-all-status");
      if (status) status.textContent = "Saving...";
      const prefix = basePath();
      try {
        const result = await fetchJson(`${prefix}/api/nzb/save_all`, { method: "POST" });
        if (status) status.textContent = `Saved ${result.saved || 0} NZBs.`;
        await loadNzbs();
      } catch (err) {
        if (status) status.textContent = `Save failed: ${err.message}`;
      }
    });
  }

  loadReleases();
  loadNzbs();
}

initPage();
