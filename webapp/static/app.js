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

  renderReview(review);
  renderProducts(items);
  renderClassifySelect(items);
}

function renderProducts(items) {
  const tbody = $("#products-table tbody");
  tbody.replaceChildren();
  for (const item of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><div class="mini-swatch" style="${swatchCss(item)}"></div></td>
      <td><b>${item.swatch_name ?? item.material_id}</b>${item.needs_review ? ' <span class="chip">⚠ review</span>' : ""}</td>
      <td>${item.company ?? ""}</td>
      <td class="groups-cell"></td>`;
    const cell = tr.querySelector(".groups-cell");
    item.color_groups.forEach((b) =>
      cell.appendChild(groupChip(b, async () => {
        await api(`/api/products/${idOf(item)}/tags/${b}`, { method: "DELETE" });
        refreshAdmin();
      })),
    );
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
    tbody.appendChild(tr);
  }
}

function renderReview(review) {
  $("#review-count").textContent = review.length || "";
  const list = $("#review-list");
  list.replaceChildren();
  if (!review.length) {
    list.innerHTML = `<p class="empty">Queue is empty — nothing needs review.</p>`;
    return;
  }
  for (const { material, record } of review) {
    // reason comes from the record itself: conflict_reason when set (§6
    // conflicts), otherwise derived from its low confidence.
    const reason = record.conflict_reason
      ?? `Low confidence (${Math.round(record.confidence * 100)}%) — ${record.color_groups.length} candidate buckets.`;
    const div = document.createElement("div");
    div.className = "review-item";
    div.innerHTML = `
      <b>${material.swatch_name}</b> <span class="muted">· ${material.company ?? ""} · source: ${record.source}</span>
      <div class="reason">${reason}</div>
      <div class="suggested"></div>
      <button class="btn approve">Approve selected</button>
      <button class="btn secondary dismiss">Dismiss</button>`;
    const sug = div.querySelector(".suggested");
    const selected = new Set(record.color_groups);
    for (const b of record.color_groups) {
      const chip = document.createElement("span");
      chip.className = "chip selectable on";
      chip.innerHTML = `<span class="dot" style="background:${BUCKET_CSS[b] || "#ccc"}"></span>${b}`;
      chip.onclick = () => {
        chip.classList.toggle("on");
        chip.classList.contains("on") ? selected.add(b) : selected.delete(b);
      };
      sug.appendChild(chip);
    }
    div.querySelector(".approve").onclick = async () => {
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

function renderClassifySelect(items) {
  const sel = $("#classify-product");
  sel.replaceChildren(
    ...items.map((item) =>
      Object.assign(document.createElement("option"), {
        value: idOf(item),
        textContent: `${item.swatch_name ?? item.material_id} — ${item.company ?? "?"}${item.color_groups.length ? "" : " (unclassified)"}`,
      }),
    ),
  );
}

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
    refreshAdmin();
  } catch (err) {
    out.innerHTML = `<div class="flash warn">⚠️ ${err.message}</div>`;
  }
};

// initial load
refreshAdmin();
