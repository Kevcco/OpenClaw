(() => {
  const host = document.querySelector("#api-operations");
  const tokenInput = document.querySelector("#bearer-token");

  const field = (labelText, value, inputType = "text") => {
    const wrapper = document.createElement("div");
    wrapper.className = "field";
    const label = document.createElement("label");
    label.textContent = labelText;
    const input = document.createElement("input");
    input.type = inputType;
    input.value = value || "";
    wrapper.append(label, input);
    return { wrapper, input };
  };

  const showResult = (pre, text) => { pre.textContent = text; };

  const runOperation = async ({ operation, method, path, inputs, body, button, output }) => {
    button.disabled = true;
    showResult(output, "Requesting…");
    try {
      let requestPath = path;
      const query = new URLSearchParams();
      for (const item of inputs) {
        const value = item.input.value.trim();
        if (item.parameter.in === "path") requestPath = requestPath.replace(`{${item.parameter.name}}`, encodeURIComponent(value));
        if (item.parameter.in === "query" && value) query.set(item.parameter.name, value);
      }
      const url = new URL(requestPath, window.location.origin);
      url.search = query.toString();
      const headers = new Headers();
      const hasAuth = (operation.security || []).some((entry) => entry.BearerAuth !== undefined);
      const token = tokenInput.value.trim();
      if (hasAuth && token) headers.set("Authorization", `Bearer ${token}`);
      const options = { method, headers, credentials: "omit" };
      if (body) {
        headers.set("Content-Type", "application/json");
        options.body = body.value.trim() || "{}";
      }
      const response = await fetch(url, options);
      const contentType = response.headers.get("Content-Type") || "";
      if (contentType.includes("text/event-stream")) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let streamText = `HTTP ${response.status}\n${contentType}\n\n`;
        showResult(output, streamText);
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          streamText += decoder.decode(value, { stream: true });
          showResult(output, streamText);
        }
        streamText += decoder.decode();
        showResult(output, streamText);
      } else {
        const raw = await response.text();
        let rendered = raw;
        try {
          const parsed = JSON.parse(raw);
          rendered = JSON.stringify(parsed, null, 2);
          if (parsed.access_token) tokenInput.value = parsed.access_token;
        } catch (_error) {}
        showResult(output, `HTTP ${response.status}\n${contentType}\n\n${rendered}`);
      }
    } catch (error) {
      showResult(output, `Request error: ${error.message}`);
    } finally {
      button.disabled = false;
    }
  };

  const render = (documentData) => {
    host.replaceChildren();
    const paths = documentData.paths || {};
    const tags = new Map();
    for (const [path, pathItem] of Object.entries(paths)) {
      for (const [method, operation] of Object.entries(pathItem)) {
        if (!["get", "post", "put", "patch", "delete"].includes(method)) continue;
        const tag = operation.tags?.[0] || "Other";
        if (!tags.has(tag)) {
          const section = document.createElement("section");
          section.className = "group";
          const heading = document.createElement("h2");
          heading.textContent = tag;
          section.append(heading);
          tags.set(tag, section);
          host.append(section);
        }

        const details = document.createElement("details");
        details.className = "op";
        const summary = document.createElement("summary");
        const badge = document.createElement("span");
        badge.className = `method ${method.toUpperCase()}`;
        badge.textContent = method.toUpperCase();
        const route = document.createElement("span");
        route.className = "path";
        route.textContent = path;
        const label = document.createElement("span");
        label.className = "summary";
        label.textContent = operation.summary || "";
        summary.append(badge, route, label);
        details.append(summary);

        const panel = document.createElement("div");
        panel.className = "detail";
        if (operation.description) {
          const description = document.createElement("p");
          description.className = "description";
          description.textContent = operation.description;
          panel.append(description);
        }
        const inputs = [];
        const parameters = [...(pathItem.parameters || []), ...(operation.parameters || [])];
        for (const parameter of parameters) {
          const control = field(`${parameter.name} · ${parameter.in}${parameter.required ? " · required" : ""}`, parameter.schema?.default ?? "");
          control.parameter = parameter;
          inputs.push(control);
          panel.append(control.wrapper);
        }
        let bodyControl = null;
        const bodyExample = operation.requestBody?.content?.["application/json"]?.example;
        if (bodyExample !== undefined) {
          const wrapper = document.createElement("div");
          wrapper.className = "field";
          const bodyLabel = document.createElement("label");
          bodyLabel.textContent = "application/json body";
          const textarea = document.createElement("textarea");
          textarea.value = JSON.stringify(bodyExample, null, 2);
          wrapper.append(bodyLabel, textarea);
          panel.append(wrapper);
          bodyControl = textarea;
        }
        const button = document.createElement("button");
        button.type = "button";
        button.className = "try";
        button.textContent = "Try it out";
        const output = document.createElement("pre");
        output.className = "result";
        output.hidden = true;
        button.addEventListener("click", () => {
          output.hidden = false;
          runOperation({ operation, method: method.toUpperCase(), path, inputs, body: bodyControl, button, output });
        });
        panel.append(button, output);
        details.append(panel);
        tags.get(tag).append(details);
      }
    }
  };

  fetch("/openapi.json", { credentials: "omit" })
    .then((response) => {
      if (!response.ok) throw new Error(`OpenAPI request failed (${response.status})`);
      return response.json();
    })
    .then(render)
    .catch((error) => { host.textContent = `无法加载 OpenAPI 文档：${error.message}`; });
})();
