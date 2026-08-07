const form = document.getElementById("ask-form");
const queryInput = document.getElementById("query");
const fuelSelect = document.getElementById("fuel");
const vehicleSelect = document.getElementById("vehicle");
const composerOptions = document.getElementById("composer-options");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const threadEl = document.getElementById("thread");
const newConversationBtn = document.getElementById("new-conversation-btn");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const themeToggle = document.getElementById("theme-toggle");
const historyEl = document.getElementById("history");
const historyListEl = document.getElementById("history-list");
const searchStepsEl = document.getElementById("search-steps");
const searchStepsList = document.getElementById("search-steps-list");
const mobileMenuToggle = document.getElementById("mobile-menu-toggle");
const mobileMenu = document.getElementById("mobile-menu");
const mobileMenuBackdrop = document.getElementById("mobile-menu-backdrop");
const mobileMenuClose = document.getElementById("mobile-menu-close");
const discordBanner = document.querySelector(".discord-banner");

const THEME_KEY = "rta-psa-theme";
const HISTORY_KEY = "rta-psa-history";
// Nombre de tours précédents envoyés au serveur pour qu'une question de suivi garde le
// fil (voir aussi _MAX_HISTORY_TURNS côté backend, qui retronque de toute façon).
const HISTORY_TURNS_SENT = 4;

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
  // La RTA Diesel ne couvre qu'un seul moteur : le 1.5D (TUD5, code moteur VJZ, 58 ch) -
  // ni Saxo ni 106 n'ont jamais reçu d'autre motorisation Diesel (pas de turbo, pas de
  // HDi) sur cette génération, donc il n'y a pas d'autre variante moteur à lister ici
  // (contrairement à l'essence, qui a plusieurs cylindrées/motorisations).
  diesel: {
    "Citroën Saxo": [["Citroën Saxo 1.5D", "Saxo 1.5D"]],
    "Peugeot 106": [["Peugeot 106 1.5D", "106 1.5D"]],
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

// Restaure la sélection carburant/véhicule d'une question historique. Le catalogue
// VEHICLE_OPTIONS peut changer entre l'enregistrement d'une question et sa relecture
// (ex : renommage d'un libellé) - dans ce cas l'option d'origine n'existe plus dans la
// liste fraîchement peuplée et une simple affectation de `.value` échouerait
// silencieusement (rien de sélectionné). On réinjecte alors l'option manquante avec le
// libellé mémorisé, pour que la question se rouvre toujours avec le véhicule choisi à
// l'origine plutôt que de retomber sur "toutes les versions".
function restoreFuelAndVehicle(fuel, vehicle, vehicleLabel) {
  fuelSelect.value = fuel || "";
  populateVehicleOptions(fuel);
  if (vehicle && !Array.from(vehicleSelect.options).some((o) => o.value === vehicle)) {
    vehicleSelect.appendChild(new Option(vehicleLabel || vehicle, vehicle));
  }
  vehicleSelect.value = vehicle || "";
}

function inferFuel(vehicle) {
  // Historique enregistré avant l'ajout du sélecteur carburant : on déduit du texte.
  if (!vehicle) return "";
  return /diesel/i.test(vehicle) ? "diesel" : "essence";
}

function newId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// L'historique enregistre des CONVERSATIONS entières (une ou plusieurs questions de
// suite sur le même sujet), pas juste une question isolée - reposer une question
// historique doit rouvrir tout le fil, avec chaque réponse et ses sources telles
// qu'elles étaient. `loadHistory` migre les anciens formats rencontrés au fil du temps :
// - une simple chaîne (tout premier format, avant même le véhicule)
// - un objet à plat {query, vehicle, vehicleLabel, fuel, response} (une question par
//   entrée, avant l'ajout des conversations à plusieurs tours)
function loadHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
    return raw.map((entry, i) => {
      if (typeof entry === "string") {
        return { id: `legacy-${i}`, query: entry, vehicle: "", vehicleLabel: "", fuel: "", turns: [] };
      }
      if (Array.isArray(entry.turns)) {
        return { id: entry.id || `legacy-${i}`, vehicle: "", vehicleLabel: "", fuel: "", ...entry };
      }
      const fuel = entry.fuel || inferFuel(entry.vehicle);
      const turns = entry.response ? [{ query: entry.query, response: entry.response }] : [];
      return {
        id: entry.id || `legacy-${i}`,
        query: entry.query,
        vehicle: entry.vehicle || "",
        vehicleLabel: entry.vehicleLabel || "",
        fuel,
        turns,
      };
    });
  } catch {
    return [];
  }
}

// Pas de limite arbitraire sur le nombre de conversations gardées - on essaie de tout
// garder. localStorage fait généralement 5-10 Mo par site, largement suffisant pour des
// centaines de conversations ; si jamais le quota est dépassé, on supprime les
// conversations les plus anciennes (en fin de liste, la plus récente est toujours en
// tête via unshift) jusqu'à ce que ça rentre, plutôt que de perdre toute la sauvegarde.
function persistHistory(history) {
  while (history.length > 0) {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
      return;
    } catch {
      history.pop();
    }
  }
  localStorage.removeItem(HISTORY_KEY);
}

// On garde la réponse complète avec chaque tour de conversation : reposer une question
// depuis l'historique doit réafficher EXACTEMENT ce qui avait été répondu, pas relancer
// une recherche qui - une fois le cache serveur (TTL 6h) expiré - peut regénérer une
// réponse différente (LLM non déterministe).
function saveConversationToHistory(conversation) {
  const history = loadHistory().filter((entry) => entry.id !== conversation.id);
  history.unshift({ ...conversation });
  persistHistory(history);
  renderHistory();
}

function removeConversationFromHistory(id) {
  const history = loadHistory().filter((entry) => entry.id !== id);
  persistHistory(history);
  renderHistory();
  if (activeConversation && activeConversation.id === id) startNewConversation();
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

    const firstTurn = entry.turns[0];
    const rawQuery = firstTurn ? firstTurn.query : entry.query || "";

    const queryLabel = document.createElement("span");
    queryLabel.className = "history-item-query";
    // Le titre court (reformulé par Gemini) est plus lisible dans la liste que la
    // question brute, parfois longue - la question complète reste dans le tooltip.
    queryLabel.textContent = (firstTurn && firstTurn.response && firstTurn.response.title) || rawQuery;
    queryLabel.title = rawQuery;
    textBtn.appendChild(queryLabel);

    if (entry.vehicleLabel) {
      const vehicleTag = document.createElement("span");
      vehicleTag.className = "history-item-vehicle";
      vehicleTag.textContent = entry.vehicleLabel;
      textBtn.appendChild(vehicleTag);
    }

    if (entry.turns.length > 1) {
      const countTag = document.createElement("span");
      countTag.className = "history-item-count";
      countTag.textContent = `${entry.turns.length} questions`;
      textBtn.appendChild(countTag);
    }

    textBtn.addEventListener("click", () => {
      closeMobileMenu();
      if (entry.turns.length === 0) {
        // Entrée d'historique enregistrée avant l'ajout du cache local (ou conversation
        // jamais aboutie) : on n'a que la question, on la repropose sans relancer de
        // recherche automatiquement.
        showInitialForm();
        restoreFuelAndVehicle(entry.fuel, entry.vehicle, entry.vehicleLabel);
        queryInput.value = rawQuery;
        return;
      }
      openConversation(entry);
    });

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "history-item-remove";
    removeBtn.setAttribute("aria-label", "Supprimer cette conversation");
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", () => {
      removeConversationFromHistory(entry.id);
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

// Sur mobile, le bouton thème/le bandeau Discord/l'historique prennent trop de place
// dans le flux : ils passent dans un menu hamburger. On déplace les VRAIS éléments
// (pas des copies, pour ne pas dupliquer l'état) plutôt que de dupliquer le HTML - un
// marqueur à chaque emplacement d'origine permet de les y remettre sur grand écran.
const themeToggleAnchor = document.createComment("theme-toggle-anchor");
const discordBannerAnchor = document.createComment("discord-banner-anchor");
const historyAnchor = document.createComment("history-anchor");
themeToggle.after(themeToggleAnchor);
discordBanner.after(discordBannerAnchor);
historyEl.after(historyAnchor);

function openMobileMenu() {
  mobileMenu.classList.add("open");
  mobileMenuBackdrop.hidden = false;
  mobileMenuToggle.setAttribute("aria-expanded", "true");
}

function closeMobileMenu() {
  mobileMenu.classList.remove("open");
  mobileMenuBackdrop.hidden = true;
  mobileMenuToggle.setAttribute("aria-expanded", "false");
}

function layoutForMobileMenu(isMobile) {
  if (isMobile) {
    mobileMenu.append(themeToggle, discordBanner, historyEl);
  } else {
    closeMobileMenu();
    themeToggleAnchor.after(themeToggle);
    discordBannerAnchor.after(discordBanner);
    historyAnchor.after(historyEl);
  }
}

mobileMenuToggle.addEventListener("click", () => {
  if (mobileMenu.classList.contains("open")) closeMobileMenu();
  else openMobileMenu();
});
mobileMenuClose.addEventListener("click", closeMobileMenu);
mobileMenuBackdrop.addEventListener("click", closeMobileMenu);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeMobileMenu();
});

const mobileMenuQuery = window.matchMedia("(max-width: 700px)");
layoutForMobileMenu(mobileMenuQuery.matches);
mobileMenuQuery.addEventListener("change", (event) => layoutForMobileMenu(event.matches));

// --- Conversation active -----------------------------------------------------------
// Une conversation garde le fil (fuel/vehicle figés au premier tour + historique des
// questions/réponses) pour que les questions de suivi ("et pour le diesel ?") soient
// comprises sans tout reformuler. `activeConversation` est null tant qu'aucune question
// n'a encore reçu de réponse. Une seule barre de saisie (style Claude/ChatGPT, fixée en
// bas de page) sert à la fois pour la toute première question et pour les questions de
// suivi : elle affiche le sélecteur carburant/véhicule uniquement tant qu'aucune
// conversation n'est en cours (ce choix fige le reste du fil).
let activeConversation = null;
let currentEventSource = null;
let idleSubmitLabel = "Chercher";

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  submitBtn.textContent = isLoading ? "Recherche…" : idleSubmitLabel;
}

function showInitialForm() {
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  activeConversation = null;
  threadEl.innerHTML = "";
  threadEl.hidden = true;
  composerOptions.hidden = false;
  newConversationBtn.hidden = true;
  queryInput.placeholder = "ex : de quelle couleur est le fil du démarreur ?";
  idleSubmitLabel = "Chercher";
  setLoading(false);
  statusEl.hidden = true;
  resetSearchSteps();
}

function startNewConversation() {
  showInitialForm();
  queryInput.value = "";
  fuelSelect.value = "";
  populateVehicleOptions("");
  queryInput.focus();
}

function switchToFollowupMode() {
  composerOptions.hidden = true;
  newConversationBtn.hidden = false;
  queryInput.placeholder = "Poser une question de suivi sur le même sujet…";
  idleSubmitLabel = "Envoyer";
  setLoading(false);
}

function openConversation(entry) {
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  activeConversation = {
    id: entry.id,
    vehicle: entry.vehicle,
    vehicleLabel: entry.vehicleLabel,
    fuel: entry.fuel,
    turns: entry.turns,
  };
  restoreFuelAndVehicle(entry.fuel, entry.vehicle, entry.vehicleLabel);
  queryInput.value = "";
  statusEl.hidden = true;
  resetSearchSteps();
  renderThread();
  switchToFollowupMode();
}

newConversationBtn.addEventListener("click", startNewConversation);

// Compacte l'historique envoyé au serveur (paramètre GET - EventSource ne permet pas de
// requête POST, donc pas de corps de requête) : la question et un extrait de la réponse
// suffisent à comprendre une question de suivi, pas besoin du texte complet.
function historyPayload(turns) {
  return JSON.stringify(
    turns.slice(-HISTORY_TURNS_SENT).map((t) => ({ q: t.query, a: (t.response.answer || "").slice(0, 600) }))
  );
}

function runSearch({ query, fuel, vehicle, historyTurns, onStep, onResult, onError }) {
  const params = new URLSearchParams({ q: query });
  if (fuel) params.set("fuel", fuel);
  if (vehicle) params.set("vehicle", vehicle);
  if (historyTurns && historyTurns.length) params.set("history", historyPayload(historyTurns));

  const es = new EventSource(`/api/ask/stream?${params.toString()}`);
  currentEventSource = es;

  es.addEventListener("step", (event) => onStep(JSON.parse(event.data).message));

  es.addEventListener("result", (event) => {
    es.close();
    currentEventSource = null;
    onResult(JSON.parse(event.data));
  });

  es.onerror = () => {
    es.close();
    currentEventSource = null;
    onError();
  };
}

// Une seule soumission gère les deux cas : premier tour d'une conversation (fuel/vehicle
// choisis dans #composer-options, une nouvelle conversation est créée) et question de
// suivi (activeConversation existe déjà, fuel/vehicle/historique repris tels quels).
form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  closeMobileMenu();

  if (!activeConversation) {
    const fuel = fuelSelect.value;
    const vehicle = vehicleSelect.value;
    const vehicleLabel = vehicle ? vehicleSelect.options[vehicleSelect.selectedIndex].text : "";
    activeConversation = { id: newId(), vehicle, vehicleLabel, fuel, turns: [] };
  }
  const conversation = activeConversation;
  const isFirstTurn = conversation.turns.length === 0;

  setLoading(true);
  resetSearchSteps();
  showStatus("Recherche en cours…", false);

  runSearch({
    query,
    fuel: conversation.fuel,
    vehicle: conversation.vehicle,
    historyTurns: conversation.turns,
    onStep: addSearchStep,
    onResult: (data) => {
      conversation.turns.push({ query, response: data });
      queryInput.value = "";
      if (isFirstTurn) switchToFollowupMode();
      setLoading(false);
      statusEl.hidden = true;
      renderThread();
      saveConversationToHistory(conversation);
    },
    onError: () => {
      setLoading(false);
      showStatus("Erreur : la recherche a échoué.", true);
    },
  });
});

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

// --- Rendu du fil de conversation ---------------------------------------------------

function renderThread() {
  threadEl.innerHTML = "";
  threadEl.hidden = activeConversation.turns.length === 0;
  activeConversation.turns.forEach((turn) => {
    threadEl.appendChild(renderTurn(turn));
  });
  const lastTurn = threadEl.lastElementChild;
  if (lastTurn) lastTurn.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderTurn(turn) {
  const data = turn.response;

  const article = document.createElement("article");
  article.className = "turn";

  const questionEl = document.createElement("p");
  questionEl.className = "turn-question";
  questionEl.textContent = turn.query;
  article.appendChild(questionEl);

  const answerWrap = document.createElement("div");
  answerWrap.className = "turn-answer";

  const badge = document.createElement("div");
  if (data.answer_origin === "web_only") {
    badge.className = "origin-badge origin-badge--web";
    badge.textContent = "🌐 Non trouvé dans la RTA - réponse basée sur le web";
  } else {
    badge.className = "origin-badge origin-badge--rta";
    badge.textContent = "📖 RTA + 🌐 Web";
  }
  answerWrap.appendChild(badge);

  const textEl = document.createElement("div");
  textEl.className = "answer-text";
  textEl.innerHTML = renderMarkdown(data.answer);
  answerWrap.appendChild(textEl);

  // Sources RTA (pages/schémas) et sources web toujours affichées en bas de CETTE
  // réponse précise, pas juste à la fin du fil - chaque tour garde ses propres sources.
  const sourcesEl = document.createElement("div");
  sourcesEl.className = "sources";
  if (data.answer_origin !== "web_only") fillSources(sourcesEl, data.sources);
  answerWrap.appendChild(sourcesEl);

  const webSourcesEl = document.createElement("div");
  webSourcesEl.className = "web-sources";
  fillWebSources(webSourcesEl, data.web_sources);
  answerWrap.appendChild(webSourcesEl);

  article.appendChild(answerWrap);
  return article;
}

function fillSources(container, sources) {
  if (!sources || sources.length === 0) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = sources
    .flatMap((source) => {
      if (source.schematic_image_urls && source.schematic_image_urls.length > 0) {
        return source.schematic_image_urls.map((url, i) => {
          const label =
            source.schematic_image_urls.length > 1 ? `Schéma ${i + 1} - page ${source.page_num}` : `Schéma - page ${source.page_num}`;
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

  container.querySelectorAll("[data-full]").forEach((el) => {
    el.addEventListener("click", (event) => {
      event.preventDefault();
      openLightbox(el.dataset.full);
    });
  });
}

function fillWebSources(container, webSources) {
  if (!webSources || webSources.length === 0) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML =
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
  // gras uniquement (**texte**) - c'est le seul style markdown que Gemini utilise ici
  return escapeHtml(line).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

// Volontairement tolérants : Gemini ne termine pas toujours une ligne de tableau par
// "|", et les lignes de séparation ("|---|:---|") peuvent contenir un nombre de tirets
// variable (parfois très long si le modèle "aligne" les colonnes). On ne veut pas
// perdre le tableau - ni afficher des tirets/pipes bruts en repli - pour si peu.
const TABLE_ROW_RE = /^\|(.*)$/;
const TABLE_SEPARATOR_RE = /^\|?[\s|:-]*-{2,}[\s|:-]*$/;

function splitTableRow(row) {
  const trimmed = row.trim();
  const withoutEdgePipes = trimmed.replace(/^\|/, "").replace(/\|$/, "");
  return withoutEdgePipes.split("|").map((cell) => cell.trim());
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
  // entre deux étapes, on referme le <ol> - et un nouveau <ol> recommence à 1
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

    const heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      const level = Math.min(heading[1].length + 2, 6); // ### -> h5, jamais h1/h2 (déjà pris par le titre de page)
      html.push(`<h${level}>${inlineFormat(heading[2])}</h${level}>`);
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
