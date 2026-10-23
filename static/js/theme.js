const themeToggle = document.querySelector("#theme-toggle");
const themePreferenceKey = "test-workspace-theme";
const operatingSystemTheme = window.matchMedia("(prefers-color-scheme: dark)");

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const darkMode = theme === "dark";
  themeToggle.setAttribute("aria-label", `Switch to ${darkMode ? "light" : "dark"} theme`);
  themeToggle.title = `Switch to ${darkMode ? "light" : "dark"} theme`;
}

function getSessionTheme() {
  try {
    const theme = window.sessionStorage.getItem(themePreferenceKey);
    return theme === "dark" || theme === "light" ? theme : null;
  } catch (error) {
    console.warn("Could not read the session theme preference.", error);
    return null;
  }
}

function saveSessionTheme(theme) {
  try {
    window.sessionStorage.setItem(themePreferenceKey, theme);
  } catch (error) {
    console.warn("Could not save the session theme preference.", error);
  }
}

applyTheme(getSessionTheme() || (operatingSystemTheme.matches ? "dark" : "light"));

themeToggle.addEventListener("click", () => {
  const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(nextTheme);
  saveSessionTheme(nextTheme);
});

operatingSystemTheme.addEventListener("change", (event) => {
  if (!getSessionTheme()) {
    applyTheme(event.matches ? "dark" : "light");
  }
});
