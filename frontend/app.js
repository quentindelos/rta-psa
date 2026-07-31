const form = document.getElementById("ask-form");
const queryInput = document.getElementById("query");
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
const historyClearBtn = document.getElementById("history-clear");

const THEME_KEY = "rta-psa-theme";
const HISTORY_KEY = "rta-psa-history";
const HISTORY_MAX = 12;

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
  } catch {
    return [];
  }
}

function saveQueryToHistory(query) {
  const history = loadHistory().filter((q) => q !== query);
  history.unshift(query);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, HISTORY_MAX)));
  renderHistory();
}

function renderHistory() {
  const history = loadHistory();
  historyEl.hidden = history.length === 0;
  if (history.length === 0) return;

  historyListEl.innerHTML = history
    .map((q) => `<button type="button" class="history-item">${escapeHtml(q)}</button>`)
    .join("");

  historyListEl.querySelectorAll(".history-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      queryInput.value = btn.textContent;
      form.requestSubmit();
    });
  });
}

historyClearBtn.addEventListener("click", () => {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
});

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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  setLoading(true);
  answerCard.hidden = true;
  statusEl.hidden = true;

  try {
    const vehicle = vehicleSelect.value;
    const params = new URLSearchParams({ q: query });
    if (vehicle) params.set("vehicle", vehicle);
    const data = await fetchJSON(`/api/ask?${params.toString()}`);
    renderAnswer(data);
    saveQueryToHistory(query);
  } catch (err) {
    showStatus(`Erreur : ${err.message}`, true);
  } finally {
    setLoading(false);
  }
});

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  submitBtn.textContent = isLoading ? "Recherche…" : "Chercher";
  if (isLoading) {
    showStatus("Recherche en cours…", false);
  }
}

function showStatus(message, isError) {
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.classList.toggle("status-error", isError);
}

function renderAnswer(data) {
  statusEl.hidden = true;
  answerCard.hidden = false;
  answerText.innerHTML = renderMarkdown(data.answer);

  if (data.answer_origin === "web") {
    originBadge.className = "origin-badge origin-badge--web";
    originBadge.textContent = "⚠ Non trouvé dans la RTA — réponse IA basée sur une recherche web";
    sourcesEl.innerHTML = "";
    renderWebSources(data.web_sources);
  } else {
    originBadge.className = "origin-badge origin-badge--rta";
    originBadge.textContent = "✓ Réponse basée sur la revue technique";
    webSourcesEl.innerHTML = "";
    renderSources(data.sources);
  }
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
