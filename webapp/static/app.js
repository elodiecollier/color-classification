// Demo frontend logic. Vanilla JS, built strictly against the CLAUDE.md §10
// contract: GET /search?color= -> SearchResponse{query,bucket,count,results},
// items are SearchResultItem, classify/review payloads are §8 ColorRecords.

const $ = (sel) => document.querySelector(sel);

// Display color per bucket, for tag chips. The actual values live in ONE
// place — the :root palette in style.css — referenced here by variable.
const bucketCss = (b) => `var(--bucket-${b}, var(--bucket-unknown))`;

// canonical_hsl {h,s,l} -> CSS. Null record -> a striped "unclassified" fill.
const UNCLASSIFIED =
  "repeating-linear-gradient(45deg,var(--stripe-a),var(--stripe-a) 6px,var(--stripe-b) 6px,var(--stripe-b) 12px)";
const cssOf = (hsl) =>
  hsl ? `hsl(${Math.round(hsl.h)} ${Math.round(hsl.s * 100)}% ${Math.round(hsl.l * 100)}%)` : UNCLASSIFIED;

// Prefer the real swatch image (image_url, served from fixtures/images/);
// fall back to the canonical_hsl color fill / unclassified stripes.
// Longhand properties: the shorthand can't combine a gradient fallback with
// a url() image in one layer (invalid CSS -> dropped entirely).
const swatchCss = (item) =>
  item.image_url
    ? `background-image:url('${encodeURI(item.image_url)}');background-size:cover;` +
      `background-position:center;background-color:var(--soft)`
    : `background:${cssOf(item.canonical_hsl)}`;

// The per-swatch key used in admin API paths (a material can have many swatches).
const idOf = (x) => x.swatch_id ?? x.material_id;

const api = async (path, opts = {}) => {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
};

// ---------- tabs ----------
const showTab = (name) => {
  $("#view-search").hidden = name !== "search";
  $("#view-admin").hidden = name !== "admin";
  $("#tab-search").classList.toggle("active", name === "search");
  $("#tab-admin").classList.toggle("active", name === "admin");
  if (name === "admin") refreshAdmin();
  if (name === "search") runSearch($("#search-input").value);
};
$("#tab-search").onclick = () => showTab("search");
$("#tab-admin").onclick = () => showTab("admin");

// ---------- shared renderers ----------
const groupChip = (bucket, onRemove) => {
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.innerHTML = `<span class="dot" style="background:${bucketCss(bucket)}"></span>${bucket}`;
  if (onRemove) {
    const x = document.createElement("span");
    x.className = "x";
    x.textContent = "×";
    x.title = "remove";
    x.onclick = onRemove;
    chip.appendChild(x);
  }
  return chip;
};

// One SearchResultItem -> a result card.
const resultCard = (item) => {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <div class="swatch" style="${swatchCss(item)}"></div>
    <div class="body">
      <div class="name">${item.swatch_name ?? item.material_id}
        ${item.needs_review ? '<span class="chip">⚠ review</span>' : ""}</div>
      <div class="sub">${item.company ?? ""}</div>
      <div class="groups"></div>
    </div>`;
  const groups = card.querySelector(".groups");
  item.color_groups.forEach((b) => groups.appendChild(groupChip(b)));
  if (!item.color_groups.length) groups.innerHTML = `<span class="muted">unclassified</span>`;
  return card;
};

// ---------- search tab (the §10 contract, paginated) ----------
// Empty query = browse the whole library; a term filters by color bucket.
// Results are fetched a page at a time and appended on scroll, so this scales
// to an arbitrarily large library (the server slices; the client never holds
// more than what's been scrolled to).
const PAGE_SIZE = 24;

// Live pagination state. `seq` tags the active query so a slow in-flight page
// from a superseded search (fast typing) is discarded instead of appended.
let browse = { q: "", offset: 0, total: 0, loading: false, done: true, seq: 0 };
let _searchSeq = 0;

function setSearchMeta() {
  const trimmed = browse.q.trim();
  const meta = $("#search-meta");
  if (!trimmed) {
    meta.textContent = `Showing ${browse.offset} of ${browse.total} swatches — type a color or name to filter`;
  } else if (browse.bucket) {
    meta.textContent = `“${browse.q}” → ${browse.bucket} · ${browse.total} result(s)`;
  } else {
    meta.textContent = `“${browse.q}” · ${browse.total} result(s)`;
  }
}

// Start a fresh search (resets pagination + clears the grid).
async function runSearch(q) {
  const seq = ++_searchSeq;
  browse = { q, offset: 0, total: 0, bucket: null, loading: false, done: false, seq };
  $("#search-results").replaceChildren();
  await loadNextPage();
}

// Fetch + append the next page for the current query. No-op while a page is in
// flight or once the full set is exhausted.
async function loadNextPage() {
  if (browse.loading || browse.done) return;
  browse.loading = true;
  const seq = browse.seq;
  let data;
  try {
    data = await api(
      `/search?color=${encodeURIComponent(browse.q)}&offset=${browse.offset}&limit=${PAGE_SIZE}`,
    );
  } catch (err) {
    browse.loading = false;
    return;
  }
  if (seq !== _searchSeq) return; // a newer search superseded this one

  browse.bucket = data.bucket;
  browse.total = data.total ?? data.count;
  browse.offset += data.results.length;
  if (!data.results.length || browse.offset >= browse.total) browse.done = true;

  const out = $("#search-results");
  if (!browse.offset && browse.done) {
    // first page came back empty
    out.innerHTML = browse.q.trim()
      ? `<p class="empty">No swatches match “${browse.q}” by color or name.</p>`
      : `<p class="empty">No swatches in the library yet.</p>`;
  } else {
    data.results.forEach((item) => out.appendChild(resultCard(item)));
  }
  setSearchMeta();
  browse.loading = false;

  // If the first page didn't fill the viewport there's no scrollbar to drive
  // further loads — keep pulling until the page scrolls or the set is done.
  if (!browse.done && document.documentElement.scrollHeight <= window.innerHeight) {
    loadNextPage();
  }
}

$("#search-form").onsubmit = (e) => {
  e.preventDefault();
  runSearch($("#search-input").value);
};

// Filter live as the user types (debounced so we don't fire on every keystroke).
let _searchTimer;
$("#search-input").addEventListener("input", () => {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => runSearch($("#search-input").value), 200);
});

// Infinite scroll: load the next page as the user nears the bottom.
window.addEventListener("scroll", () => {
  if ($("#view-search").hidden) return;
  const nearBottom =
    window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 400;
  if (nearBottom) loadNextPage();
});

// ---------- admin tab ----------
async function refreshAdmin() {
  const [items, review, buckets] = await Promise.all([
    api("/api/products"),  // list[SearchResultItem]
    api("/api/review"),    // list[{material, record}]
    api("/api/buckets"),
  ]);

  $("#bucket-list").replaceChildren(
    ...buckets.map((b) => Object.assign(document.createElement("option"), { value: b })),
  );

  renderReview(review, buckets);
  renderProducts(items);
}

function renderProducts(adminItems) {
  const tbody = $("#products-table tbody");
  tbody.replaceChildren();
  for (const { item, source, confidence, bucket_coverage } of adminItems) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><div class="mini-swatch" style="${swatchCss(item)}"></div></td>
      <td><b>${item.swatch_name ?? item.material_id}</b>${item.needs_review ? ' <span class="chip">⚠ review</span>' : ""}</td>
      <td>${item.company ?? ""}</td>
      <td class="groups-cell"></td>`;
    const cell = tr.querySelector(".groups-cell");
    // Tagged chips, labelled ONLY with measured pixel coverage. A tag without
    // pixel evidence (manually added / name-sourced) gets "manual", never a
    // fake percentage.
    const pct = (v) => `${Math.round(v * 100)}%`;
    item.color_groups.forEach((b) => {
      const cov = bucket_coverage[b] ?? 0;
      const chip = groupChip(b, async () => {
        await api(`/api/products/${idOf(item)}/tags/${b}`, { method: "DELETE" });
        refreshAdmin();
      });
      chip.title = cov > 0 ? "pixel coverage (share of the swatch image)" : "no pixel evidence for this tag";
      chip.insertBefore(
        Object.assign(document.createElement("span"), {
          className: "pct",
          textContent: cov > 0 ? pct(cov) : "manual",
        }),
        chip.querySelector(".x"),
      );
      cell.appendChild(chip);
    });
    // inline add input — server validates against the 10-bucket taxonomy
    const input = document.createElement("input");
    input.className = "add-tag";
    input.placeholder = "+ color";
    input.setAttribute("list", "bucket-list");
    input.onkeydown = async (e) => {
      if (e.key === "Enter" && input.value.trim()) {
        e.preventDefault();
        try {
          await api(`/api/products/${idOf(item)}/tags`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tag: input.value }),
          });
          refreshAdmin();
        } catch (err) {
          alert(err.message); // e.g. not one of the 10 buckets
        }
      }
    };
    cell.appendChild(input);

    // Under the tags: the full measured pixel-coverage breakdown across ALL
    // ten buckets (tagged + untagged, sorted by coverage), then the
    // record-level pipeline confidence + which signal produced it.
    const breakdown = Object.entries(bucket_coverage)
      .sort(([, a], [, b]) => b - a)
      .map(([b, v]) => `${b} ${pct(v)}`)
      .join(" · ");
    const detail = document.createElement("div");
    detail.className = "bucket-detail";
    detail.textContent = source
      ? `pixel coverage: ${breakdown}\npipeline confidence ${pct(confidence)} · source: ${source}`
      : "no classification yet";
    cell.appendChild(detail);
    tbody.appendChild(tr);
  }
}

function renderReview(review, allBuckets) {
  $("#review-count").textContent = review.length || "";
  const list = $("#review-list");
  list.replaceChildren();
  if (!review.length) {
    list.innerHTML = `<p class="empty">Queue is empty — nothing needs review.</p>`;
    return;
  }
  for (const { material, record, bucket_coverage } of review) {
    // reason comes from the record itself: conflict_reason when set (§6
    // conflicts), otherwise derived from its low confidence.
    const reason = record.conflict_reason
      ?? `Low confidence (${Math.round(record.confidence * 100)}%) — ${record.color_groups.length} candidate buckets.`;
    const div = document.createElement("div");
    div.className = "review-item";
    // thumb: the actual swatch image when the record has one, else the
    // record's canonical color (or unclassified stripes).
    const thumbCss = material.image_ref
      ? `background-image:url('${encodeURI(`/swatches/${material.image_ref}`)}');` +
        `background-size:cover;background-position:center`
      : `background:${cssOf(record.canonical_hsl)}`;
    div.innerHTML = `
      <div class="review-thumb" style="${thumbCss}" title="${material.image_ref ?? "no swatch image"}"></div>
      <div class="review-body">
        <b>${material.swatch_name ?? material.material_id}</b> <span class="muted">· ${material.company ?? ""} · source: ${record.source}</span>
        <div class="reason">${reason}</div>
        <div class="suggested"></div>
        <button class="btn approve">Approve selected</button>
        <button class="btn secondary dismiss">Dismiss</button>
      </div>`;
    const sug = div.querySelector(".suggested");
    const selected = new Set(record.color_groups);
    // ALL ten buckets are offered — the algorithm's suggestions come
    // pre-selected with their pixel evidence; the reviewer is free to pick
    // any other color (e.g. the one the NAME suggested in a conflict).
    for (const b of allBuckets) {
      const suggested = record.color_groups.includes(b);
      const cov = bucket_coverage[b] ?? 0;
      const chip = document.createElement("span");
      chip.className = `chip selectable${suggested ? " on" : ""}`;
      chip.title = cov > 0 ? "pixel coverage" : "no pixel evidence";
      chip.innerHTML = `<span class="dot" style="background:${bucketCss(b)}"></span>${b}` +
        (cov > 0 ? ` <span class="pct">${Math.round(cov * 100)}%</span>` : "");
      chip.onclick = () => {
        chip.classList.toggle("on");
        chip.classList.contains("on") ? selected.add(b) : selected.delete(b);
      };
      sug.appendChild(chip);
    }
    div.querySelector(".approve").onclick = async () => {
      if (!selected.size) {
        alert("Select at least one color — or Dismiss the item.");
        return;
      }
      await api(`/api/review/${idOf(record)}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ color_groups: [...selected] }),
      });
      refreshAdmin();
    };
    div.querySelector(".dismiss").onclick = async () => {
      await api(`/api/review/${idOf(record)}/dismiss`, { method: "POST" });
      refreshAdmin();
    };
    list.appendChild(div);
  }
}

// ---------- add-to-library drop-zone ----------
const dropZone = $("#drop-zone");
const fileInput = $("#classify-file");
const nameInput = $("#swatch-name");

const showPickedFile = () => {
  const f = fileInput.files[0];
  $("#drop-zone-label").textContent = f ? `🖼 ${f.name}` : "📥 Drop a swatch image here — or click to browse";
  // autofill the swatch name from the file name (sans extension); the user
  // can edit it before hitting "Add to library"
  if (f) nameInput.value = f.name.replace(/\.[^.]+$/, "");
};

dropZone.onclick = () => fileInput.click();
dropZone.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") fileInput.click(); };
fileInput.onchange = showPickedFile;

dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add("drag"); };
dropZone.ondragleave = () => dropZone.classList.remove("drag");
dropZone.ondrop = (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag");
  const file = e.dataTransfer.files[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    $("#classify-result").innerHTML = `<div class="flash warn">⚠️ "${file.name}" isn't an image</div>`;
    return;
  }
  fileInput.files = e.dataTransfer.files;
  showPickedFile();
  nameInput.focus(); // dropped: name is prefilled — review it, then Add to library
};

// Dropping anywhere else on the page must not navigate away from the demo.
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

// Step 1: Analyze — run the full pipeline, show the editable proposal.
$("#classify-form").onsubmit = async (e) => {
  e.preventDefault();
  const out = $("#classify-result");
  const file = fileInput.files[0];
  if (!file) {
    out.innerHTML = `<div class="flash warn">Drop or pick a swatch image first.</div>`;
    return;
  }
  const swatchName = nameInput.value.trim();
  const form = new FormData();
  form.append("file", file);
  form.append("name", swatchName);
  out.innerHTML = `<p class="muted">Analyzing (pixels${swatchName ? " + name" : ""})…</p>`;
  try {
    const a = await api("/api/swatches/analyze", { method: "POST", body: form });
    renderProposal(file, swatchName, a);
  } catch (err) {
    out.innerHTML = `<div class="flash warn">⚠️ ${err.message}</div>`;
  }
};

// Step 2: the proposal — tags as toggleable chips, then commit or discard.
function renderProposal(file, swatchName, a) {
  const out = $("#classify-result");
  const rec = a.record;
  const pct = (v) => `${Math.round(v * 100)}%`;

  const nameLine = !swatchName
    ? "name signal: (no name given)"
    : a.name_used
      ? `name signal: ${a.name_buckets.length ? a.name_buckets.join(", ") : "not an intuitive color"} (${pct(a.name_confidence)})`
      : "name signal: unavailable (no OPENROUTER_API_KEY)";
  // the third opinion only runs when name and image conflicted
  const visionLine = a.vision_used
    ? `\nvision third opinion: ${a.vision_buckets.length ? a.vision_buckets.join(", ") : "unsure"} (${pct(a.vision_confidence)})`
    : "";

  const box = document.createElement("div");
  box.className = `flash${rec.needs_review ? " warn" : ""}`;
  // preview the dropped image itself, straight from the browser's copy
  const imgUrl = URL.createObjectURL(file);
  box.innerHTML = `
    <div class="proposal-row">
      <div class="review-thumb" style="background-image:url('${imgUrl}');background-size:cover;background-position:center" title="${file.name}"></div>
      <div class="review-body">
        <b>Proposed for “${swatchName || file.name}”</b>
        <div class="bucket-detail">${nameLine}${visionLine}
pipeline verdict: ${rec.color_groups.join(", ") || "(none)"} · confidence ${pct(rec.confidence)} · source: ${rec.source}${rec.conflict_reason ? `\n⚠ ${rec.conflict_reason}` : ""}</div>
        <div class="suggested"></div>
        <button class="btn commit">Add to library</button>
        <button class="btn secondary discard">Discard</button>
      </div>
    </div>`;

  // full-taxonomy editable chips, proposal pre-selected, pixel evidence shown
  const selected = new Set(rec.color_groups);
  const sug = box.querySelector(".suggested");
  for (const [b, cov] of Object.entries(a.bucket_coverage)) {
    const chip = document.createElement("span");
    chip.className = `chip selectable${selected.has(b) ? " on" : ""}`;
    chip.title = cov > 0 ? "pixel coverage" : "no pixel evidence";
    chip.innerHTML = `<span class="dot" style="background:${bucketCss(b)}"></span>${b}` +
      (cov > 0 ? ` <span class="pct">${pct(cov)}</span>` : "");
    chip.onclick = () => {
      chip.classList.toggle("on");
      chip.classList.contains("on") ? selected.add(b) : selected.delete(b);
    };
    sug.appendChild(chip);
  }

  box.querySelector(".commit").onclick = async () => {
    if (!selected.size) {
      alert("Select at least one color — or Discard.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("name", swatchName);
    form.append("record", JSON.stringify(rec));
    form.append("color_groups", JSON.stringify([...selected]));
    try {
      const final = await api("/api/swatches", { method: "POST", body: form });
      URL.revokeObjectURL(imgUrl);
      out.innerHTML = `<div class="flash">Added “${swatchName || final.material_id}” → <b>${final.color_groups.join(", ")}</b> (source: ${final.source})</div>`;
      fileInput.value = "";
      nameInput.value = "";
      showPickedFile();
      refreshAdmin();
    } catch (err) {
      out.innerHTML = `<div class="flash warn">⚠️ ${err.message}</div>`;
    }
  };
  box.querySelector(".discard").onclick = () => {
    URL.revokeObjectURL(imgUrl);
    out.replaceChildren();
  };

  out.replaceChildren(box);
}

// initial load — the search tab is shown first, so populate the browse list
runSearch("");
refreshAdmin();
