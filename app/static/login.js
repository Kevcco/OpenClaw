(() => {
  const root = document.documentElement;
  const themeButton = document.querySelector("[data-theme-toggle]");
  const savedTheme = localStorage.getItem("campusclaw-theme");
  if (savedTheme === "dark" || savedTheme === "light") root.dataset.theme = savedTheme;
  themeButton?.addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("campusclaw-theme", root.dataset.theme);
  });
})();
