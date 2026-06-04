// Demo frontend logic. Vanilla JS, talks to the FastAPI /api/* endpoints.

const $ = (sel) => document.querySelector(sel);

// Rough display color per bucket, for tag chips.
const BUCKET_CSS = {
  red: "#d04545", orange: "#e07b39", yellow: "#e3c33e", green: "#5a9a5e",
  blue: "#4a72c4", purple: "#8c5fb5", grey: "#9aa0a8", white: "#f5f5f2",
  black: "#26282b", brown: "#8a5a3b",
};

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
const tagChip = (tag, onRemove) => {
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.innerHTML = `<span class="dot" style="background:${BUCKET_CSS[tag] || "#ccc"}"></span>${tag}`;
  if (onRemove) {
    const x = document.createElement("span");
    x.className = "x";
    x.textContent = "×";
    x.title = "remove tag";
    x.onclick = onRemove;
    chip.appendChild(x);
  }
  return chip;
};

const productCard = (p) => {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <div class="swatch" style="background:${p.hex}"></div>
    <div class="body">
      <div class="name">${p.name}</div>
      <div class="sub">${p.product} · ${p.company}</div>
      <div class="tags"></div>
    </div>`;
  const tags = card.querySelector(".tags");
  p.tags.forEach((t) => tags.appendChild(tagChip(t)));
  if (!p.tags.length) tags.innerHTML = `<span class="muted">no color tags yet</span>`;
  return card;
};

// ---------- search tab ----------
$("#search-form").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("#search-input").value;
  const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
  const meta = $("#search-meta");
  if (data.matched_via === "synonym") meta.textContent = `“${data.query}” → ${data.bucket} · ${data.products.length} result(s)`;
  else if (data.matched_via === "bucket") meta.textContent = `color: ${data.bucket} · ${data.products.length} result(s)`;
  else if (data.matched_via === "text") meta.textContent = `text match · ${data.products.length} result(s)`;
  else meta.textContent = "";

  const out = $("#search-results");
  out.replaceChildren(...data.products.map(productCard));
  if (!data.products.length && q.trim()) out.innerHTML = `<p class="empty">No matches — is anything tagged “${q}” yet? (Check the Admin tab.)</p>`;
};

// ---------- admin tab ----------
async function refreshAdmin() {
  const [products, review, buckets] = await Promise.all([
    api("/api/products"), api("/api/review"), api("/api/buckets"),
  ]);

  // bucket datalist for add-tag inputs
  $("#bucket-list").replaceChildren(
    ...buckets.map((b) => Object.assign(document.createElement("option"), { value: b })),
  );

  renderReview(review, products);
  renderProducts(products);
  renderClassifySelect(products);
}

function renderProducts(products) {
  const tbody = $("#products-table tbody");
  tbody.replaceChildren();
  for (const p of products) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><div class="mini-swatch" style="background:${p.hex}"></div></td>
      <td><b>${p.name}</b></td>
      <td>${p.product}</td>
      <td>${p.company}</td>
      <td class="tags-cell"></td>`;
    const cell = tr.querySelector(".tags-cell");
    p.tags.forEach((t) =>
      cell.appendChild(tagChip(t, async () => {
        await api(`/api/products/${p.id}/tags/${t}`, { method: "DELETE" });
        refreshAdmin();
      })),
    );
    // inline add-tag input (suggests the 10 buckets, Enter to add)
    const input = document.createElement("input");
    input.className = "add-tag";
    input.placeholder = "+ tag";
    input.setAttribute("list", "bucket-list");
    input.onkeydown = async (e) => {
      if (e.key === "Enter" && input.value.trim()) {
        e.preventDefault();
        await api(`/api/products/${p.id}/tags`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tag: input.value }),
        });
        refreshAdmin();
      }
    };
    cell.appendChild(input);
    tbody.appendChild(tr);
  }
}

function renderReview(review, products) {
  $("#review-count").textContent = review.length || "";
  const list = $("#review-list");
  list.replaceChildren();
  if (!review.length) {
    list.innerHTML = `<p class="empty">Queue is empty — nothing needs review. 🎉</p>`;
    return;
  }
  for (const item of review) {
    const p = products.find((x) => x.id === item.product_id);
    const div = document.createElement("div");
    div.className = "review-item";
    div.innerHTML = `
      <b>${p ? p.name : "?"}</b> <span class="muted">· ${p ? p.product : ""}</span>
      <div class="reason">${item.reason}</div>
      <div class="suggested"></div>
      <button class="btn approve">Approve selected</button>
      <button class="btn secondary dismiss">Dismiss</button>`;
    const sug = div.querySelector(".suggested");
    // suggested buckets are toggleable chips, all selected by default
    const selected = new Set(item.suggested.map((s) => s.bucket));
    for (const s of item.suggested) {
      const chip = document.createElement("span");
      chip.className = "chip selectable on";
      chip.innerHTML = `<span class="dot" style="background:${s.css}"></span>${s.bucket} ${(s.coverage * 100).toFixed(0)}%`;
      chip.onclick = () => {
        chip.classList.toggle("on");
        chip.classList.contains("on") ? selected.add(s.bucket) : selected.delete(s.bucket);
      };
      sug.appendChild(chip);
    }
    div.querySelector(".approve").onclick = async () => {
      await api(`/api/review/${item.id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ color_groups: [...selected] }),
      });
      refreshAdmin();
    };
    div.querySelector(".dismiss").onclick = async () => {
      await api(`/api/review/${item.id}/dismiss`, { method: "POST" });
      refreshAdmin();
    };
    list.appendChild(div);
  }
}

function renderClassifySelect(products) {
  const sel = $("#classify-product");
  sel.replaceChildren(
    ...products.map((p) =>
      Object.assign(document.createElement("option"), {
        value: p.id,
        textContent: `${p.name} — ${p.product}${p.tags.length ? "" : " (untagged)"}`,
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
    const data = await api(`/api/classify/${$("#classify-product").value}`, { method: "POST", body: form });
    const chips = data.clusters
      .map((c) => `<span class="chip"><span class="dot" style="background:${c.css}"></span>${c.bucket} ${(c.coverage * 100).toFixed(0)}%</span>`)
      .join(" ");
    out.innerHTML = data.applied
      ? `<div class="flash">✅ Confident → tagged <b>${data.color_groups.join(", ")}</b> &nbsp;${chips}</div>`
      : `<div class="flash warn">🤔 Ambiguous (${data.color_groups.length} buckets) → sent to review queue &nbsp;${chips}</div>`;
    refreshAdmin();
  } catch (err) {
    out.innerHTML = `<div class="flash warn">⚠️ ${err.message}</div>`;
  }
};

// initial load
refreshAdmin();
