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
  if (!toggle) return;
  toggle.addEventListener("click", () => {
    sidebar.classList.toggle("open");
  });
});
