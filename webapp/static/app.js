// Demo frontend logic. Vanilla JS, built strictly against the CLAUDE.md §10
// contract: GET /search?color= -> SearchResponse{query,bucket,count,results},
// items are SearchResultItem, classify/review payloads are §8 ColorRecords.

const $ = (sel) => document.querySelector(sel);

// Rough display color per bucket, for tag chips.
const BUCKET_CSS = {
  red: "#d04545", orange: "#e07b39", yellow: "#e3c33e", green: "#5a9a5e",
  blue: "#4a72c4", purple: "#8c5fb5", grey: "#9aa0a8", white: "#f5f5f2",
  black: "#26282b", brown: "#8a5a3b",
};

// canonical_hsl {h,s,l} -> CSS. Null record -> a striped "unclassified" fill.
const UNCLASSIFIED = "repeating-linear-gradient(45deg,#eceef1,#eceef1 6px,#f8f9fa 6px,#f8f9fa 12px)";
const cssOf = (hsl) =>
  hsl ? `hsl(${Math.round(hsl.h)} ${Math.round(hsl.s * 100)}% ${Math.round(hsl.l * 100)}%)` : UNCLASSIFIED;

// Prefer the real swatch image (image_url, served from fixtures/images/);
// fall back to the canonical_hsl color fill / unclassified stripes.
// Longhand properties: the shorthand can't combine a gradient fallback with
// a url() image in one layer (invalid CSS -> dropped entirely).
const swatchCss = (item) =>
  item.image_url
    ? `background-image:url('${encodeURI(item.image_url)}');background-size:cover;` +
      `background-position:center;background-color:#eef0f3`
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
};
$("#tab-search").onclick = () => showTab("search");
$("#tab-admin").onclick = () => showTab("admin");

// ---------- shared renderers ----------
const groupChip = (bucket, onRemove) => {
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.innerHTML = `<span class="dot" style="background:${BUCKET_CSS[bucket] || "#ccc"}"></span>${bucket}`;
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

// ---------- search tab (the §10 contract) ----------
$("#search-form").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("#search-input").value;
  const data = await api(`/search?color=${encodeURIComponent(q)}`); // SearchResponse
  $("#search-meta").textContent = data.bucket
    ? `“${data.query}” → ${data.bucket} · ${data.count} result(s)`
    : q.trim() ? `“${data.query}” doesn't map to a color bucket` : "";

  const out = $("#search-results");
  out.replaceChildren(...data.results.map(resultCard));
  if (!data.count && q.trim()) {
    out.innerHTML = `<p class="empty">No results${data.bucket ? ` for ${data.bucket} — is anything classified ${data.bucket} yet? (Admin tab)` : ""}.</p>`;
  }
};

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
  renderClassifySelect(items);
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
      chip.innerHTML = `<span class="dot" style="background:${BUCKET_CSS[b] || "#ccc"}"></span>${b}` +
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

function renderClassifySelect(adminItems) {
  const sel = $("#classify-product");
  sel.replaceChildren(
    ...adminItems.map(({ item }) =>
      Object.assign(document.createElement("option"), {
        value: idOf(item),
        textContent: `${item.swatch_name ?? item.material_id} — ${item.company ?? "?"}${item.color_groups.length ? "" : " (unclassified)"}`,
      }),
    ),
  );
}

// ---------- classify drop-zone ----------
const dropZone = $("#drop-zone");
const fileInput = $("#classify-file");

const showPickedFile = () => {
  const f = fileInput.files[0];
  $("#drop-zone-label").textContent = f ? `🖼 ${f.name}` : "📥 Drop a swatch image here — or click to browse";
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
  $("#classify-form").requestSubmit(); // dropping = classify immediately
};

// Dropping anywhere else on the page must not navigate away from the demo.
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

$("#classify-form").onsubmit = async (e) => {
  e.preventDefault();
  const file = $("#classify-file").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const out = $("#classify-result");
  out.innerHTML = `<p class="muted">Clustering…</p>`;
  try {
    // response is a §8 ColorRecord
    const rec = await api(`/api/classify/${$("#classify-product").value}`, { method: "POST", body: form });
    const chips = rec.color_groups
      .map((b) => `<span class="chip"><span class="dot" style="background:${BUCKET_CSS[b] || "#ccc"}"></span>${b}</span>`)
      .join(" ");
    const dom = `<span class="chip"><span class="dot" style="background:${cssOf(rec.canonical_hsl)}"></span>dominant</span>`;
    out.innerHTML = rec.needs_review
      ? `<div class="flash warn">Ambiguous (confidence ${Math.round(rec.confidence * 100)}%) → sent to review queue &nbsp;${chips} ${dom}</div>`
      : `<div class="flash">Published <b>${rec.color_groups.join(", ")}</b> (confidence ${Math.round(rec.confidence * 100)}%) &nbsp;${chips} ${dom}</div>`;
    fileInput.value = "";   // ready for the next drop
    showPickedFile();
    refreshAdmin();
  } catch (err) {
    out.innerHTML = `<div class="flash warn">⚠️ ${err.message}</div>`;
  }
};

// initial load
refreshAdmin();
