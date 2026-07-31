const form = document.getElementById("search-form");
const resultsEl = document.getElementById("results");
const answerEl = document.getElementById("answer");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = document.getElementById("query").value.trim();
  if (!query) return;

  const mode = form.elements["mode"].value;
  resultsEl.innerHTML = "";
  answerEl.hidden = true;
  answerEl.innerHTML = "";

  try {
    if (mode === "ask") {
      const data = await fetchJSON(`/api/ask?q=${encodeURIComponent(query)}`);
      renderAnswer(data);
    } else {
      const data = await fetchJSON(`/api/search?q=${encodeURIComponent(query)}`);
      renderResults(data.results);
    }
  } catch (err) {
    resultsEl.innerHTML = `<li class="error">Erreur : ${err.message}</li>`;
  }
});

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function renderAnswer(data) {
  answerEl.hidden = false;
  const sources = data.sources.map((p) => `page ${p}`).join(", ");
  answerEl.innerHTML = `
    <p>${escapeHtml(data.answer).replace(/\n/g, "<br>")}</p>
    <p class="sources">Sources : ${sources || "aucune"}</p>
  `;
}

function renderResults(results) {
  if (results.length === 0) {
    resultsEl.innerHTML = `<li class="empty">Aucun résultat.</li>`;
    return;
  }
  resultsEl.innerHTML = results
    .map(
      (r) => `
    <li class="result">
      <span class="page-badge">page ${r.page_num}</span>
      <p class="excerpt">${escapeHtml(r.excerpt)}</p>
      <img class="thumbnail" src="${r.image_url}" alt="Page ${r.page_num}" loading="lazy" />
    </li>
  `
    )
    .join("");

  resultsEl.querySelectorAll(".thumbnail").forEach((img) => {
    img.addEventListener("click", () => openLightbox(img.src));
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
