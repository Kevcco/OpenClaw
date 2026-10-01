(() => {
  const root = document.documentElement;
  const themeButton = document.querySelector("[data-theme-toggle]");
  const savedTheme = localStorage.getItem("campusclaw-theme");
  const tokenStorageKey = "campusclaw-access-token";
  const form = document.querySelector("[data-login-form]");
  const message = document.querySelector("[data-login-message]");
  const submit = form?.querySelector("button[type=submit]");

  if (savedTheme === "dark" || savedTheme === "light") root.dataset.theme = savedTheme;
  themeButton?.addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("campusclaw-theme", root.dataset.theme);
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = form.elements.username.value.trim();
    const password = form.elements.password.value;
    message.textContent = "正在登录…";
    message.hidden = false;
    message.classList.remove("error");
    submit.disabled = true;
    sessionStorage.removeItem(tokenStorageKey);
    try {
      const response = await fetch(form.action, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "omit",
        body: JSON.stringify({ username, password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.access_token || payload.token_type !== "Bearer") {
        throw new Error(payload.error || "登录失败，请检查账号和密码。");
      }
      sessionStorage.setItem(tokenStorageKey, payload.access_token);
      window.location.assign("/materials");
    } catch (error) {
      message.textContent = error.message || "登录失败，请稍后重试。";
      message.classList.add("error");
    } finally {
      submit.disabled = false;
    }
  });
})();
