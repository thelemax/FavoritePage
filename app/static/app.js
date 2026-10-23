/* FavoritePage - frontend (vanilla JS).
   Données : /api/data (data.yaml) · Thème : /api/theme (theme.yaml) · Fonds : /api/backgrounds (config/fonds). */

const board = document.getElementById("board");
const tooltip = document.getElementById("tooltip");
const $ = id => document.getElementById(id);

const DEFAULT_THEME = {
  columns: 3,
  link: { width: null, show_icon: true, show_name: true, show_description: false, icon_size: 16 },
  fonts: { link: 14, description: 11, category: 15 },
  colors: { button: "#1c1e22", button_hover: "#464a50", text: "#f2f2f2", button_opacity: 0.88,
            panel: "#14181e", panel_opacity: 0.45 },
  background: { mode: "fixed", image: "", attachment: "fixed" }
};

let data = { columns: [] };
let theme = structuredClone(DEFAULT_THEME);
let backgrounds = [];   // fichiers de config/fonds
let randomBg = null;    // image tirée au hasard (une fois par chargement de page)
let preview = null;     // thème en cours d'édition (aperçu en direct)
let editing = false;
let current = null;     // contexte de la modale lien/catégorie ouverte
let drag = null;        // lien en cours de glisser-déposer
let categoryDrag = null; // catégorie en cours de glisser-déposer

const activeTheme = () => preview || theme;

/* ---------- API ---------- */
function errorMessage(body, res) {
  const d = body && body.detail;
  if (!d) return `${res.status} ${res.statusText}`;
  return typeof d === "string" ? d : JSON.stringify(d);
}

async function request(method, path, payload) {
  const res = await fetch(path, {
    method,
    cache: "no-store",
    headers: payload ? { "Content-Type": "application/json" } : {},
    body: payload ? JSON.stringify(payload) : undefined
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(errorMessage(body, res));
  return body;
}

async function reload() {
  try {
    const [d, t, b] = await Promise.all([
      request("GET", "/api/data"), request("GET", "/api/theme"), request("GET", "/api/backgrounds")
    ]);
    data = d; theme = t; backgrounds = b;
    applyTheme();
    render();
  } catch (e) {
    console.error(e);
    alert("Impossible de charger les données : " + e.message);
  }
}

/* Mutation de data.yaml : la réponse contient les données complètes */
async function api(method, path, payload) {
  try {
    data = await request(method, path, payload);
    render();
    return true;
  } catch (e) {
    alert("Erreur : " + e.message);
    await reload(); // resynchronise l'affichage avec les fichiers
    return false;
  }
}

const catPath = (ci, ki) => `/api/columns/${ci}/categories` + (ki >= 0 ? `/${ki}` : "");
const linkPath = (ci, ki, li) => `${catPath(ci, ki)}/links` + (li >= 0 ? `/${li}` : "");

/* ---------- Thème ---------- */
function hexRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/* Nom simple => fichier du dossier `dir` ; URL absolue ou chemin => tel quel */
function resolveImage(value, dir) {
  if (!value) return "";
  if (/^(https?:|data:|\/)/i.test(value)) return value;
  return `/${dir}/` + value.split("/").map(encodeURIComponent).join("/");
}

function backgroundUrl(bg) {
  if (bg.mode === "random" && backgrounds.length) {
    if (!backgrounds.includes(randomBg)) randomBg = backgrounds[Math.floor(Math.random() * backgrounds.length)];
    return resolveImage(randomBg, "fonds");
  }
  return resolveImage(bg.image, "fonds");
}

function applyTheme() {
  const t = activeTheme(), c = t.colors, s = document.documentElement.style;
  s.setProperty("--chip-bg", hexRgba(c.button, c.button_opacity));
  s.setProperty("--chip-bg-hover", hexRgba(c.button_hover, Math.min(1, c.button_opacity + 0.04)));
  s.setProperty("--chip-text", c.text);
  s.setProperty("--panel-bg", hexRgba(c.panel, c.panel_opacity));
  const f = t.fonts || DEFAULT_THEME.fonts;
  s.setProperty("--icon-size", (t.link.icon_size || 16) + "px");
  s.setProperty("--font-link", f.link + "px");
  s.setProperty("--font-desc", f.description + "px");
  s.setProperty("--font-category", f.category + "px");
  const url = backgroundUrl(t.background);
  document.body.style.backgroundImage = url ? `url("${url.replace(/"/g, '\\"')}")` : "";
  document.body.style.backgroundAttachment = t.background.attachment === "scroll" ? "scroll" : "fixed";
}

/* Réglages effectifs d'un lien : style du lien > thème */
function effective(l) {
  const t = activeTheme().link, s = l.style || {};
  const pick = k => (s[k] === undefined || s[k] === null) ? t[k] : s[k];
  const e = { show_icon: pick("show_icon"), show_name: pick("show_name"), show_description: pick("show_description") };
  if (!e.show_icon && !e.show_name) e.show_name = true; // jamais de lien vide
  e.width = (s.width === undefined || s.width === null) ? t.width : (s.width || null);
  return e;
}

/* ---------- Rendu ---------- */
function render() {
  board.innerHTML = "";
  board.style.setProperty("--cols", Math.max(1, data.columns.length));
  data.columns.forEach((col, ci) => {
    const colEl = document.createElement("section");
    colEl.className = "column";

    col.categories.forEach((c, ki) => {
      const wrap = document.createElement("div");
      wrap.className = "category-item";
      wrap.innerHTML = `
        <div class="category-head">
          <span class="category-title"></span>
          <span class="category-tools">
            <button class="icon-btn" title="Ajouter un lien" data-act="add">+</button>
            <button class="icon-btn" title="Modifier la catégorie" data-act="edit">✎</button>
          </span>
        </div>
        <div class="panel"></div>`;
      wrap.querySelector(".category-title").textContent = c.name;
      wrap.querySelector('[data-act="add"]').onclick = () => openLink(ci, ki, -1);
      wrap.querySelector('[data-act="edit"]').onclick = () => openCat(ci, ki);
      const head = wrap.querySelector(".category-head");
      head.classList.add("drag-handle");
      head.draggable = editing;
      head.addEventListener("dragstart", e => {
        if (!editing) {
          e.preventDefault();
          return;
        }
        categoryDrag = { ci, ki };
        wrap.classList.add("dragging");
        hideTooltip();
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", `cat:${ci}:${ki}`);
      });
      head.addEventListener("dragend", () => {
        wrap.classList.remove("dragging");
        categoryDrag = null;
        board.querySelectorAll(".category-item.drop-target, .column.drop-target").forEach(el => el.classList.remove("drop-target"));
      });

      const panel = wrap.querySelector(".panel");
      c.links.forEach((l, li) => panel.appendChild(linkEl(l, ci, ki, li)));
      setupDrop(panel, ci, ki);
      setupCategoryDrop(wrap, colEl, ci, ki);
      colEl.appendChild(wrap);
    });

    const add = document.createElement("div");
    add.className = "new-category";
    add.textContent = "+ Nouvelle catégorie";
    add.onclick = () => openCat(ci, -1);
    colEl.appendChild(add);
    board.appendChild(colEl);
  });
}

function iconSrc(l) {
  if (l.style && l.style.icon) return resolveImage(l.style.icon, "icons");
  if (/^https?:\/\//i.test(l.url)) return "/api/favicon?url=" + encodeURIComponent(l.url);
  return "";
}

function letterIcon(name) {
  const s = document.createElement("span");
  s.className = "link-letter";
  s.textContent = (name.trim()[0] || "?");
  return s;
}

function linkEl(l, ci, ki, li) {
  const e = effective(l);
  const s = l.style || {};
  const a = document.createElement("a");
  a.className = "link" + (l.hidden ? " hidden-link" : "") + (e.show_name ? "" : " icon-only") + (e.width ? " fixed-w" : "");
  a.href = l.url || "#";
  a.target = "_blank";
  a.rel = "noopener";
  a.draggable = editing;
  if (e.width) a.style.width = e.width + "px";
  if (s.color) {
    const bg = hexRgba(s.color, activeTheme().colors.button_opacity);
    a.style.setProperty("--chip-bg", bg);
    a.style.setProperty("--chip-bg-hover", bg);
    a.classList.add("custom-bg");
  }
  if (s.text) a.style.color = s.text;
  if (s.icon_size) a.style.setProperty("--icon-size", s.icon_size + "px");
  if (s.font_size) a.style.setProperty("--font-link", s.font_size + "px");

  if (e.show_icon) {
    const src = iconSrc(l);
    if (src) {
      const img = document.createElement("img");
      img.className = "link-icon";
      img.alt = "";
      img.loading = "lazy";
      img.draggable = false;
      img.src = src;
      img.onerror = () => img.replaceWith(letterIcon(l.name));
      a.appendChild(img);
    } else {
      a.appendChild(letterIcon(l.name));
    }
  }
  if (e.show_name) {
    const text = document.createElement("span");
    text.className = "link-text";
    const name = document.createElement("span");
    name.className = "link-name";
    name.textContent = l.name;
    text.appendChild(name);
    if (e.show_description && l.description) {
      const desc = document.createElement("span");
      desc.className = "link-desc";
      desc.textContent = l.description;
      text.appendChild(desc);
    }
    a.appendChild(text);
  }

  const badge = document.createElement("span");
  badge.className = "edit-badge";
  badge.textContent = "✎";
  a.appendChild(badge);

  a.addEventListener("click", ev => {
    if (editing) { ev.preventDefault(); openLink(ci, ki, li); }
    else if (!l.url) ev.preventDefault();
  });
  a.addEventListener("mouseenter", () => showTooltip(l, e));
  a.addEventListener("mousemove", moveTooltip);
  a.addEventListener("mouseleave", hideTooltip);
  a.addEventListener("dragstart", ev => {
    drag = { ci, ki, li };
    a.classList.add("dragging");
    hideTooltip();
    ev.dataTransfer.effectAllowed = "move";
  });
  a.addEventListener("dragend", () => { a.classList.remove("dragging"); drag = null; });
  return a;
}

function setupDrop(panel, ci, ki) {
  panel.addEventListener("dragover", e => { if (drag && !categoryDrag) { e.preventDefault(); panel.classList.add("drop-target"); } });
  panel.addEventListener("dragleave", e => { if (!panel.contains(e.relatedTarget)) panel.classList.remove("drop-target"); });
  panel.addEventListener("drop", e => {
    e.preventDefault();
    panel.classList.remove("drop-target");
    if (!drag || categoryDrag) return;
    // position d'insertion : avant le lien survolé, sinon à la fin
    const targets = [...panel.querySelectorAll(".link")];
    const over = e.target.closest(".link");
    const index = over ? targets.indexOf(over) : targets.length;
    const source = drag;
    drag = null;
    api("POST", "/api/links/move", { source, target: { ci, ki, index } });
  });
}

function setupCategoryDrop(wrap, colEl, ci, ki) {
  wrap.addEventListener("dragover", e => {
    if (!categoryDrag || drag) return;
    e.preventDefault();
    colEl.classList.remove("drop-target");
    wrap.classList.add("drop-target");
  });
  wrap.addEventListener("dragleave", e => {
    if (!wrap.contains(e.relatedTarget)) wrap.classList.remove("drop-target");
  });
  wrap.addEventListener("drop", e => {
    if (!categoryDrag || drag) return;
    e.preventDefault();
    e.stopPropagation();
    wrap.classList.remove("drop-target");
    colEl.classList.remove("drop-target");
    const rect = wrap.getBoundingClientRect();
    const before = e.clientY < (rect.top + rect.height / 2);
    const index = before ? ki : ki + 1;
    const source = categoryDrag;
    categoryDrag = null;
    api("POST", "/api/categories/move", { source, target: { ci, index } });
  });

  colEl.addEventListener("dragover", e => {
    if (!categoryDrag || drag) return;
    if (e.target.closest(".category-item")) return;
    e.preventDefault();
    colEl.classList.add("drop-target");
  });
  colEl.addEventListener("dragleave", e => {
    if (!colEl.contains(e.relatedTarget)) colEl.classList.remove("drop-target");
  });
  colEl.addEventListener("drop", e => {
    if (!categoryDrag || drag) return;
    if (e.target.closest(".category-item")) return;
    e.preventDefault();
    colEl.classList.remove("drop-target");
    const source = categoryDrag;
    categoryDrag = null;
    api("POST", "/api/categories/move", {
      source,
      target: { ci, index: data.columns[ci].categories.length }
    });
  });
}

/* ---------- Tooltip ---------- */
function showTooltip(l, e) {
  if (drag) return;
  let text = l.description || l.name;
  if (!e.show_name && l.description) text = `${l.name} — ${l.description}`;
  tooltip.querySelector(".tt-desc").textContent = text;
  tooltip.querySelector(".tt-url").textContent = l.url || "";
  tooltip.style.display = "block";
}
function moveTooltip(e) {
  const x = Math.min(e.clientX + 14, window.innerWidth - tooltip.offsetWidth - 8);
  tooltip.style.left = x + "px";
  tooltip.style.top = (e.clientY + 18) + "px";
}
function hideTooltip() { tooltip.style.display = "none"; }

/* ---------- Modales lien / catégorie ---------- */
const linkModal = $("linkModal");
const catModal = $("catModal");
const themeModal = $("themeModal");

function openModal(m, focusId) {
  hideTooltip();
  m.classList.add("open");
  if (focusId) setTimeout(() => { const f = $(focusId); f.focus(); f.setSelectionRange(f.value.length, f.value.length); }, 0);
}
function closeModals() {
  linkModal.classList.remove("open");
  catModal.classList.remove("open");
  current = null;
  if (themeModal.classList.contains("open")) {
    themeModal.classList.remove("open");
    preview = null;      // annule l'aperçu
    applyTheme();
    render();
  }
}

const triGet = v => (v === true ? "1" : v === false ? "0" : "");
const triSet = v => (v === "" ? null : v === "1");

function syncColorToggles() {
  $("lsColor").disabled = !$("lsColorOn").checked;
  $("lsText").disabled = !$("lsTextOn").checked;
}
$("lsColorOn").onchange = syncColorToggles;
$("lsTextOn").onchange = syncColorToggles;

function openLink(ci, ki, li) {
  current = { ci, ki, li };
  const l = li >= 0 ? data.columns[ci].categories[ki].links[li]
                    : { name: "", url: "", description: "", hidden: false, style: {} };
  const s = l.style || {};
  $("linkModalTitle").textContent = li >= 0 ? "Modifier le lien" : "Nouveau lien";
  $("linkName").value = l.name;
  $("linkUrl").value = l.url;
  $("linkDesc").value = l.description;
  $("linkHidden").checked = l.hidden;
  $("lsIcon").value = s.icon || "";
  $("lsShowIcon").value = triGet(s.show_icon);
  $("lsShowName").value = triGet(s.show_name);
  $("lsShowDesc").value = triGet(s.show_description);
  $("lsWidth").value = s.width ?? "";
  $("lsIconSize").value = s.icon_size ?? "";
  $("lsFontSize").value = s.font_size ?? "";
  $("lsColorOn").checked = !!s.color;
  $("lsColor").value = s.color || theme.colors.button;
  $("lsTextOn").checked = !!s.text;
  $("lsText").value = s.text || theme.colors.text;
  syncColorToggles();
  $("linkAppearance").open = Object.keys(s).length > 0;
  $("linkDelete").style.visibility = li >= 0 ? "visible" : "hidden";
  openModal(linkModal, "linkName");
}

function openCat(ci, ki) {
  current = { ci, ki };
  $("catModalTitle").textContent = ki >= 0 ? "Modifier la catégorie" : "Nouvelle catégorie";
  $("catName").value = ki >= 0 ? data.columns[ci].categories[ki].name : "";
  $("catDelete").style.display = ki >= 0 ? "" : "none";
  openModal(catModal, "catName");
}

$("linkForm").addEventListener("submit", async e => {
  e.preventDefault();
  const { ci, ki, li } = current;
  const width = $("lsWidth").value.trim();
  const optNum = (id, min, max) => { const v = $(id).value.trim(); return v === "" ? null : clamp(v, min, max, null); };
  const link = {
    name: $("linkName").value.trim(),
    url: $("linkUrl").value.trim(),
    description: $("linkDesc").value.trim(),
    hidden: $("linkHidden").checked,
    style: {
      icon: $("lsIcon").value.trim() || null,
      show_icon: triSet($("lsShowIcon").value),
      show_name: triSet($("lsShowName").value),
      show_description: triSet($("lsShowDesc").value),
      width: width === "" ? null : Math.max(0, Math.min(600, parseInt(width, 10) || 0)),
      icon_size: optNum("lsIconSize", 10, 64),
      font_size: optNum("lsFontSize", 8, 32),
      color: $("lsColorOn").checked ? $("lsColor").value : null,
      text: $("lsTextOn").checked ? $("lsText").value : null
    }
  };
  if (!link.name) return;
  closeModals();
  await api(li >= 0 ? "PUT" : "POST", linkPath(ci, ki, li), link);
});
$("linkDelete").onclick = async () => {
  const { ci, ki, li } = current;
  const name = data.columns[ci].categories[ki].links[li].name;
  if (!confirm(`Supprimer le lien « ${name} » ?`)) return;
  closeModals();
  await api("DELETE", linkPath(ci, ki, li));
};

$("catForm").addEventListener("submit", async e => {
  e.preventDefault();
  const { ci, ki } = current;
  const name = $("catName").value.trim();
  if (!name) return;
  closeModals();
  await api(ki >= 0 ? "PUT" : "POST", catPath(ci, ki), { name });
});
$("catDelete").onclick = async () => {
  const { ci, ki } = current;
  const c = data.columns[ci].categories[ki];
  if (!confirm(`Supprimer la catégorie « ${c.name} » et ses ${c.links.length} lien(s) ?`)) return;
  closeModals();
  await api("DELETE", catPath(ci, ki));
};

/* ---------- Modale thème ---------- */
const URL_OPTION = "__url__";
const clamp = (v, min, max, def) => { const n = parseInt(v, 10); return isNaN(n) ? def : Math.max(min, Math.min(max, n)); };

function fillThemeForm(t) {
  $("thColumns").value = t.columns;
  $("thWidthOn").checked = t.link.width !== null;
  $("thWidth").value = t.link.width ?? 160;
  $("thShowIcon").checked = t.link.show_icon;
  $("thShowName").checked = t.link.show_name;
  $("thShowDesc").checked = t.link.show_description;
  const f = t.fonts || DEFAULT_THEME.fonts;
  $("thIconSize").value = t.link.icon_size || 16;
  $("thFontLink").value = f.link;
  $("thFontDesc").value = f.description;
  $("thFontCat").value = f.category;
  $("thButton").value = t.colors.button;
  $("thButtonHover").value = t.colors.button_hover;
  $("thText").value = t.colors.text;
  $("thButtonOpacity").value = Math.round(t.colors.button_opacity * 100);
  $("thPanel").value = t.colors.panel;
  $("thPanelOpacity").value = Math.round(t.colors.panel_opacity * 100);
  $("thBgMode").value = t.background.mode;
  $("thBgAttach").value = t.background.attachment;

  const sel = $("thBgSelect");
  sel.innerHTML = "";
  const opt = (value, label) => { const o = document.createElement("option"); o.value = value; o.textContent = label; sel.appendChild(o); };
  opt("", "(aucune — dégradé par défaut)");
  backgrounds.forEach(f => opt(f, f));
  opt(URL_OPTION, "URL personnalisée…");
  const img = t.background.image;
  sel.value = !img ? "" : backgrounds.includes(img) ? img : URL_OPTION;
  $("thBgUrl").value = sel.value === URL_OPTION ? img : "";
  syncThemeForm();
}

function readThemeForm() {
  const sel = $("thBgSelect").value;
  return {
    columns: clamp($("thColumns").value, 1, 6, theme.columns),
    link: {
      width: $("thWidthOn").checked ? clamp($("thWidth").value, 40, 600, 160) : null,
      show_icon: $("thShowIcon").checked,
      show_name: $("thShowName").checked,
      show_description: $("thShowDesc").checked,
      icon_size: clamp($("thIconSize").value, 10, 64, 16)
    },
    fonts: {
      link: clamp($("thFontLink").value, 8, 32, 14),
      description: clamp($("thFontDesc").value, 8, 32, 11),
      category: clamp($("thFontCat").value, 8, 40, 15)
    },
    colors: {
      button: $("thButton").value,
      button_hover: $("thButtonHover").value,
      text: $("thText").value,
      button_opacity: $("thButtonOpacity").value / 100,
      panel: $("thPanel").value,
      panel_opacity: $("thPanelOpacity").value / 100
    },
    background: {
      mode: $("thBgMode").value,
      image: sel === URL_OPTION ? $("thBgUrl").value.trim() : sel,
      attachment: $("thBgAttach").value
    }
  };
}

function syncThemeForm() {
  $("thWidth").disabled = !$("thWidthOn").checked;
  $("thButtonOpacityOut").textContent = $("thButtonOpacity").value + " %";
  $("thPanelOpacityOut").textContent = $("thPanelOpacity").value + " %";
  for (const id of ["thIconSize", "thFontLink", "thFontDesc", "thFontCat"]) $(id + "Out").textContent = $(id).value + " px";
  $("thBgUrl").style.display = $("thBgSelect").value === URL_OPTION ? "" : "none";
  const random = $("thBgMode").value === "random";
  $("thBgHint").textContent = random
    ? (backgrounds.length
        ? `${backgrounds.length} image(s) dans config/fonds : une est tirée au hasard à chaque chargement.`
        : "Aucune image dans config/fonds : l'image ci-dessus est utilisée.")
    : "Le nombre de colonnes est appliqué à l'enregistrement.";
}

function openTheme() {
  preview = structuredClone(theme);
  fillThemeForm(preview);
  openModal(themeModal);
}

$("themeForm").addEventListener("input", () => {
  syncThemeForm();
  preview = readThemeForm();
  applyTheme();
  render();
});

$("themeReset").onclick = () => {
  const t = structuredClone(DEFAULT_THEME);
  t.columns = theme.columns;
  fillThemeForm(t);
  preview = readThemeForm();
  applyTheme();
  render();
};

$("themeForm").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    const res = await request("PUT", "/api/theme", readThemeForm());
    theme = res.theme;
    data = res.data;
    themeModal.classList.remove("open");
    preview = null;
    applyTheme();
    render();
  } catch (err) {
    alert("Erreur : " + err.message); // la modale reste ouverte (ex. réduction de colonnes refusée)
  }
});

$("themeBtn").onclick = openTheme;

document.querySelectorAll("[data-close]").forEach(b => b.onclick = closeModals);
document.querySelectorAll(".overlay").forEach(o => o.addEventListener("mousedown", e => { if (e.target === o) closeModals(); }));
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModals(); });

/* ---------- Mode édition ---------- */
$("editBtn").onclick = () => {
  editing = !editing;
  document.body.classList.toggle("editing", editing);
  $("editBtn").classList.toggle("active", editing);
  render();
};

/* ---------- Barre de recherche Google ---------- */
const searchInput = $("searchInput");

// Mode IA de Google = recherche avec udm=50
$("aiBtn").onclick = () => {
  const q = searchInput.value.trim();
  location.href = "https://www.google.com/search?udm=50" + (q ? "&q=" + encodeURIComponent(q) : "");
};

// Recherche vocale via l'API Web Speech (Chrome / Edge), bouton masqué si non supportée
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (Recognition) {
  $("voiceBtn").onclick = () => {
    const rec = new Recognition();
    rec.lang = "fr-FR";
    rec.onstart = () => $("voiceBtn").classList.add("listening");
    rec.onend = () => $("voiceBtn").classList.remove("listening");
    rec.onresult = e => {
      searchInput.value = e.results[0][0].transcript;
      $("searchForm").submit();
    };
    rec.start();
  };
} else {
  $("voiceBtn").style.display = "none";
}

/* Recharge au retour sur l'onglet (prise en compte des éditions manuelles des YAML) */
window.addEventListener("focus", () => { if (!current && !drag && !categoryDrag && !preview) reload(); });

reload();

