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
  const knowledgeForm = $(`[data-knowledge-search]`);
  const knowledgeQuery = knowledgeForm?.elements.query;
  const knowledgeMode = knowledgeForm?.elements.mode;
  const knowledgeSubmit = $(`[data-knowledge-submit]`);
  const knowledgeStatus = $(`[data-knowledge-status]`);
  const knowledgeResults = $(`[data-knowledge-results]`);
  const answerForm = $(`[data-knowledge-ask]`);
  const answerQuestion = answerForm?.elements.question;
  const answerSubmit = $(`[data-knowledge-ask-submit]`);
  const answerStatus = $(`[data-answer-status]`);
  const answerPanel = $(`[data-answer-panel]`);
  const answerText = $(`[data-answer-text]`);
  const tokenStorageKey = "campusclaw-access-token";
  let user = null;
  let activeIndex = 0;

  const setNotice = (message, error = false) => {
    notice.textContent = message;
    notice.classList.toggle("error", error);
    notice.hidden = !message;
  };

  const getToken = () => sessionStorage.getItem(tokenStorageKey);

  const redirectToLogin = () => {
    sessionStorage.removeItem(tokenStorageKey);
    window.location.assign("/login");
  };

  const fetchJson = async (url, options = {}) => {
    const headers = new Headers(options.headers || {});
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(url, { ...options, headers, credentials: "omit" });
    if (response.status === 401) {
      redirectToLogin();
      throw new Error("登录已失效");
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.error || `请求失败 (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return payload;
  };

  const downloadMaterial = async (url) => {
    const token = getToken();
    const headers = new Headers();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(url, { headers, credentials: "omit" });
    if (response.status === 401) {
      redirectToLogin();
      throw new Error("登录已失效");
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `下载失败 (${response.status})`);
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    const disposition = response.headers.get("Content-Disposition") || "";
    const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
    const plainName = disposition.match(/filename="?([^";]+)"?/i)?.[1];
    link.download = encodedName ? decodeURIComponent(encodedName) : (plainName || "material");
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
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
    download.addEventListener("click", (event) => {
      event.preventDefault();
      downloadMaterial(download.href).catch((error) => setNotice(error.message, true));
    });
    actions.append(preview, download);
    row.append(icon, main, actions);
    return row;
  };

  const setKnowledgeStatus = (message, state = "") => {
    knowledgeStatus.textContent = message;
    knowledgeStatus.className = "retrieval-status";
    if (state) knowledgeStatus.classList.add(state);
    knowledgeStatus.hidden = !message;
  };

  const setAnswerStatus = (message, state = "") => {
    answerStatus.textContent = message;
    answerStatus.className = "retrieval-status";
    if (state) answerStatus.classList.add(state);
    answerStatus.hidden = !message;
  };

  const clearAnswer = () => {
    answerText.textContent = "";
    answerPanel.replaceChildren(answerPanel.querySelector(".eyebrow"), answerText);
    answerPanel.hidden = true;
  };

  const makeKnowledgeHit = (hit, index) => {
    const source = hit.source || {};
    const card = document.createElement("article");
    card.className = "retrieval-hit";

    const head = document.createElement("div");
    head.className = "retrieval-hit-head";
    const title = document.createElement("div");
    title.className = "retrieval-hit-title";
    title.textContent = `[${index}] ${source.title || "未命名材料"}`;
    const score = document.createElement("span");
    score.className = "retrieval-hit-score";
    if (typeof hit.score === "number") score.textContent = `相关度 ${hit.score.toFixed(4)}`;
    head.append(title, score);

    const meta = document.createElement("div");
    meta.className = "retrieval-hit-meta";
    const chunk = document.createElement("span");
    chunk.textContent = `切片 ${source.chunk_index ?? "-"}`;
    const range = document.createElement("span");
    range.textContent = `字符 ${source.start_offset ?? "-"}-${source.end_offset ?? "-"}`;
    const strategy = document.createElement("span");
    strategy.textContent = source.strategy ? `策略 ${source.strategy}` : "";
    meta.append(chunk, range);
    if (strategy.textContent) meta.append(strategy);

    const snippet = document.createElement("p");
    snippet.className = "retrieval-hit-snippet";
    snippet.textContent = hit.snippet || "";

    const links = document.createElement("div");
    links.className = "retrieval-hit-links";
    if (source.preview_url && source.material_id != null) {
      const preview = document.createElement("button");
      preview.type = "button";
      preview.addEventListener("click", () => openPreview(source.material_id));
      preview.textContent = "打开材料";
      links.append(preview);
    }
    if (source.download_url) {
      const download = document.createElement("a");
      download.href = source.download_url;
      download.textContent = "下载原文件";
      download.addEventListener("click", (event) => {
        event.preventDefault();
        downloadMaterial(download.href).catch((error) => setKnowledgeStatus(error.message, "error"));
      });
      links.append(download);
    }
    card.append(head, meta, snippet, links);
    return card;
  };

  const renderKnowledgeHits = (hits) => {
    knowledgeResults.replaceChildren();
    hits.forEach((hit, index) => knowledgeResults.append(makeKnowledgeHit(hit, index + 1)));
  };

  const renderAnswer = (payload) => {
    answerText.textContent = payload.answer || "";
    const eyebrow = answerPanel.querySelector(".eyebrow") || document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "ANSWER";
    const nodes = [eyebrow, answerText];
    if (Array.isArray(payload.citations) && payload.citations.length) {
      const list = document.createElement("ol");
      list.className = "answer-citations";
      payload.citations.forEach((citation) => {
        const item = document.createElement("li");
        const source = citation.source || {};
        item.textContent = `[${citation.index ?? "?"}] ${source.title || "未命名材料"} · 切片 ${source.chunk_index ?? "-"}`;
        list.append(item);
      });
      nodes.push(list);
    }
    answerPanel.replaceChildren(...nodes);
    answerPanel.hidden = false;
  };

  const searchKnowledge = async (event) => {
    event.preventDefault();
    const query = knowledgeQuery.value.trim();
    const mode = knowledgeMode.value;
    if (!query) {
      renderKnowledgeHits([]);
      setKnowledgeStatus("请输入问题或知识点。", "error");
      knowledgeQuery.focus();
      return;
    }
    knowledgeSubmit.disabled = true;
    renderKnowledgeHits([]);
    setKnowledgeStatus("正在检索本班知识库…", "loading");
    try {
      const url = new URL("/api/knowledge/search", window.location.origin);
      url.searchParams.set("q", query);
      url.searchParams.set("mode", mode);
      url.searchParams.set("limit", "10");
      const payload = await fetchJson(url);
      renderKnowledgeHits(payload.hits || []);
      if (!payload.hits?.length) {
        setKnowledgeStatus(payload.message || "资料中未找到相关内容", "");
        return;
      }
      setKnowledgeStatus(`找到 ${payload.hits.length} 条本班依据。`, "");
    } catch (error) {
      if (error.message === "登录已失效") return;
      renderKnowledgeHits([]);
      const message = error.status === 503
        ? "向量服务暂不可用，请稍后重试；关键词模式仍可使用。"
        : error.message;
      setKnowledgeStatus(message, "error");
    } finally {
      knowledgeSubmit.disabled = false;
    }
  };

  const askKnowledge = async (event) => {
    event.preventDefault();
    const question = answerQuestion.value.trim();
    if (!question) {
      clearAnswer();
      setAnswerStatus("请输入要询问的问题。", "error");
      answerQuestion.focus();
      return;
    }
    answerSubmit.disabled = true;
    clearAnswer();
    setAnswerStatus("正在根据本班材料生成回答…", "loading");
    try {
      const payload = await fetchJson("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      renderAnswer(payload);
      setAnswerStatus(
        payload.citations?.length ? "回答已生成，出处见下方。" : "资料中未找到相关依据。",
        "",
      );
    } catch (error) {
      if (error.message === "登录已失效") return;
      clearAnswer();
      setAnswerStatus(`问答失败：${error.message}`, "error");
    } finally {
      answerSubmit.disabled = false;
    }
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

  const logout = async () => {
    try {
      if (getToken()) await fetchJson("/logout", { method: "POST" });
    } catch (error) {
      if (error.message !== "登录已失效") setNotice(error.message, true);
    } finally {
      sessionStorage.removeItem(tokenStorageKey);
      window.location.assign("/login");
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
  knowledgeForm?.addEventListener("submit", searchKnowledge);
  answerForm?.addEventListener("submit", askKnowledge);
  $(`[data-refresh]`).addEventListener("click", () => loadMaterials());
  $(`[data-logout]`).addEventListener("click", logout);
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
  $(`[data-download-link]`).addEventListener("click", (event) => {
    event.preventDefault();
    downloadMaterial(event.currentTarget.href).catch((error) => setNotice(error.message, true));
  });
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

  if (document.body.dataset.initialQuery) searchInput.value = document.body.dataset.initialQuery;
  loadIdentity().then(() => loadMaterials(document.body.dataset.initialQuery || "")).catch((error) => {
    if (error.message !== "登录已失效") setNotice("无法确认当前身份，请重新登录。", true);
  });
})();
