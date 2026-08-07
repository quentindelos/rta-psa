const form = document.getElementById("ask-form");
const queryInput = document.getElementById("query");
const fuelSelect = document.getElementById("fuel");
const vehicleSelect = document.getElementById("vehicle");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const answerCard = document.getElementById("answer-card");
const originBadge = document.getElementById("origin-badge");
const answerText = document.getElementById("answer-text");
const sourcesEl = document.getElementById("sources");
const webSourcesEl = document.getElementById("web-sources");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const themeToggle = document.getElementById("theme-toggle");
const historyEl = document.getElementById("history");
const historyListEl = document.getElementById("history-list");
const searchStepsEl = document.getElementById("search-steps");
const searchStepsList = document.getElementById("search-steps-list");

const THEME_KEY = "rta-psa-theme";
const HISTORY_KEY = "rta-psa-history";
const HISTORY_MAX = 12;

// Variantes par carburant — le formulaire demande d'abord essence/diesel (voir index.html)
// avant d'afficher cette liste, pour ne jamais mélanger les deux moitiés de la RTA.
const VEHICLE_OPTIONS = {
  essence: {
    "Citroën Saxo": [
      ["Citroën Saxo 1.0i", "Saxo 1.0i"],
      ["Citroën Saxo 1.1i", "Saxo 1.1i"],
      ["Citroën Saxo 1.4i", "Saxo 1.4i"],
      ["Citroën Saxo 1.6i", "Saxo 1.6i"],
      ["Citroën Saxo 1.6i 16v (VTS)", "Saxo 1.6i 16v (VTS) — version inconnue"],
      ["Citroën Saxo 1.6i 16v (VTS) — moteur TU5J4 L3", "Saxo VTS — moteur TU5J4 L3"],
      ["Citroën Saxo 1.6i 16v (VTS) — moteur TU5J4 L4", "Saxo VTS — moteur TU5J4 L4"],
    ],
    "Peugeot 106": [
      ["Peugeot 106 1.0i", "106 1.0i"],
      ["Peugeot 106 1.1i", "106 1.1i"],
      ["Peugeot 106 1.4i", "106 1.4i"],
      ["Peugeot 106 1.6i", "106 1.6i"],
      ["Peugeot 106 1.6i 16v (S16)", "106 1.6i 16v (S16) — version inconnue"],
      ["Peugeot 106 1.6i 16v (S16) — moteur TU5J4 L3", "106 S16 — moteur TU5J4 L3"],
      ["Peugeot 106 1.6i 16v (S16) — moteur TU5J4 L4", "106 S16 — moteur TU5J4 L4"],
      ["Peugeot 106 Rallye 1.3i 8v (Phase 1)", "106 Rallye Phase 1 — 1.3i 8v"],
      ["Peugeot 106 Rallye 1.6i 8v (Phase 2)", "106 Rallye Phase 2 — 1.6i 8v"],
    ],
  },
  diesel: {
    "Citroën Saxo": [["Citroën Saxo Diesel", "Saxo Diesel"]],
    "Peugeot 106": [["Peugeot 106 Diesel", "106 Diesel"]],
  },
};

function populateVehicleOptions(fuel) {
  vehicleSelect.innerHTML = "";
  if (!fuel || !VEHICLE_OPTIONS[fuel]) {
    vehicleSelect.disabled = true;
    vehicleSelect.appendChild(new Option("Choisis d'abord le carburant", ""));
    return;
  }

  vehicleSelect.disabled = false;
  vehicleSelect.appendChild(
    new Option(`Version non précisée (toutes les ${fuel})`, "")
  );
  for (const [group, options] of Object.entries(VEHICLE_OPTIONS[fuel])) {
    const optgroup = document.createElement("optgroup");
    optgroup.label = group;
    for (const [value, label] of options) {
      optgroup.appendChild(new Option(label, value));
    }
    vehicleSelect.appendChild(optgroup);
  }
}

fuelSelect.addEventListener("change", () => populateVehicleOptions(fuelSelect.value));

function inferFuel(vehicle) {
  // Historique enregistré avant l'ajout du sélecteur carburant : on déduit du texte.
  if (!vehicle) return "";
  return /diesel/i.test(vehicle) ? "diesel" : "essence";
}

function loadHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
    // Anciennes entrées enregistrées avant l'ajout du contexte véhicule/carburant : de
    // simples chaînes, ou des objets sans champ fuel.
    return raw.map((entry) => {
      if (typeof entry === "string") return { query: entry, vehicle: "", vehicleLabel: "", fuel: "" };
      return { fuel: inferFuel(entry.vehicle), ...entry };
    });
  } catch {
    return [];
  }
}

function sameEntry(a, query, vehicle) {
  return a.query === query && a.vehicle === vehicle;
}

function saveQueryToHistory(query, vehicle, vehicleLabel, fuel) {
  const history = loadHistory().filter((entry) => !sameEntry(entry, query, vehicle));
  history.unshift({ query, vehicle, vehicleLabel, fuel });
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, HISTORY_MAX)));
  renderHistory();
}

function removeQueryFromHistory(query, vehicle) {
  const history = loadHistory().filter((entry) => !sameEntry(entry, query, vehicle));
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  renderHistory();
}

function renderHistory() {
  const history = loadHistory();
  historyEl.hidden = history.length === 0;
  historyListEl.innerHTML = "";
  if (history.length === 0) return;

  // Construit les éléments via le DOM (pas de HTML avec du texte utilisateur
  // interpolé) : une question peut contenir des guillemets, ça casserait un
  // attribut construit par concaténation de chaînes.
  history.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "history-item";

    const textBtn = document.createElement("button");
    textBtn.type = "button";
    textBtn.className = "history-item-text";

    const queryLabel = document.createElement("span");
    queryLabel.className = "history-item-query";
    queryLabel.textContent = entry.query;
    textBtn.appendChild(queryLabel);

    if (entry.vehicleLabel) {
      const vehicleTag = document.createElement("span");
      vehicleTag.className = "history-item-vehicle";
      vehicleTag.textContent = entry.vehicleLabel;
      textBtn.appendChild(vehicleTag);
    }

    textBtn.addEventListener("click", () => {
      queryInput.value = entry.query;
      fuelSelect.value = entry.fuel || "";
      populateVehicleOptions(entry.fuel);
      vehicleSelect.value = entry.vehicle;
      form.requestSubmit();
    });

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "history-item-remove";
    removeBtn.setAttribute("aria-label", "Supprimer cette question");
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", () => {
      removeQueryFromHistory(entry.query, entry.vehicle);
    });

    item.append(textBtn, removeBtn);
    historyListEl.appendChild(item);
  });
}

renderHistory();

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeToggle.textContent = theme === "dark" ? "☀️" : "🌙";
}

applyTheme(localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light");

themeToggle.addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
});

let currentEventSource = null;

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }

  setLoading(true);
  answerCard.hidden = true;
  resetSearchSteps();
  showStatus("Recherche en cours…", false);

  const fuel = fuelSelect.value;
  const vehicle = vehicleSelect.value;
  const vehicleLabel = vehicle ? vehicleSelect.options[vehicleSelect.selectedIndex].text : "";
  const params = new URLSearchParams({ q: query });
  if (fuel) params.set("fuel", fuel);
  if (vehicle) params.set("vehicle", vehicle);

  const es = new EventSource(`/api/ask/stream?${params.toString()}`);
  currentEventSource = es;

  es.addEventListener("step", (event) => {
    addSearchStep(JSON.parse(event.data).message);
  });

  es.addEventListener("result", (event) => {
    es.close();
    currentEventSource = null;
    renderAnswer(JSON.parse(event.data));
    saveQueryToHistory(query, vehicle, vehicleLabel, fuel);
    setLoading(false);
  });

  es.onerror = () => {
    es.close();
    currentEventSource = null;
    showStatus("Erreur : la recherche a échoué.", true);
    setLoading(false);
  };
});

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  submitBtn.textContent = isLoading ? "Recherche…" : "Chercher";
}

function showStatus(message, isError) {
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.classList.toggle("status-error", isError);
}

function resetSearchSteps() {
  searchStepsList.innerHTML = "";
  searchStepsEl.hidden = true;
}

function addSearchStep(message) {
  statusEl.hidden = true;
  searchStepsEl.hidden = false;
  const li = document.createElement("li");
  li.textContent = message;
  searchStepsList.appendChild(li);
}

function renderAnswer(data) {
  statusEl.hidden = true;
  answerCard.hidden = false;
  answerText.innerHTML = renderMarkdown(data.answer);

  if (data.answer_origin === "web_only") {
    originBadge.className = "origin-badge origin-badge--web";
    originBadge.textContent = "🌐 Non trouvé dans la RTA — réponse basée sur le web";
    sourcesEl.innerHTML = "";
  } else {
    originBadge.className = "origin-badge origin-badge--rta";
    originBadge.textContent = "📖 RTA + 🌐 Web";
    renderSources(data.sources);
  }
  renderWebSources(data.web_sources);
}

function renderSources(sources) {
  if (!sources || sources.length === 0) {
    sourcesEl.innerHTML = "";
    return;
  }

  sourcesEl.innerHTML = sources
    .flatMap((source) => {
      if (source.schematic_image_urls && source.schematic_image_urls.length > 0) {
        return source.schematic_image_urls.map((url, i) => {
          const label =
            source.schematic_image_urls.length > 1 ? `Schéma ${i + 1} — page ${source.page_num}` : `Schéma — page ${source.page_num}`;
          return `
            <figure class="source-card source-card--schematic">
              <img
                class="source-image"
                src="${url}"
                alt="${label}"
                loading="lazy"
                data-full="${url}"
              />
              <figcaption>
                ${label}
                <a class="full-page-link" data-full="${source.page_image_url}" href="#">page complète</a>
              </figcaption>
            </figure>
          `;
        });
      }
      return [
        `
        <figure class="source-card">
          <img
            class="source-image"
            src="${source.page_image_url}"
            alt="Page ${source.page_num}"
            loading="lazy"
            data-full="${source.page_image_url}"
          />
          <figcaption>Page ${source.page_num}</figcaption>
        </figure>
      `,
      ];
    })
    .join("");

  sourcesEl.querySelectorAll("[data-full]").forEach((el) => {
    el.addEventListener("click", (event) => {
      event.preventDefault();
      openLightbox(el.dataset.full);
    });
  });
}

function renderWebSources(webSources) {
  if (!webSources || webSources.length === 0) {
    webSourcesEl.innerHTML = "";
    return;
  }

  webSourcesEl.innerHTML =
    "<p class='web-sources-label'>Sources :</p>" +
    "<ul>" +
    webSources
      .map(
        (s) =>
          `<li><a href="${s.url}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title)}</a></li>`
      )
      .join("") +
    "</ul>";
}

function openLightbox(src) {
  lightboxImg.src = src;
  lightbox.hidden = false;
}

lightbox.addEventListener("click", () => {
  lightbox.hidden = true;
  lightboxImg.src = "";
});

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function inlineFormat(line) {
  // gras uniquement (**texte**) — c'est le seul style markdown que Gemini utilise ici
  return escapeHtml(line).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

const TABLE_ROW_RE = /^\|(.+)\|$/;
const TABLE_SEPARATOR_RE = /^\|?(\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?$/;

function splitTableRow(row) {
  return row
    .split("|")
    .map((cell) => cell.trim())
    .filter((cell, index, cells) => !(cell === "" && (index === 0 || index === cells.length - 1)));
}

function renderTable(header, rows) {
  const thead = `<tr>${header.map((cell) => `<th>${inlineFormat(cell)}</th>`).join("")}</tr>`;
  const tbody = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${inlineFormat(cell)}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="answer-table-wrap"><table><thead>${thead}</thead><tbody>${tbody}</tbody></table></div>`;
}

// Petit moteur markdown maison : gras, listes numérotées/à puces, paragraphes.
// Volontairement minimal (pas de lib externe) pour ce que Gemini produit réellement.
function renderMarkdown(raw) {
  const lines = (raw || "").split("\n");
  const html = [];
  let paragraph = [];
  let i = 0;
  // Gemini écrit souvent chaque étape avec "1." (le renderer est censé
  // renuméroter), mais dès qu'un paragraphe ou une liste à puces s'intercale
  // entre deux étapes, on referme le <ol> — et un nouveau <ol> recommence à 1
  // en HTML. On fait donc continuer la numérotation entre les blocs.
  let nextOrderedNumber = 1;

  const flushParagraph = () => {
    if (paragraph.length) {
      html.push(`<p>${paragraph.join("<br>")}</p>`);
      paragraph = [];
    }
  };

  while (i < lines.length) {
    const trimmed = lines[i].trim();

    if (trimmed === "") {
      flushParagraph();
      i++;
      continue;
    }

    const tableHeader = trimmed.match(TABLE_ROW_RE);
    const tableSeparator = lines[i + 1] && lines[i + 1].trim();
    if (tableHeader && tableSeparator && TABLE_SEPARATOR_RE.test(tableSeparator)) {
      flushParagraph();
      const header = splitTableRow(tableHeader[1]);
      i += 2;
      const rows = [];
      while (i < lines.length) {
        const m = lines[i].trim().match(TABLE_ROW_RE);
        if (!m) break;
        rows.push(splitTableRow(m[1]));
        i++;
      }
      html.push(renderTable(header, rows));
      continue;
    }

    const ordered = trimmed.match(/^\d+\.\s+(.*)$/);
    if (ordered) {
      flushParagraph();
      const items = [];
      while (i < lines.length) {
        const m = lines[i].trim().match(/^\d+\.\s+(.*)$/);
        if (!m) break;
        items.push(`<li>${inlineFormat(m[1])}</li>`);
        i++;
      }
      html.push(`<ol start="${nextOrderedNumber}">${items.join("")}</ol>`);
      nextOrderedNumber += items.length;
      continue;
    }

    const bulleted = trimmed.match(/^[*-]\s+(.*)$/);
    if (bulleted) {
      flushParagraph();
      const items = [];
      while (i < lines.length) {
        const m = lines[i].trim().match(/^[*-]\s+(.*)$/);
        if (!m) break;
        items.push(`<li>${inlineFormat(m[1])}</li>`);
        i++;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    paragraph.push(inlineFormat(trimmed));
    i++;
  }
  flushParagraph();
  return html.join("");
}
