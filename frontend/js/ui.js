/**
 * UI 小工具：创建元素、消息提示、确认框、弹窗、分页、状态标签等。
 * 所有用户数据一律通过 textContent / 文本节点写入，避免 XSS。
 */

const ICON_NAMES = new Set([
  "dashboard", "scan", "borrow", "return", "records", "users", "user", "logout",
  "search", "plus", "edit", "ban", "check", "x", "chevron-left", "chevron-right",
  "menu", "info", "alert", "inbox", "refresh", "clock", "shield", "calendar",
  "box", "key",
]);

/** 返回内部图标（name 来自固定常量，不是用户输入）。 */
export function icon(name) {
  const safeName = ICON_NAMES.has(name) ? name : "info";
  return `<svg class="icon" aria-hidden="true"><use href="#i-${safeName}"></use></svg>`;
}

/**
 * 创建 DOM 元素。
 * html 属性只用于内部固定的图标字符串，禁止传入用户数据。
 */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else if (key === "html") node.innerHTML = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "style" && typeof value === "object") Object.assign(node.style, value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key in node) node[key] = value;
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function debounce(fn, wait = 280) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function initials(name) {
  const text = String(name || "?").trim();
  return text ? text.slice(0, 1).toUpperCase() : "?";
}

export function roleLabel(role) {
  return { admin: "管理员", staff: "工作人员", viewer: "访客" }[role] || role || "未知";
}

export function roleDescription(role) {
  return {
    admin: "管理用户、管理资料、办理借阅和归还。",
    staff: "查询资料、办理借阅和归还。",
    viewer: "只能查询资料和借阅记录。",
  }[role] || "";
}

export function formatDateTime(value) {
  if (!value) return "—";
  const text = String(value).trim();
  const date = new Date(text.replace(" ", "T") + "Z");
  if (Number.isNaN(date.getTime())) return text;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function localDateKey(value) {
  if (!value) return "";
  const date = new Date(String(value).trim().replace(" ", "T") + "Z");
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function localDateToUtcStart(dateText) {
  return new Date(`${dateText}T00:00:00`).toISOString().slice(0, 19).replace("T", " ");
}

export function localDateToUtcEnd(dateText) {
  return new Date(`${dateText}T23:59:59`).toISOString().slice(0, 19).replace("T", " ");
}

export function isOverdue(record) {
  if (!record || record.returned_at) return false;
  const text = String(record.due_at || "").trim();
  if (!text) return false;
  const due = new Date(text.replace(" ", "T") + "Z");
  return !Number.isNaN(due.getTime()) && due.getTime() < Date.now();
}

export function materialStatusPill(status) {
  const map = {
    available: ["可借阅", "pill-ok"],
    borrowed: ["已借出", "pill-info"],
    disabled: ["已停用", "pill-muted"],
  };
  const [text, className] = map[status] || [status || "未知", "pill-muted"];
  return el("span", { class: `pill ${className}`, text });
}

export function borrowStatusPill(record) {
  if (record && record.returned_at) return el("span", { class: "pill pill-muted", text: "已归还" });
  if (isOverdue(record)) return el("span", { class: "pill pill-danger", text: "已逾期" });
  return el("span", { class: "pill pill-info", text: "借阅中" });
}

export function toast(message, type = "info") {
  const stack = document.getElementById("toast-stack");
  if (!stack) return;
  const iconName = { success: "check", error: "alert", warn: "alert", info: "info" }[type] || "info";
  const node = el("div", { class: `toast toast-${type}`, role: "status" }, [
    el("span", { class: "toast-icon", html: icon(iconName) }),
    el("span", { class: "toast-text", text: message }),
  ]);
  stack.append(node);
  window.setTimeout(() => {
    node.style.transition = "opacity .18s ease, transform .18s ease";
    node.style.opacity = "0";
    node.style.transform = "translateY(6px)";
    window.setTimeout(() => node.remove(), 200);
  }, 4200);
}

export function openModal({ title, body, footer = [], large = false, onClose = null }) {
  const overlay = el("div", { class: "modal-overlay" });
  const closeButton = el("button", {
    class: "icon-btn",
    type: "button",
    "aria-label": "关闭",
    html: icon("x"),
  });

  const card = el("div", {
    class: `modal${large ? " modal-lg" : ""}`,
    role: "dialog",
    "aria-modal": "true",
    "aria-label": title,
  });

  const bodyNode = el("div", { class: "modal-body" }, [body]);
  card.append(
    el("div", { class: "modal-head" }, [
      el("h2", { class: "modal-title", text: title }),
      closeButton,
    ]),
    bodyNode,
  );
  if (footer.length) card.append(el("div", { class: "modal-foot" }, footer));

  overlay.append(card);
  document.body.append(overlay);
  document.body.classList.add("modal-open");

  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    overlay.remove();
    document.body.classList.remove("modal-open");
    document.removeEventListener("keydown", onKey);
    if (onClose) onClose();
  }
  function onKey(event) {
    if (event.key === "Escape") close();
  }
  closeButton.addEventListener("click", close);
  overlay.addEventListener("mousedown", (event) => {
    if (event.target === overlay) close();
  });
  document.addEventListener("keydown", onKey);

  const focusable = bodyNode.querySelector("input, select, textarea, button");
  if (focusable) focusable.focus();

  return { close, card, body: bodyNode };
}

export function confirmDialog({
  title = "请确认",
  message,
  confirmText = "确认",
  cancelText = "取消",
  danger = false,
} = {}) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };

    let modal = null;
    const cancelButton = el("button", {
      class: "btn btn-secondary",
      type: "button",
      text: cancelText,
      onclick: () => {
        finish(false);
        if (modal) modal.close();
      },
    });
    const confirmButton = el("button", {
      class: `btn ${danger ? "btn-danger" : "btn-primary"}`,
      type: "button",
      text: confirmText,
      onclick: () => {
        finish(true);
        if (modal) modal.close();
      },
    });

    modal = openModal({
      title,
      body: el("p", { class: "confirm-text", text: message }),
      footer: [cancelButton, confirmButton],
      onClose: () => finish(false),
    });
  });
}

export function setBusy(button, busy, busyText = "处理中…") {
  if (!button) return;
  if (busy) {
    if (!button.dataset.idleHtml) button.dataset.idleHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span><span>${busyText}</span>`;
  } else {
    button.disabled = false;
    if (button.dataset.idleHtml) {
      button.innerHTML = button.dataset.idleHtml;
      delete button.dataset.idleHtml;
    }
  }
}

export async function runBusy(button, task, busyText = "处理中…") {
  setBusy(button, true, busyText);
  try {
    return await task();
  } finally {
    setBusy(button, false);
  }
}

export function pagination({ page, totalPages, total, onChange }) {
  const safeTotalPages = Math.max(1, totalPages);
  const safePage = Math.min(Math.max(1, page), safeTotalPages);

  const info = el("span", {
    class: "pager-info",
    text: `第 ${safePage} / ${safeTotalPages} 页 · 共 ${total} 条`,
  });

  const actions = el("div", { class: "pager-actions" }, [
    el("button", {
      class: "page-btn",
      type: "button",
      "aria-label": "上一页",
      disabled: safePage <= 1,
      html: icon("chevron-left"),
      onclick: () => onChange(safePage - 1),
      title: "上一页",
    }),
    el("button", {
      class: "page-btn",
      type: "button",
      "aria-label": "下一页",
      disabled: safePage >= safeTotalPages,
      html: icon("chevron-right"),
      onclick: () => onChange(safePage + 1),
      title: "下一页",
    }),
  ]);

  return el("nav", { class: "pager", "aria-label": "分页" }, [info, actions]);
}

export function emptyState({ iconName = "inbox", title = "暂无数据", text = "", action = null } = {}) {
  const children = [
    el("div", { class: "empty-icon", html: icon(iconName) }),
    el("div", { class: "empty-title", text: title }),
  ];
  if (text) children.push(el("div", { class: "empty-text", text }));
  if (action) {
    children.push(
      el("button", {
        class: "btn btn-secondary btn-sm",
        type: "button",
        text: action.label,
        onclick: action.onClick,
      }),
    );
  }
  return el("div", { class: "empty-state" }, children);
}

export function errorState(error, onRetry) {
  const children = [
    el("div", { class: "error-icon", html: icon("alert") }),
    el("div", { class: "empty-title", text: "加载失败" }),
    el("div", { class: "empty-text", text: (error && error.message) || "请稍后重试" }),
  ];
  if (onRetry) {
    children.push(
      el("button", {
        class: "btn btn-secondary btn-sm",
        type: "button",
        text: "重新加载",
        onclick: onRetry,
      }),
    );
  }
  return el("div", { class: "error-state" }, children);
}

export function loadingRows(rows = 5) {
  const wrap = el("div", { class: "skeleton-rows" });
  for (let i = 0; i < rows; i += 1) {
    wrap.append(
      el("div", { class: "skeleton-row" }, [
        el("div", { class: "skeleton" }),
        el("div", { class: "skeleton" }),
        el("div", { class: "skeleton" }),
      ]),
    );
  }
  return wrap;
}

export function detailList(items) {
  const list = el("dl", { class: "detail-list" });
  for (const [label, value] of items) {
    list.append(el("dt", { text: label }), el("dd", {}, [value instanceof Node ? value : String(value ?? "—")]));
  }
  return list;
}

export function formErrorBox() {
  return el("div", { class: "form-error", role: "alert" });
}

export function showFormError(box, message) {
  if (!box) return;
  box.replaceChildren(el("span", { html: icon("alert") }), el("span", { text: message }));
  box.classList.add("is-visible");
}

export function hideFormError(box) {
  if (!box) return;
  box.classList.remove("is-visible");
  box.replaceChildren();
}

export function isAuthError(error) {
  return Boolean(error && error.status === 401);
}

export function errorMessage(error) {
  return (error && error.message) || "操作失败，请稍后重试";
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
