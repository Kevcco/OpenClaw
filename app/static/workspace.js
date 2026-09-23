(() => {
  const root = document.documentElement;
  const $ = (selector) => document.querySelector(selector);
  const list = $(`[data-material-list]`);
  const notice = $(`[data-notice]`);
  const empty = $(`[data-empty-state]`);
  const resultCount = $(`[data-result-count]`);
  const searchForm = $(`[data-search-form]`);
  const searchInput = searchForm.elements.q;
  const uploadPanel = $(`[data-upload-panel]`);
  const uploadDialogButton = $(`[data-open-upload]`);
  const commandDialog = $(`[data-command-dialog]`);
  const commandInput = $(`[data-command-input]`);
  const previewDialog = $(`[data-preview-dialog]`);
  let user = null;
  let activeIndex = 0;

  const setNotice = (message, error = false) => {
    notice.textContent = message;
    notice.classList.toggle("error", error);
    notice.hidden = !message;
  };

  const fetchJson = async (url, options = {}) => {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    if (response.status === 401) {
      window.location.assign("/login");
      throw new Error("登录已失效");
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `请求失败 (${response.status})`);
    return payload;
  };

  const loadIdentity = async () => {
    user = await fetchJson("/api/me");
    const identity = $(`[data-identity]`);
    identity.querySelector(".avatar").textContent = user.username.slice(0, 1).toUpperCase();
    identity.querySelector("span:last-child").innerHTML = "";
    const label = document.createElement("span");
    label.textContent = user.username;
    const role = document.createElement("small");
    role.textContent = user.role === "teacher" ? "教师 · 可管理材料" : "学生 · 只读访问";
    label.append(role);
    identity.append(label);
    $(`[data-class-name]`).textContent = `班级 ${user.class_id === 1 ? "A" : user.class_id === 2 ? "B" : user.class_id}`;
    $(`[data-role-label]`).textContent = user.role === "teacher" ? "教师工作区" : "学生只读";
    if (user.role === "teacher") {
      uploadDialogButton.hidden = false;
      $(`[data-teacher-command]`).hidden = false;
    }
  };

  const makeMaterialRow = (material) => {
    const row = document.createElement("article");
    row.className = "material-row";
    const icon = document.createElement("span");
    icon.className = "file-icon";
    icon.textContent = "▤";
    const main = document.createElement("div");
    main.className = "material-main";
    const title = document.createElement("button");
    title.className = "material-title";
    title.type = "button";
    title.textContent = material.title;
    title.addEventListener("click", () => openPreview(material.id));
    const meta = document.createElement("div");
    meta.className = "material-meta";
    const date = document.createElement("span");
    date.textContent = material.created_at || "教学资料";
    const tag = document.createElement("span");
    tag.className = "file-tag";
    tag.textContent = "MATERIAL";
    meta.append(date, tag);
    main.append(title, meta);
    const actions = document.createElement("div");
    actions.className = "row-actions";
    const preview = document.createElement("button");
    preview.type = "button";
    preview.textContent = "预览";
    preview.addEventListener("click", () => openPreview(material.id));
    const download = document.createElement("a");
    download.href = `/api/materials/${material.id}/download`;
    download.textContent = "下载";
    actions.append(preview, download);
    row.append(icon, main, actions);
    return row;
  };

  const loadMaterials = async (query = searchInput.value.trim()) => {
    resultCount.textContent = "正在加载…";
    list.replaceChildren();
    empty.hidden = true;
    setNotice("");
    try {
      const url = new URL("/api/materials", window.location.origin);
      if (query) url.searchParams.set("q", query);
      const payload = await fetchJson(url);
      for (const material of payload.materials) list.append(makeMaterialRow(material));
      resultCount.textContent = `共 ${payload.materials.length} 项`;
      empty.hidden = payload.materials.length > 0;
      const current = new URL(window.location.href);
      if (query) current.searchParams.set("q", query);
      else current.searchParams.delete("q");
      window.history.replaceState({}, "", current);
    } catch (error) {
      if (error.message !== "登录已失效") setNotice(error.message, true);
      resultCount.textContent = "加载失败";
    }
  };

  const openPreview = async (materialId) => {
    try {
      const material = await fetchJson(`/api/materials/${materialId}`);
      $(`[data-preview-title]`)?.remove();
      $("#preview-title").textContent = material.title;
      $(`[data-preview-body]`).textContent = material.body_text;
      $(`[data-download-link]`).href = `/api/materials/${materialId}/download`;
      previewDialog.showModal();
    } catch (error) {
      setNotice(error.message, true);
    }
  };

  document.querySelectorAll("[data-preview-id]").forEach((button) => {
    button.addEventListener("click", () => openPreview(button.dataset.previewId));
  });

  const closeCommand = () => commandDialog.close();
  const actions = {
    search: () => { searchInput.focus(); searchInput.select(); },
    refresh: () => loadMaterials(),
    theme: () => $(`[data-theme-toggle]`).click(),
    upload: () => { if (user?.role === "teacher") { uploadPanel.hidden = false; uploadPanel.scrollIntoView({ behavior: "smooth", block: "start" }); } },
  };

  const runCommand = (name) => { closeCommand(); actions[name]?.(); };
  const commands = [...commandDialog.querySelectorAll("[data-command]")];
  const selectCommand = (index) => {
    activeIndex = (index + commands.length) % commands.length;
    commands.forEach((item, i) => item.classList.toggle("selected", i === activeIndex));
  };

  const themeToggle = $(`[data-theme-toggle]`);
  const savedTheme = localStorage.getItem("campusclaw-theme");
  if (savedTheme === "dark" || savedTheme === "light") root.dataset.theme = savedTheme;
  themeToggle.addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("campusclaw-theme", root.dataset.theme);
  });
  searchForm.addEventListener("submit", (event) => { event.preventDefault(); loadMaterials(); });
  $(`[data-refresh]`).addEventListener("click", () => loadMaterials());
  uploadDialogButton.addEventListener("click", () => { uploadPanel.hidden = false; uploadPanel.scrollIntoView({ behavior: "smooth", block: "start" }); });
  $(`[data-close-upload]`).addEventListener("click", () => { uploadPanel.hidden = true; });
  $(`[data-file-name]`).closest("label").querySelector("input[type=file]").addEventListener("change", (event) => {
    $(`[data-file-name]`).textContent = event.target.files[0]?.name || "选择 .md 或 .txt 文件";
  });
  $(`[data-upload-form]`).addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $(`[data-submit-upload]`);
    const message = $(`[data-upload-message]`);
    button.disabled = true;
    message.textContent = "正在上传并解析…";
    message.classList.remove("error");
    try {
      await fetchJson("/api/materials/upload", { method: "POST", body: new FormData(form) });
      form.reset();
      $(`[data-file-name]`).textContent = "选择 .md 或 .txt 文件";
      message.textContent = "上传成功，材料已加入本班知识库。";
      await loadMaterials();
    } catch (error) {
      message.textContent = error.message;
      message.classList.add("error");
    } finally {
      button.disabled = false;
    }
  });
  $(`[data-command="search"]`).addEventListener("click", () => runCommand("search"));
  $(`[data-command="refresh"]`).addEventListener("click", () => runCommand("refresh"));
  $(`[data-command="theme"]`).addEventListener("click", () => runCommand("theme"));
  $(`[data-command="upload"]`).addEventListener("click", () => runCommand("upload"));
  $(`[data-close-preview]`).addEventListener("click", () => previewDialog.close());
  commandInput.addEventListener("input", () => {
    const query = commandInput.value.trim().toLowerCase();
    commands.forEach((item) => { item.hidden = !item.textContent.toLowerCase().includes(query); });
    activeIndex = 0;
    selectCommand(activeIndex);
  });
  commandDialog.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") { event.preventDefault(); selectCommand(activeIndex + 1); }
    if (event.key === "ArrowUp") { event.preventDefault(); selectCommand(activeIndex - 1); }
    if (event.key === "Enter" && commands[activeIndex] && !commands[activeIndex].hidden) { event.preventDefault(); commands[activeIndex].click(); }
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault(); commandDialog.showModal(); commandInput.value = ""; commands.forEach((item) => { item.hidden = false; }); selectCommand(0); commandInput.focus();
    }
    if (event.key === "Escape" && previewDialog.open) previewDialog.close();
  });

  loadIdentity().then(() => loadMaterials(document.body.dataset.initialQuery || "")).catch((error) => {
    if (error.message !== "登录已失效") setNotice("无法确认当前身份，请重新登录。", true);
  });
})();
