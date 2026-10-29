/**
 * 登录页、应用外壳、路由、仪表盘、个人信息。
 */

import { api } from "./api.js?v=0.9.1";
import { getUser, login, logout } from "./auth.js?v=0.9.1";
import {
  el, icon, toast, confirmDialog, formatDateTime, borrowStatusPill,
  roleLabel, roleDescription, emptyState, errorState, detailList, initials,
  isAuthError, errorMessage, setBusy, isOverdue,
} from "./ui.js?v=0.9.1";
import { renderMaterials } from "./materials.js?v=0.9.1";
import { renderBorrow, renderReturn, renderRecords } from "./borrows.js?v=0.9.1";
import { renderUsers } from "./users.js?v=0.9.1";
import { renderLogs } from "./logs.js?v=0.9.1";
import { renderBackup } from "./backup.js?v=0.9.1";

const ROUTES = [
  {
    id: "dashboard", title: "仪表盘", sub: "资料与借阅情况总览", icon: "dashboard",
    group: "工作台", roles: ["admin", "staff", "viewer"], render: renderDashboard,
  },
  {
    id: "materials", title: "资料管理", sub: "查询与维护医学影像资料", icon: "scan",
    group: "业务办理", roles: ["admin", "staff", "viewer"], render: renderMaterials,
  },
  {
    id: "borrow", title: "借阅办理", sub: "浏览可借阅资料并发起借阅", icon: "borrow",
    group: "业务办理", roles: ["admin", "staff"], render: renderBorrow,
  },
  {
    id: "return", title: "归还办理", sub: "处理尚未归还的借阅记录", icon: "return",
    group: "业务办理", roles: ["admin", "staff"], render: renderReturn,
  },
  {
    id: "records", title: "借阅记录", sub: "查询全部借阅历史", icon: "records",
    group: "业务办理", roles: ["admin", "staff", "viewer"], render: renderRecords,
  },
  {
    id: "users", title: "用户管理", sub: "管理系统账号、角色与状态", icon: "users",
    group: "系统管理", roles: ["admin"], render: renderUsers,
  },
  {
    id: "logs", title: "操作日志", sub: "查看与导出系统操作记录", icon: "records",
    group: "系统管理", roles: ["admin"], render: renderLogs,
  },
  {
    id: "backup", title: "数据备份", sub: "数据库备份与恢复", icon: "box",
    group: "系统管理", roles: ["admin"], render: renderBackup,
  },
  {
    id: "profile", title: "个人信息", sub: "账户信息与安全退出", icon: "user",
    group: "系统管理", roles: ["admin", "staff", "viewer"], render: renderProfile,
  },
];

let shellCleanup = null;

/* ------------------------------ 登录页 ------------------------------ */

export function renderLogin(root, { message = "", onSuccess } = {}) {
  root.replaceChildren();
  document.title = "登录 · 医学影像资料借阅管理系统";

  const errorBox = el("div", { class: "form-error", role: "alert" });
  const usernameInput = el("input", {
    class: "input", id: "login-username", name: "username", type: "text",
    placeholder: "请输入用户名", autocomplete: "username", maxlength: 50, required: true,
  });
  const passwordInput = el("input", {
    class: "input", id: "login-password", name: "password", type: "password",
    placeholder: "请输入密码", autocomplete: "current-password", required: true,
  });
  const submitButton = el("button", { class: "btn btn-primary", type: "submit" }, [
    el("span", { html: icon("key") }),
    el("span", { text: "登录系统" }),
  ]);

  const form = el("form", { class: "login-form", novalidate: true }, [
    el("div", { class: "field" }, [
      el("label", { class: "field-label", for: "login-username" }, ["用户名"]),
      usernameInput,
    ]),
    el("div", { class: "field" }, [
      el("label", { class: "field-label", for: "login-password" }, ["密码"]),
      passwordInput,
    ]),
    errorBox,
    submitButton,
  ]);

  let submitting = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitting) return;
    const username = usernameInput.value.trim();
    const password = passwordInput.value;
    if (!username || !password) {
      showLoginError(errorBox, "请输入用户名和密码");
      return;
    }
    submitting = true;
    errorBox.classList.remove("is-visible");
    setBusy(submitButton, true, "登录中…");
    try {
      const user = await login(username, password);
      passwordInput.value = "";
      onSuccess(user);
    } catch (error) {
      showLoginError(errorBox, errorMessage(error));
    } finally {
      submitting = false;
      setBusy(submitButton, false);
    }
  });

  const brandFeature = (iconName, title, text) =>
    el("div", { class: "brand-feature" }, [
      el("span", { class: "icon-wrap", html: icon(iconName) }),
      el("div", {}, [el("div", { text: title }), el("small", { text })]),
    ]);

  const page = el("div", { class: "login-page" }, [
    el("section", { class: "login-brand" }, [
      el("div", { class: "brand-top" }, [
        el("div", { class: "brand-logo", html: icon("scan") }),
        el("div", { class: "brand-name" }, [
          "医学影像资料借阅管理",
          el("span", { text: "MEDICAL IMAGING LENDING" }),
        ]),
      ]),
      el("div", { class: "brand-body" }, [
        el("h1", { class: "brand-title" }, [
          "让每一份影像资料",
          el("br"),
          "都可查、可借、可追溯",
        ]),
        el("p", { class: "brand-sub" }, [
          "面向影像科的资料借阅管理平台，统一管理资料档案、借阅流程与归还记录。",
        ]),
        el("div", { class: "brand-features" }, [
          brandFeature("box", "资料集中管理", "编号、检查类型、载体与存放位置清晰可查"),
          brandFeature("records", "借阅全程留痕", "借出、应还与归还时间完整保存"),
          brandFeature("shield", "角色权限分明", "管理员、工作人员、访客各司其职"),
        ]),
      ]),
      el("div", { class: "brand-foot", text: "本科课程设计 · 医学影像资料借阅管理系统" }),
    ]),
    el("section", { class: "login-panel" }, [
      el("div", { class: "login-card" }, [
        el("div", { class: "login-head" }, [
          el("span", { class: "eyebrow", text: "ACCOUNT LOGIN" }),
          el("h2", { class: "login-title", text: "欢迎回来" }),
          el("p", { class: "login-desc", text: "请使用系统账号登录，登录状态仅保留在当前标签页。" }),
        ]),
        form,
        el("p", { class: "login-note" }, [
          el("strong", { text: "角色说明：" }),
          "管理员可管理用户与资料；工作人员可办理借阅与归还；访客只能查询资料和借阅记录。",
        ]),
      ]),
    ]),
  ]);

  root.append(page);
  if (message) showLoginError(errorBox, message);
}

function showLoginError(box, message) {
  box.replaceChildren(el("span", { html: icon("alert") }), el("span", { text: message }));
  box.classList.add("is-visible");
}

/* ------------------------------ 应用外壳 ------------------------------ */

export function mountApp(root, { onLoggedOut } = {}) {
  const user = getUser();
  if (!user) return;

  if (shellCleanup) shellCleanup();
  root.replaceChildren();

  const view = el("main", { class: "view", id: "view" });
  const pageTitle = el("div", { class: "page-title", text: "仪表盘" });
  const pageSub = el("div", { class: "page-sub", text: "" });
  const nav = el("nav", { class: "nav", "aria-label": "主导航" });
  const navLinks = new Map();

  const groups = [...new Set(ROUTES.map((route) => route.group))];
  for (const group of groups) {
    const items = ROUTES.filter((route) => route.group === group && route.roles.includes(user.role));
    if (!items.length) continue;
    const groupNode = el("div", { class: "nav-group" }, [el("div", { class: "nav-label", text: group })]);
    for (const route of items) {
      const link = el("a", {
        class: "nav-item",
        href: `#/${route.id}`,
        id: `nav-${route.id}`,
      }, [
        el("span", { html: icon(route.icon) }),
        el("span", { class: "nav-text", text: route.title }),
      ]);
      link.addEventListener("click", () => layout.classList.remove("sidebar-open"));
      navLinks.set(route.id, link);
      groupNode.append(link);
    }
    nav.append(groupNode);
  }

  const layout = el("div", { class: "layout", id: "layout" });
  const sidebarOverlay = el("div", { class: "sidebar-overlay" });
  sidebarOverlay.addEventListener("click", () => layout.classList.remove("sidebar-open"));

  const sidebar = el("aside", { class: "sidebar" }, [
    el("div", { class: "sidebar-brand" }, [
      el("div", { class: "brand-mark", html: icon("scan") }),
      el("div", { class: "brand-text" }, [
        el("div", { class: "title", text: "影像资料借阅" }),
        el("div", { class: "sub", text: "MEDICAL IMAGING" }),
      ]),
    ]),
    nav,
    el("div", { class: "sidebar-foot" }, [
      el("div", { class: "user-mini" }, [
        el("div", { class: "avatar", text: initials(user.username) }),
        el("div", { class: "user-mini-text" }, [
          el("div", { class: "user-mini-name", text: user.username }),
          el("div", { class: "user-mini-role", text: `${roleLabel(user.role)} · ${user.is_active ? "启用中" : "已停用"}` }),
        ]),
      ]),
    ]),
  ]);

  const menuButton = el("button", {
    class: "icon-btn menu-btn",
    type: "button",
    "aria-label": "打开导航",
    html: icon("menu"),
  });
  menuButton.addEventListener("click", () => layout.classList.add("sidebar-open"));

  const logoutButton = el("button", {
    class: "icon-btn",
    type: "button",
    "aria-label": "退出登录",
    title: "退出登录",
    html: icon("logout"),
  });
  logoutButton.addEventListener("click", async () => {
    const confirmed = await confirmDialog({
      title: "退出登录",
      message: "确认退出当前账号？",
      confirmText: "退出登录",
    });
    if (!confirmed) return;
    await logout();
    if (onLoggedOut) onLoggedOut();
  });

  const topbar = el("header", { class: "topbar" }, [
    menuButton,
    el("div", { class: "page-head" }, [pageTitle, pageSub]),
    el("div", { class: "topbar-right" }, [
      el("span", { class: "role-badge" }, [
        el("span", { html: icon("shield") }),
        el("span", { text: roleLabel(user.role) }),
      ]),
      el("div", { class: "topbar-user" }, [
        el("div", { class: "avatar", text: initials(user.username) }),
        el("div", { class: "topbar-name", text: user.username }),
      ]),
      logoutButton,
    ]),
  ]);

  layout.append(sidebar, sidebarOverlay, el("div", { class: "main-wrap" }, [topbar, view]));
  root.append(layout);

  function currentRoute() {
    const id = (location.hash || "").replace(/^#\/?/, "").split("/")[0].trim();
    return ROUTES.find((route) => route.id === id) || ROUTES[0];
  }

  function setActive(routeId) {
    for (const [id, link] of navLinks) {
      link.classList.toggle("active", id === routeId);
      if (id === routeId) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
  }

  let renderSequence = 0;
  let sessionSync = null;

  // 后端会实时按数据库里的角色鉴权；这里在切换页面/回到标签页时同步一次，
  // 如果角色或状态被管理员改过，就整页刷新，让导航和按钮保持与后端一致。
  async function syncSession() {
    if (sessionSync) return sessionSync;
    sessionSync = (async () => {
      try {
        const fresh = await api.me();
        const cached = getUser();
        const changed =
          !cached ||
          fresh.role !== cached.role ||
          Boolean(fresh.is_active) !== Boolean(cached.is_active);
        if (changed) {
          window.location.reload();
          return false;
        }
        return true;
      } catch (error) {
        if (isAuthError(error)) return false;
        return true;
      } finally {
        sessionSync = null;
      }
    })();
    return sessionSync;
  }

  function handleVisibilityChange() {
    if (!document.hidden) syncSession();
  }

  async function renderRoute() {
    const sequence = ++renderSequence;
    if (!(await syncSession())) return;
    if (sequence !== renderSequence) return;

    const route = currentRoute();
    if (!route.roles.includes(user.role)) {
      toast("当前角色无权访问该页面", "warn");
      location.hash = "#/dashboard";
      return;
    }
    setActive(route.id);
    pageTitle.textContent = route.title;
    pageSub.textContent = route.sub;
    document.title = `${route.title} · 医学影像资料借阅管理系统`;

    // 每次渲染使用独立容器：快速切换菜单时，先发出的慢请求只会写入已分离的旧容器，
    // 不会把后一个页面覆盖掉。
    const container = el("div", { class: "route-container" });
    view.replaceChildren(container);

    try {
      await route.render(container, { user, onLoggedOut, navigate });
    } catch (error) {
      if (sequence === renderSequence && !isAuthError(error)) {
        container.replaceChildren(errorState(error, renderRoute));
      }
    }
    if (sequence === renderSequence) window.scrollTo(0, 0);
  }

  function navigate(routeId) {
    location.hash = `#/${routeId}`;
  }

  window.addEventListener("hashchange", renderRoute);
  window.addEventListener("focus", syncSession);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  shellCleanup = () => {
    window.removeEventListener("hashchange", renderRoute);
    window.removeEventListener("focus", syncSession);
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  };

  renderRoute();
}

/* ------------------------------ 仪表盘 ------------------------------ */

export async function renderDashboard(view, { user, navigate }) {
  const today = new Date().toLocaleDateString("zh-CN", {
    year: "numeric", month: "long", day: "numeric", weekday: "long",
  });

  const actions = el("div", { class: "hero-actions" }, [
    el("button", {
      class: "btn btn-secondary",
      type: "button",
      html: icon("scan"),
      onclick: () => navigate("materials"),
    }, [el("span", { text: "资料管理" })]),
  ]);
  if (user.role !== "viewer") {
    actions.append(
      el("button", {
        class: "btn btn-primary",
        type: "button",
        html: icon("borrow"),
        onclick: () => navigate("borrow"),
      }, [el("span", { text: "借阅办理" })]),
    );
  }

  const hero = el("div", { class: "page-hero" }, [
    el("div", {}, [
      el("h1", { class: "hero-title", text: `你好，${user.username}` }),
      el("p", { class: "hero-sub", text: `${today} · ${roleLabel(user.role)}` }),
    ]),
    actions,
  ]);

  const content = el("div");
  view.append(hero, content);
  content.append(el("div", { class: "loading-block" }, [el("span", { class: "spinner spinner-lg" }), el("p", { text: "正在加载数据…" })]));

  try {
    const [materials, activeBorrows, history] = await Promise.all([
      api.materials(),
      api.activeBorrows(),
      api.history(),
    ]);

    const available = materials.filter((item) => item.status === "available").length;
    const borrowed = materials.filter((item) => item.status === "borrowed").length;
    const mine = activeBorrows.filter((record) => record.borrower_id === user.id);
    const recent = history.slice(0, 6);

    const statCard = (label, value, foot, iconName, tone) =>
      el("div", { class: "stat-card" }, [
        el("div", { class: `stat-icon ${tone || ""}`, html: icon(iconName) }),
        el("div", {}, [
          el("div", { class: "stat-label", text: label }),
          el("div", { class: "stat-value", text: String(value) }),
          el("div", { class: "stat-foot", text: foot }),
        ]),
      ]);

    const stats = el("div", { class: "stat-grid" }, [
      statCard("资料总数", materials.length, "含已停用资料", "box", ""),
      statCard("可借阅", available, "当前可办理借阅", "check", "ok"),
      statCard("已借出", borrowed, "尚未归还", "borrow", "warn"),
      statCard("我的在借", mine.length, user.role === "viewer" ? "访客账号不可借阅" : "由我经办未归还", "clock", "muted"),
    ]);

    const mineCard = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("div", {}, [
          el("div", { class: "card-title" }, [el("span", { html: icon("clock") }), el("span", { text: "我的借阅" })]),
          el("div", { class: "card-sub", text: "当前仍未归还的借阅记录" }),
        ]),
        el("button", {
          class: "btn btn-ghost btn-sm",
          type: "button",
          text: "查看全部记录",
          onclick: () => navigate("records"),
        }),
      ]),
      mine.length
        ? el("div", { class: "table-wrap" }, [
            el("table", { class: "table" }, [
              el("thead", {}, [el("tr", {}, [
                el("th", { text: "资料" }), el("th", { text: "应还时间" }), el("th", { text: "状态" }),
              ])]),
              el("tbody", {}, mine.map((record) =>
                el("tr", {}, [
                  el("td", {}, [
                    el("div", { class: "cell-main", text: record.title }),
                    el("div", { class: "cell-sub", text: record.material_code }),
                  ]),
                  el("td", { text: formatDateTime(record.due_at) }),
                  el("td", {}, [borrowStatusPill(record)]),
                ]),
              )),
            ]),
          ])
        : emptyState({ iconName: "inbox", title: "当前没有未归还的借阅", text: "借阅成功后会在这里显示" }),
    ]);

    const quickItems = [
      ["materials", "scan", "资料管理", "查询资料与状态"],
      ["records", "records", "借阅记录", "查看完整借阅历史"],
    ];
    if (user.role !== "viewer") {
      quickItems.unshift(["borrow", "borrow", "借阅办理", "为资料办理借出"]);
      quickItems.push(["return", "return", "归还办理", "处理未归还记录"]);
    }
    if (user.role === "admin") quickItems.push(["users", "users", "用户管理", "账号、角色与状态"]);

    const quickCard = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("div", { class: "card-title" }, [el("span", { html: icon("dashboard") }), el("span", { text: "快捷操作" })]),
      ]),
      el("div", { class: "card-body" }, [
        el("div", { class: "permission-list" }, quickItems.map(([routeId, iconName, title, desc]) =>
          el("button", {
            class: "btn btn-ghost",
            type: "button",
            style: { justifyContent: "flex-start", height: "auto", padding: "10px 12px" },
            onclick: () => navigate(routeId),
          }, [
            el("span", { class: "stat-icon", style: { width: "34px", height: "34px", borderRadius: "9px" }, html: icon(iconName) }),
            el("span", {}, [
              el("span", { style: { display: "block", fontWeight: "600" }, text: title }),
              el("span", { style: { display: "block", fontSize: "12px", color: "var(--ink-400)", fontWeight: "400" }, text: desc }),
            ]),
          ]),
        )),
      ]),
    ]);

    const recentCard = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("div", {}, [
          el("div", { class: "card-title" }, [el("span", { html: icon("records") }), el("span", { text: "最近借阅记录" })]),
          el("div", { class: "card-sub", text: "按借出时间倒序展示最近 6 条" }),
        ]),
        el("button", {
          class: "btn btn-ghost btn-sm", type: "button", text: "查看全部",
          onclick: () => navigate("records"),
        }),
      ]),
      recent.length
        ? el("div", { class: "table-wrap" }, [
            el("table", { class: "table" }, [
              el("thead", {}, [el("tr", {}, [
                el("th", { text: "资料" }), el("th", { text: "借阅人" }),
                el("th", { text: "借出时间" }), el("th", { text: "应还时间" }), el("th", { text: "状态" }),
              ])]),
              el("tbody", {}, recent.map((record) =>
                el("tr", {}, [
                  el("td", {}, [
                    el("div", { class: "cell-main", text: record.title }),
                    el("div", { class: "cell-sub", text: record.material_code }),
                  ]),
                  el("td", { text: record.borrower_username }),
                  el("td", { text: formatDateTime(record.borrowed_at) }),
                  el("td", {}, [
                    el("div", { text: formatDateTime(record.due_at) }),
                    isOverdue(record) ? el("span", { class: "pill pill-danger", text: "已逾期", style: { marginTop: "4px" } }) : null,
                  ]),
                  el("td", {}, [borrowStatusPill(record)]),
                ]),
              )),
            ]),
          ])
        : emptyState({ iconName: "inbox", title: "还没有借阅记录", text: "办理第一笔借阅后，这里会显示记录" }),
    ]);

    content.replaceChildren(
      stats,
      el("div", { class: "grid-2" }, [mineCard, quickCard]),
      recentCard,
    );
  } catch (error) {
    if (isAuthError(error)) return;
    content.replaceChildren(errorState(error, () => renderDashboard(view, { user, navigate })));
  }
}

/* ------------------------------ 个人信息 ------------------------------ */

export async function renderProfile(view, { onLoggedOut }) {
  const hero = el("div", { class: "page-hero" }, [
    el("div", {}, [
      el("h1", { class: "hero-title", text: "个人信息" }),
      el("p", { class: "hero-sub", text: "查看当前账号资料、角色权限与登录状态" }),
    ]),
  ]);
  const content = el("div");
  view.append(hero, content);
  content.append(el("div", { class: "loading-block" }, [el("span", { class: "spinner spinner-lg" }), el("p", { text: "正在加载账户信息…" })]));

  try {
    const me = await api.me();
    const statusPill = el("span", {
      class: `pill ${me.is_active ? "pill-ok" : "pill-muted"}`,
      text: me.is_active ? "启用中" : "已停用",
    });

    const permissionItems = {
      admin: [
        "管理用户：创建、停用、启用账号与调整角色",
        "管理资料：新增、修改、停用资料",
        "办理业务：借阅与归还",
      ],
      staff: ["查询资料与借阅记录", "办理资料借阅", "办理资料归还"],
      viewer: ["查询资料列表与详情", "查看借阅记录"],
    }[me.role] || [];

    const infoCard = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("div", { class: "card-title" }, [el("span", { html: icon("user") }), el("span", { text: "账户信息" })]),
      ]),
      el("div", { class: "card-body" }, [
        el("div", { class: "profile-head" }, [
          el("div", { class: "avatar", text: initials(me.username) }),
          el("div", {}, [
            el("div", { class: "profile-name", text: me.username }),
            el("div", { class: "profile-role", text: `${roleLabel(me.role)} · 用户 ID ${me.id}` }),
          ]),
        ]),
        detailList([
          ["用户名", me.username],
          ["角色", roleLabel(me.role)],
          ["账户状态", statusPill],
          ["用户 ID", String(me.id)],
        ]),
      ]),
    ]);

    const permissionCard = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("div", { class: "card-title" }, [el("span", { html: icon("shield") }), el("span", { text: "角色权限" })]),
      ]),
      el("div", { class: "card-body" }, [
        el("p", { class: "field-hint", style: { marginBottom: "12px" }, text: roleDescription(me.role) }),
        el("div", { class: "permission-list" }, permissionItems.map((text) =>
          el("div", { class: "permission-item" }, [
            el("span", { html: icon("check") }),
            el("span", { text }),
          ]),
        )),
        el("div", { class: "modal-note", style: { marginTop: "16px" } }, [
          el("span", { html: icon("info") }),
          el("span", { text: "登录令牌仅保存在当前标签页的会话存储中，关闭标签页后需要重新登录。系统不会在页面上展示密码或密码哈希。" }),
        ]),
      ]),
    ]);

    const actionCard = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("div", { class: "card-title" }, [el("span", { html: icon("logout") }), el("span", { text: "安全退出" })]),
      ]),
      el("div", { class: "card-body" }, [
        el("p", { class: "field-hint", style: { marginBottom: "14px" }, text: "退出后当前令牌立即失效，需要重新输入用户名和密码。" }),
        el("button", {
          class: "btn btn-danger",
          type: "button",
          html: icon("logout"),
          onclick: async () => {
            const confirmed = await confirmDialog({
              title: "退出登录",
              message: "确认退出当前账号？",
              confirmText: "退出登录",
              danger: true,
            });
            if (!confirmed) return;
            await logout();
            if (onLoggedOut) onLoggedOut();
          },
        }, [el("span", { text: "安全退出登录" })]),
      ]),
    ]);

    content.replaceChildren(el("div", { class: "profile-grid" }, [infoCard, el("div", {}, [permissionCard, actionCard])]));
  } catch (error) {
    if (isAuthError(error)) return;
    content.replaceChildren(errorState(error, () => renderProfile(view, { onLoggedOut })));
  }
}
