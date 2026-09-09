// tools/html_assets/nav.js
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".sidebar-toggle");
  const sidebar = document.querySelector(".sidebar");
  if (!toggle || !sidebar) return;
  toggle.addEventListener("click", () => {
    const opening = !sidebar.classList.contains("open");
    sidebar.classList.toggle("open", opening);
    if (opening) {
      const current = sidebar.querySelector(".current");
      if (current) current.scrollIntoView({ block: "center" });
    }
  });
});
