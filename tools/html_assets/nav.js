// tools/html_assets/nav.js
document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.querySelector(".sidebar");
  if (!sidebar) return;
  // scroll the current song into view on load — works on desktop (sidebar
  // always visible) and on mobile (still laid out, just translated
  // off-screen until opened, so the scroll position is already correct
  // by the time the panel slides in)
  const current = sidebar.querySelector(".current");
  if (current) current.scrollIntoView({ block: "center" });

  const toggle = document.querySelector(".sidebar-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });
  }

  initSidebarFilter(sidebar);
});

function normalizeFilterText(s) {
  // same idea as generate_html.py's search_key: strip diacritics via NFD
  // decomposition + drop the combining marks, then lowercase
  return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function initSidebarFilter(sidebar) {
  const input = sidebar.querySelector(".sidebar-filter");
  if (!input) return;
  const links = Array.from(sidebar.querySelectorAll(".song-link"));
  const headers = Array.from(sidebar.querySelectorAll("h3"));

  const apply = () => {
    const q = normalizeFilterText(input.value.trim());
    for (const a of links) {
      a.classList.toggle("filtered-out", !(!q || a.dataset.search.includes(q)));
    }
    for (const h of headers) {
      let el = h.nextElementSibling;
      let anyVisible = false;
      while (el && el.tagName !== "H3") {
        if (el.classList.contains("song-link") && !el.classList.contains("filtered-out")) {
          anyVisible = true;
          break;
        }
        el = el.nextElementSibling;
      }
      h.classList.toggle("filtered-out", !anyVisible);
    }
  };

  input.addEventListener("input", apply);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      input.value = "";
      apply();
    }
  });
}
