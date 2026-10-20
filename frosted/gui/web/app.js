(() => {
  "use strict";

  const TOKEN = document.querySelector('meta[name="frosted-token"]').content;

  // サーバーに繋がらないときでもボタンの文字が消えないようにする
  // 最低限の英語ラベル。bootstrap が成功したら正式な文言で上書きする。
  const FALLBACK_STRINGS = {
    recipe_path: "Recipe",
    open: "Open",
    new: "New",
    save: "Save",
    generate: "Generate config",
    raw: "TOML",
    build: "Build",
    doctor: "Doctor",
    summary: "Summary",
    issues: "Validation",
    close: "Close",
    unsaved: "Unsaved changes",
    raw_help: "Edit advanced settings directly in TOML.",
    form_toml: "Render form as TOML",
    load_into_form: "Load into form",
    save_raw: "Save this TOML",
    build_note: "Copy the command and run it in a terminal.",
    new_title: "New recipe",
    name: "Name",
    preset: "Preset",
    cancel: "Cancel",
    none: "None",
    invalid_path: "Check the path",
    network_error: "Cannot reach the server",
    no_recipe: "No recipe is open",
    loading: "Loading...",
  };

  const state = {
    version: "",
    lang: "ja",
    strings: {},
    sections: [],
    presets: [],
    recipe: {},
    path: "",
    toml: "",
    tomlStale: false,
    rawDirty: false,
    issues: [],
    summary: null,
    active: "iso",
    dirty: false,
    busy: false,
    validateSeq: 0,
    validateTimer: null,
    toastTimer: null,
  };

  const dom = {
    version: document.getElementById("version"),
    path: document.getElementById("recipe-path"),
    pathLabel: document.getElementById("recipe-path-label"),
    openBtn: document.getElementById("open-btn"),
    newBtn: document.getElementById("new-btn"),
    saveBtn: document.getElementById("save-btn"),
    generateBtn: document.getElementById("generate-btn"),
    dirty: document.getElementById("dirty"),
    status: document.getElementById("status"),
    nav: document.getElementById("nav"),
    fatal: document.getElementById("fatal"),
    formPanel: document.getElementById("form-panel"),
    sectionTitle: document.getElementById("section-title"),
    form: document.getElementById("form"),
    rawPanel: document.getElementById("raw-panel"),
    rawTitle: document.getElementById("raw-title"),
    rawHelp: document.getElementById("raw-help"),
    rawStale: document.getElementById("raw-stale"),
    rawText: document.getElementById("raw-text"),
    rawRenderBtn: document.getElementById("raw-render-btn"),
    rawParseBtn: document.getElementById("raw-parse-btn"),
    rawSaveBtn: document.getElementById("raw-save-btn"),
    buildPanel: document.getElementById("build-panel"),
    buildTitle: document.getElementById("build-title"),
    buildNote: document.getElementById("build-note"),
    commands: document.getElementById("commands"),
    summaryTitle: document.getElementById("summary-title"),
    summary: document.getElementById("summary"),
    doctorBtn: document.getElementById("doctor-btn"),
    issuesTitle: document.getElementById("issues-title"),
    issues: document.getElementById("issues"),
    modal: document.getElementById("modal"),
    modalTitle: document.getElementById("modal-title"),
    modalContent: document.getElementById("modal-content"),
    toast: document.getElementById("toast"),
  };

  // ---------------------------------------------------------------- helpers

  function S(key) {
    return state.strings[key] ?? FALLBACK_STRINGS[key] ?? key;
  }

  function fmt(template, vars = {}) {
    return String(template).replace(/\{(\w+)\}/g, (match, key) =>
      vars[key] === undefined ? match : String(vars[key])
    );
  }

  function countLabel(kind, count) {
    if (count === 1) {
      return kind === "errors" ? S("error_one") : S("warning_one");
    }
    return fmt(
      kind === "errors" ? S("errors_count") : S("warnings_count"),
      { count }
    );
  }

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === false || value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (value === true) {
        node.setAttribute(key, "");
      } else {
        node.setAttribute(key, String(value));
      }
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function getPath(object, path) {
    return path.split(".").reduce((value, key) => {
      if (value && typeof value === "object" && key in value) return value[key];
      return undefined;
    }, object);
  }

  function setPath(object, path, value) {
    const parts = path.split(".");
    let current = object;
    for (let index = 0; index < parts.length - 1; index += 1) {
      const key = parts[index];
      if (
        current[key] === null ||
        typeof current[key] !== "object" ||
        Array.isArray(current[key])
      ) {
        current[key] = {};
      }
      current = current[key];
    }
    current[parts[parts.length - 1]] = value;
  }

  function deletePath(object, path) {
    const parts = path.split(".");
    let current = object;
    for (let index = 0; index < parts.length - 1; index += 1) {
      current = current ? current[parts[index]] : null;
      if (!current || typeof current !== "object") return;
    }
    if (current && typeof current === "object") {
      delete current[parts[parts.length - 1]];
    }
  }

  async function api(name, payload = {}) {
    const response = await fetch(`/api/${name}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Frosted-Token": TOKEN,
      },
      body: JSON.stringify(payload),
    });
    let data = {};
    try {
      data = await response.json();
    } catch {
      data = {};
    }
    if (!response.ok) {
      const error = new Error(data.message || `HTTP ${response.status}`);
      error.data = data;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function showToast(message, kind = "") {
    clearTimeout(state.toastTimer);
    dom.toast.textContent = message;
    dom.toast.className = `toast ${kind}`.trim();
    dom.toast.hidden = false;
    state.toastTimer = setTimeout(() => {
      dom.toast.hidden = true;
    }, 4200);
  }

  function setBusy(message) {
    state.busy = true;
    dom.status.textContent = message;
    dom.status.className = "status";
  }

  function updateStatus() {
    if (state.busy) return;
    const errors = state.issues.filter((issue) => issue.level === "error").length;
    const warnings = state.issues.filter((issue) => issue.level === "warning").length;
    if (errors > 0) {
      dom.status.textContent = countLabel("errors", errors);
      dom.status.className = "status error";
    } else if (warnings > 0) {
      dom.status.textContent = countLabel("warnings", warnings);
      dom.status.className = "status warn";
    } else {
      dom.status.textContent = S("validation_ok");
      dom.status.className = "status ok";
    }
  }

  function updateDirty() {
    dom.dirty.hidden = !state.dirty;
  }

  function markDirty() {
    state.dirty = true;
    state.tomlStale = true;
    state.rawDirty = false;
    updateDirty();
  }

  function scheduleValidate() {
    clearTimeout(state.validateTimer);
    state.validateTimer = setTimeout(validate, 450);
  }

  // ------------------------------------------------------------- navigation

  function issueSection(where) {
    if (!where) return null;
    const rules = [
      ["iso", "iso"],
      ["system", "system"],
      ["user", "user"],
      ["desktop", "desktop"],
      ["packages", "packages"],
      ["kernel", "packages"],
      ["apt", "repositories"],
      ["build.mirror", "repositories"],
      ["build.security_mirror", "repositories"],
      ["build.archive_areas", "repositories"],
      ["build.extra_repositories", "repositories"],
      ["build.repository_keys", "repositories"],
      ["build.repositories_in_image", "repositories"],
      ["build.updates", "repositories"],
      ["build.backports", "repositories"],
      ["build.proposed_updates", "repositories"],
      ["build.security", "repositories"],
      ["build.source", "repositories"],
      ["boot", "boot_image"],
      ["binary", "boot_image"],
      ["build.bootloaders", "boot_image"],
      ["build.secure_boot", "boot_image"],
      ["build.memtest", "boot_image"],
      ["installer", "installer"],
      ["build.firmware_binary", "installer"],
      ["ssh", "custom"],
      ["scripts", "custom"],
      ["files", "custom"],
      ["build", "build"],
    ];
    for (const [prefix, section] of rules) {
      if (
        where === prefix ||
        where.startsWith(`${prefix}.`) ||
        where.startsWith(`${prefix}[`)
      ) {
        return section;
      }
    }
    return null;
  }

  function issueCounts() {
    const counts = {};
    for (const issue of state.issues) {
      const section = issueSection(issue.where);
      if (!section) continue;
      if (!counts[section]) counts[section] = { errors: 0, warnings: 0 };
      if (issue.level === "error") counts[section].errors += 1;
      else counts[section].warnings += 1;
    }
    return counts;
  }

  function renderNav() {
    clear(dom.nav);
    const counts = issueCounts();
    for (const section of state.sections) {
      const label = el("span", { text: section.label });
      const button = el(
        "button",
        {
          type: "button",
          class: state.active === section.key ? "active" : "",
        },
        label
      );
      const count = counts[section.key];
      if (count && count.errors > 0) {
        button.append(el("span", { class: "badge", text: String(count.errors) }));
      } else if (count && count.warnings > 0) {
        button.append(
          el("span", { class: "warn-badge", text: String(count.warnings) })
        );
      }
      button.addEventListener("click", () => switchView(section.key));
      dom.nav.append(button);
    }
    for (const [key, label] of [
      ["raw", S("raw")],
      ["build", S("commands")],
    ]) {
      const button = el(
        "button",
        {
          type: "button",
          class: state.active === key ? "active" : "",
        },
        el("span", { text: label })
      );
      button.addEventListener("click", () => switchView(key));
      dom.nav.append(button);
    }
  }

  function switchView(key) {
    // TOML タブで編集中なら、フォームへ移る前に内容を反映する。
    // ここで捨てると、raw の変更が黙って消えてしまう。
    if (key !== "raw" && key !== "build" && state.rawDirty) {
      parseRaw(key);
      return;
    }
    showView(key);
  }

  function showView(key) {
    state.active = key;
    renderNav();
    const isForm = key !== "raw" && key !== "build";
    dom.formPanel.hidden = !isForm;
    dom.rawPanel.hidden = key !== "raw";
    dom.buildPanel.hidden = key !== "build";
    if (key === "raw") renderRaw();
    else if (key === "build") renderCommands();
    else renderForm();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ------------------------------------------------------------------- form

  function renderAll() {
    dom.path.value = state.path || "";
    if (!state.sections.some((section) => section.key === state.active)) {
      state.active = state.sections[0]?.key || "raw";
    }
    renderNav();
    const isForm = state.active !== "raw" && state.active !== "build";
    dom.formPanel.hidden = !isForm;
    dom.rawPanel.hidden = state.active !== "raw";
    dom.buildPanel.hidden = state.active !== "build";
    if (state.active === "raw") renderRaw();
    else if (state.active === "build") renderCommands();
    else renderForm();
    renderIssues();
    renderSummary();
    updateDirty();
    updateStatus();
  }

  function renderForm() {
    clear(dom.form);
    const section = state.sections.find((item) => item.key === state.active);
    if (!section) {
      dom.sectionTitle.textContent = "";
      dom.form.append(el("p", { class: "muted", text: S("no_recipe") }));
      return;
    }
    dom.sectionTitle.textContent = section.label;
    if (section.key === "custom") {
      dom.form.append(el("p", { class: "section-note", text: S("files_note") }));
    }
    for (const field of section.fields) {
      dom.form.append(renderField(field));
    }
  }

  function renderField(field) {
    const value = getPath(state.recipe, field.path);
    const id = `f-${field.path.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    const control = createControl(field, value, id);
    control.dataset.path = field.path;
    const label = el(
      "label",
      { for: id },
      field.label,
      field.required ? el("span", { class: "required", text: "*" }) : null
    );
    const helpParts = [field.help];
    if (field.kind === "list") helpParts.push(S("list_hint"));
    if (field.kind === "path") helpParts.push(S("path_hint"));
    const helpText = helpParts.filter(Boolean).join(" ");
    return el(
      "div",
      { class: "field" },
      label,
      el(
        "div",
        { class: "field-control" },
        control,
        helpText ? el("p", { class: "field-help", text: helpText }) : null
      )
    );
  }

  function createControl(field, value, id) {
    const onChange = () => {
      markDirty();
      scheduleValidate();
    };

    if (field.kind === "bool") {
      const input = el("input", { type: "checkbox", id });
      input.checked = value === true;
      input.addEventListener("change", () => {
        setPath(state.recipe, field.path, input.checked);
        onChange();
      });
      return input;
    }

    if (field.kind === "tristate") {
      const select = el("select", { id });
      select.append(
        el("option", { value: "unset", text: S("unset") }),
        el("option", { value: "true", text: S("yes") }),
        el("option", { value: "false", text: S("no") })
      );
      select.value = value === true ? "true" : value === false ? "false" : "unset";
      select.addEventListener("change", () => {
        if (select.value === "unset") deletePath(state.recipe, field.path);
        else setPath(state.recipe, field.path, select.value === "true");
        onChange();
      });
      return select;
    }

    if (field.kind === "select") {
      const select = el("select", { id });
      const options = field.options || [];
      for (const option of options) {
        const text =
          option.value === "" ? S("unset") : option.label || option.value;
        select.append(el("option", { value: option.value, text }));
      }
      const current = value === null || value === undefined ? "" : String(value);
      if (current && !options.some((option) => option.value === current)) {
        select.append(el("option", { value: current, text: current }));
      }
      select.value = current;
      select.addEventListener("change", () => {
        setPath(state.recipe, field.path, select.value);
        onChange();
      });
      return select;
    }

    if (field.kind === "int") {
      const input = el("input", { type: "number", step: "1", id });
      input.value = value === null || value === undefined ? "" : String(value);
      input.addEventListener("input", () => {
        if (input.value.trim() === "") {
          deletePath(state.recipe, field.path);
        } else {
          const number = Number(input.value);
          if (Number.isFinite(number)) {
            setPath(state.recipe, field.path, Math.trunc(number));
          } else {
            deletePath(state.recipe, field.path);
          }
        }
        onChange();
      });
      return input;
    }

    if (field.kind === "list") {
      const textarea = el("textarea", { id, rows: "3" });
      textarea.value = Array.isArray(value) ? value.join("\n") : "";
      textarea.addEventListener("input", () => {
        const items = textarea.value
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean);
        setPath(state.recipe, field.path, items);
        onChange();
      });
      return textarea;
    }

    if (field.kind === "textarea") {
      const textarea = el("textarea", { id, rows: "8" });
      textarea.value = typeof value === "string" ? value : "";
      textarea.addEventListener("input", () => {
        setPath(state.recipe, field.path, textarea.value);
        onChange();
      });
      return textarea;
    }

    const input = el("input", {
      type: field.kind === "password" ? "password" : "text",
      id,
      placeholder: field.placeholder || "",
      autocomplete: field.kind === "password" ? "new-password" : "off",
      spellcheck: "false",
    });
    input.value = value === null || value === undefined ? "" : String(value);
    input.addEventListener("input", () => {
      setPath(state.recipe, field.path, input.value);
      onChange();
    });
    return input;
  }

  // ----------------------------------------------------------------- issues

  function renderIssues() {
    clear(dom.issues);
    if (!state.issues.length) {
      dom.issues.append(el("p", { class: "muted", text: S("no_issues") }));
      return;
    }
    for (const issue of state.issues) {
      const body = el("div");
      if (issue.where) {
        body.append(el("div", { class: "where", text: issue.where }));
      }
      if (issue.where) {
        body.append(
          el(
            "button",
            {
              type: "button",
              text: issue.message,
              onclick: () => focusIssue(issue.where),
            }
          )
        );
      } else {
        body.append(el("div", { text: issue.message }));
      }
      if (issue.hint) {
        body.append(el("div", { class: "hint", text: issue.hint }));
      }
      dom.issues.append(
        el("div", { class: `issue ${issue.level}` }, body)
      );
    }
  }

  function escapeSelector(value) {
    if (window.CSS && typeof CSS.escape === "function") return CSS.escape(value);
    return String(value).replace(/["\\]/g, "\\$&");
  }

  function focusIssue(where) {
    const section = issueSection(where);
    if (section && state.active !== section) switchView(section);
    let control = document.querySelector(`[data-path="${escapeSelector(where)}"]`);
    if (!control) {
      for (const candidate of document.querySelectorAll("[data-path]")) {
        const path = candidate.dataset.path;
        if (path.startsWith(where) || where.startsWith(path)) {
          control = candidate;
          break;
        }
      }
    }
    if (control) {
      control.scrollIntoView({ block: "center", behavior: "smooth" });
      control.focus({ preventScroll: true });
    }
  }

  // ---------------------------------------------------------------- summary

  function renderSummary() {
    clear(dom.summary);
    if (!state.summary) {
      dom.summary.append(el("p", { class: "muted", text: "-" }));
      return;
    }
    const summary = state.summary;
    const dl = el("dl");
    for (const [label, value] of [
      [S("output"), summary.output],
      [S("base"), summary.base],
      [S("desktop"), summary.desktop],
      [S("workdir"), summary.workdir],
    ]) {
      dl.append(el("dt", { text: label }), el("dd", { text: value }));
    }
    dom.summary.append(dl);

    dom.summary.append(
      el(
        "details",
        {},
        el("summary", { text: S("bootappend") }),
        el("pre", { text: summary.bootappend })
      )
    );
    dom.summary.append(
      el(
        "details",
        {},
        el("summary", { text: S("lb_args") }),
        el("pre", { text: (summary.lb_args || []).join("\n") })
      )
    );
    if (summary.warnings && summary.warnings.length) {
      const notice = el("div", { class: "notice" });
      for (const warning of summary.warnings) {
        notice.append(el("div", { text: warning }));
      }
      dom.summary.append(notice);
    }
  }

  // --------------------------------------------------------------- commands

  function renderCommands() {
    clear(dom.commands);
    if (!state.summary || !state.summary.commands) {
      dom.commands.append(el("p", { class: "muted", text: "-" }));
      return;
    }
    const commands = state.summary.commands;
    for (const [key, label] of [
      ["build", S("build_command")],
      ["test", S("test_command")],
    ]) {
      if (!commands[key]) continue;
      dom.commands.append(
        el(
          "div",
          { class: "command" },
          el("div", { class: "command-label", text: label }),
          el("code", { text: commands[key] }),
          el(
            "button",
            {
              type: "button",
              class: "ghost",
              text: S("copy"),
              onclick: () => copyText(commands[key]),
            }
          )
        )
      );
    }
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      showToast(S("copied"), "ok");
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      document.body.append(textarea);
      textarea.select();
      try {
        document.execCommand("copy");
        showToast(S("copied"), "ok");
      } catch {
        showToast(text, "");
      }
      textarea.remove();
    }
  }

  // ------------------------------------------------------------------- raw

  function renderRaw() {
    dom.rawText.value = state.toml || "";
    dom.rawHelp.textContent = S("raw_help");
    dom.rawStale.hidden = !state.tomlStale;
    dom.rawStale.textContent = S("raw_stale");
  }

  async function renderRawFromForm() {
    if (state.busy) return;
    setBusy(S("generating"));
    try {
      const data = await api("render", {
        path: state.path,
        recipe: state.recipe,
      });
      state.toml = data.toml;
      state.tomlStale = false;
      state.rawDirty = false;
      if (data.summary) state.summary = data.summary;
      dom.rawText.value = state.toml;
      dom.rawStale.hidden = true;
      renderSummary();
      showToast(S("rendered"), "ok");
    } catch (error) {
      handleError(error);
    } finally {
      state.busy = false;
      updateStatus();
    }
  }

  async function parseRaw(targetKey = null) {
    if (typeof targetKey !== "string") targetKey = null;
    if (state.busy) return;
    setBusy(S("loading"));
    try {
      const data = await api("parse", {
        path: state.path,
        text: dom.rawText.value,
      });
      applyData(data, true);
      state.tomlStale = false;
      state.rawDirty = false;
      renderAll();
      const target = targetKey || state.sections[0]?.key;
      if (target) showView(target);
      showToast(S("loaded_form"), "ok");
    } catch (error) {
      handleError(error);
    } finally {
      state.busy = false;
      updateStatus();
    }
  }

  async function saveRaw() {
    if (state.busy) return;
    setBusy(S("saving"));
    try {
      const data = await api("save_raw", {
        path: state.path,
        text: dom.rawText.value,
      });
      applyData(data, false);
      showToast(S("saved"), "ok");
    } catch (error) {
      handleError(error);
    } finally {
      state.busy = false;
      updateStatus();
    }
  }

  // ------------------------------------------------------------------ data

  function applyData(data, dirty) {
    if (data.recipe) state.recipe = data.recipe;
    if (data.path) state.path = data.path;
    if (typeof data.toml === "string") state.toml = data.toml;
    state.issues = data.issues || [];
    state.summary = data.summary || state.summary;
    state.tomlStale = false;
    state.rawDirty = false;
    state.dirty = dirty;
    renderAll();
  }

  async function validate() {
    if (!state.recipe) return;
    const sequence = ++state.validateSeq;
    setBusy(S("validating"));
    try {
      const data = await api("validate", {
        path: state.path,
        recipe: state.recipe,
      });
      if (sequence !== state.validateSeq) return;
      state.issues = data.issues || [];
      state.summary = data.summary || null;
      renderIssues();
      renderSummary();
      renderNav();
    } catch (error) {
      if (sequence === state.validateSeq) handleError(error);
    } finally {
      if (sequence === state.validateSeq) {
        state.busy = false;
        updateStatus();
      }
    }
  }

  async function openRecipe() {
    if (state.busy) return;
    if (state.dirty && !window.confirm(S("unsaved_confirm"))) return;
    const path = dom.path.value.trim();
    if (!path) {
      showToast(S("invalid_path"), "error");
      return;
    }
    setBusy(S("loading"));
    try {
      const data = await api("load", { path });
      applyData(data, false);
      const first = state.sections[0]?.key;
      if (first) switchView(first);
    } catch (error) {
      handleError(error);
    } finally {
      state.busy = false;
      updateStatus();
    }
  }

  async function saveRecipe() {
    if (state.busy) return;
    if (state.active === "raw" && state.rawDirty) {
      await saveRaw();
      return;
    }
    if (state.rawDirty) {
      showToast(S("raw_stale"), "error");
      switchView("raw");
      return;
    }
    let path = dom.path.value.trim() || state.path;
    if (!path) path = "mylinux.toml";
    state.path = path;
    setBusy(S("saving"));
    try {
      const data = await api("save", {
        path,
        recipe: state.recipe,
      });
      applyData(data, false);
      const backup = data.backup
        ? ` ${fmt(S("backup"), { path: data.backup })}`
        : "";
      showToast(`${S("saved")}${backup}`, "ok");
    } catch (error) {
      handleError(error);
    } finally {
      state.busy = false;
      updateStatus();
    }
  }

  async function generateConfig() {
    if (state.busy) return;
    setBusy(S("generating"));
    try {
      const data = await api("generate", {
        path: state.path,
        recipe: state.recipe,
      });
      openGeneratedModal(data);
    } catch (error) {
      handleError(error);
    } finally {
      state.busy = false;
      updateStatus();
    }
  }

  function openGeneratedModal(data) {
    const content = el("div");
    content.append(
      el("p", {
        text: fmt(S("generated"), { count: data.created.length }),
      }),
      el("p", { class: "muted", text: data.workdir })
    );
    if (data.created.length) {
      const list = el("ul", { class: "file-list" });
      for (const file of data.created) list.append(el("li", { text: file }));
      content.append(list);
    }
    if (data.warnings && data.warnings.length) {
      const issues = el("div", { class: "issues" });
      for (const warning of data.warnings) {
        issues.append(
          el(
            "div",
            { class: "issue warning" },
            el("div", { text: warning })
          )
        );
      }
      content.append(issues);
    }
    content.append(
      el(
        "div",
        { class: "modal-actions" },
        el("button", {
          type: "button",
          class: "primary",
          text: S("close"),
          onclick: closeModal,
        })
      )
    );
    openModal(S("generated_files"), content);
  }

  // ----------------------------------------------------------------- modal

  function openModal(title, content) {
    dom.modalTitle.textContent = title;
    clear(dom.modalContent);
    dom.modalContent.append(content);
    dom.modal.hidden = false;
    const focusable = dom.modalContent.querySelector("input, select, button");
    if (focusable) focusable.focus();
  }

  function closeModal() {
    dom.modal.hidden = true;
    clear(dom.modalContent);
  }

  function newRecipe() {
    const nameInput = el("input", {
      type: "text",
      id: "new-name",
      value: "mylinux",
      placeholder: "mylinux",
      spellcheck: "false",
    });
    const presetSelect = el("select", { id: "new-preset" });
    presetSelect.append(el("option", { value: "", text: S("none") }));
    for (const preset of state.presets) {
      presetSelect.append(
        el("option", { value: preset.key, text: preset.label })
      );
    }
    const description = el("p", { class: "muted", text: S("preset_help") });
    const updateDescription = () => {
      const preset = state.presets.find(
        (item) => item.key === presetSelect.value
      );
      description.textContent = preset ? preset.description : S("preset_help");
    };
    presetSelect.addEventListener("change", updateDescription);

    const create = async () => {
      const name = nameInput.value.trim() || "mylinux";
      try {
        const data = await api("new", {
          name,
          preset: presetSelect.value,
        });
        applyData(data, true);
        closeModal();
        const first = state.sections[0]?.key;
        if (first) switchView(first);
        showToast(S("new"), "ok");
      } catch (error) {
        handleError(error);
      }
    };

    const content = el(
      "div",
      {},
      el(
        "div",
        { class: "form-row" },
        el("label", { for: "new-name", text: S("name") }),
        nameInput
      ),
      el(
        "div",
        { class: "form-row" },
        el("label", { for: "new-preset", text: S("preset") }),
        presetSelect
      ),
      description,
      el(
        "div",
        { class: "modal-actions" },
        el("button", {
          type: "button",
          class: "ghost",
          text: S("cancel"),
          onclick: closeModal,
        }),
        el("button", {
          type: "button",
          class: "primary",
          text: S("new"),
          onclick: create,
        })
      )
    );
    openModal(S("new_title"), content);
  }

  function openDoctor() {
    const network = el("input", { type: "checkbox", id: "doctor-network" });
    const results = el("div");
    const run = el("button", {
      type: "button",
      class: "primary",
      text: S("run_doctor"),
    });
    run.addEventListener("click", async () => {
      run.disabled = true;
      results.textContent = S("doctor_running");
      try {
        const data = await api("doctor", {
          path: state.path,
          recipe: state.recipe,
          network: network.checked,
        });
        clear(results);
        const fails = data.checks.filter(
          (check) => check.status === "fail"
        ).length;
        const warns = data.checks.filter(
          (check) => check.status === "warn"
        ).length;
        results.append(
          el("p", {
            text: fails
              ? countLabel("errors", fails)
              : warns
              ? countLabel("warnings", warns)
              : S("validation_ok"),
          })
        );
        const list = el("div", { class: "doctor-list" });
        const labels = { ok: "OK", warn: "!", fail: "NG", skip: "-" };
        for (const check of data.checks) {
          list.append(
            el(
              "div",
              { class: `doctor-check ${check.status}` },
              el("div", {
                class: "status-label",
                text: labels[check.status] || check.status,
              }),
              el("div", { class: "detail", text: check.detail }),
              check.hint && check.status !== "ok"
                ? el("div", { class: "hint", text: check.hint })
                : null
            )
          );
        }
        results.append(list);
      } catch (error) {
        handleError(error);
        results.textContent = error.message;
      } finally {
        run.disabled = false;
      }
    });

    const content = el(
      "div",
      {},
      el("p", { class: "muted", text: S("doctor_help") }),
      el(
        "label",
        { class: "check", for: "doctor-network" },
        network,
        S("doctor_network")
      ),
      run,
      results
    );
    openModal(S("doctor"), content);
  }

  // ----------------------------------------------------------------- error

  function handleError(error) {
    state.busy = false;
    if (error && error.data) {
      if (Array.isArray(error.data.issues) && error.data.issues.length) {
        state.issues = error.data.issues;
        renderIssues();
        renderNav();
      }
      const message = error.data.message || error.message;
      if (message) showToast(message, "error");
    } else {
      showToast(S("network_error"), "error");
    }
    updateStatus();
  }

  function showFatal(error) {
    const message =
      (error && error.data && error.data.message) ||
      (error && error.message) ||
      S("network_error");
    dom.fatal.hidden = false;
    dom.fatal.textContent = message;
    if (error && error.data && Array.isArray(error.data.issues)) {
      state.issues = error.data.issues;
      renderIssues();
    }
    dom.status.textContent = message;
    dom.status.className = "status error";
  }

  // ----------------------------------------------------------------- labels

  function applyLabels() {
    dom.pathLabel.textContent = S("recipe_path");
    dom.path.placeholder = "mylinux.toml";
    dom.openBtn.textContent = S("open");
    dom.newBtn.textContent = S("new");
    dom.saveBtn.textContent = S("save");
    dom.generateBtn.textContent = S("generate");
    dom.dirty.textContent = S("unsaved");
    dom.rawTitle.textContent = S("raw");
    dom.rawRenderBtn.textContent = S("form_toml");
    dom.rawParseBtn.textContent = S("load_into_form");
    dom.rawSaveBtn.textContent = S("save_raw");
    dom.rawHelp.textContent = S("raw_help");
    dom.buildTitle.textContent = S("commands");
    dom.buildNote.textContent = S("build_note");
    dom.summaryTitle.textContent = S("summary");
    dom.issuesTitle.textContent = S("issues");
    dom.doctorBtn.textContent = S("doctor");
    dom.version.textContent = state.version ? `v${state.version}` : "";
  }

  // ------------------------------------------------------------------ boot

  function bindStaticEvents() {
    dom.openBtn.addEventListener("click", openRecipe);
    dom.newBtn.addEventListener("click", newRecipe);
    dom.saveBtn.addEventListener("click", saveRecipe);
    dom.generateBtn.addEventListener("click", generateConfig);
    dom.doctorBtn.addEventListener("click", openDoctor);
    dom.rawRenderBtn.addEventListener("click", renderRawFromForm);
    dom.rawParseBtn.addEventListener("click", () => parseRaw());
    dom.rawSaveBtn.addEventListener("click", saveRaw);
    dom.path.addEventListener("input", () => {
      state.path = dom.path.value.trim();
    });
    dom.rawText.addEventListener("input", () => {
      state.toml = dom.rawText.value;
      state.tomlStale = false;
      state.rawDirty = true;
      state.dirty = true;
      updateDirty();
    });
    dom.modal.addEventListener("click", (event) => {
      if (event.target.closest("[data-close]")) closeModal();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !dom.modal.hidden) closeModal();
    });
    window.addEventListener("beforeunload", (event) => {
      if (state.dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
  }

  async function init() {
    bindStaticEvents();
    state.strings = { ...FALLBACK_STRINGS };
    applyLabels();
    dom.status.textContent = S("loading") || "Loading...";
    try {
      const data = await api("bootstrap");
      state.version = data.version || "";
      state.lang = data.lang || "ja";
      state.strings = data.strings || {};
      state.sections = data.sections || [];
      state.presets = data.presets || [];
      document.documentElement.lang = state.lang;
      applyLabels();
      applyData(data, false);
    } catch (error) {
      showFatal(error);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
