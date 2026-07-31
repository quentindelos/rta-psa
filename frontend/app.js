const form = document.getElementById("ask-form");
const queryInput = document.getElementById("query");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const answerCard = document.getElementById("answer-card");
const answerText = document.getElementById("answer-text");
const sourcesEl = document.getElementById("sources");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  setLoading(true);
  answerCard.hidden = true;
  statusEl.hidden = true;

  try {
    const data = await fetchJSON(`/api/ask?q=${encodeURIComponent(query)}`);
    renderAnswer(data);
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
    showStatus("Recherche dans la revue technique…", false);
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
  answerText.innerHTML = escapeHtml(data.answer).replace(/\n/g, "<br>");

  if (data.sources.length === 0) {
    sourcesEl.innerHTML = "";
    return;
  }

  sourcesEl.innerHTML = data.sources
    .map((source) => {
      if (source.schematic_image_url) {
        return `
          <figure class="source-card source-card--schematic">
            <img
              class="source-image"
              src="${source.schematic_image_url}"
              alt="Schéma, page ${source.page_num}"
              loading="lazy"
              data-full="${source.schematic_image_url}"
            />
            <figcaption>
              Schéma — page ${source.page_num}
              <a class="full-page-link" data-full="${source.page_image_url}" href="#">voir la page complète</a>
            </figcaption>
          </figure>
        `;
      }
      return `
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
      `;
    })
    .join("");

  sourcesEl.querySelectorAll("[data-full]").forEach((el) => {
    el.addEventListener("click", (event) => {
      event.preventDefault();
      openLightbox(el.dataset.full);
    });
  });
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
