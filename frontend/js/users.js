/**
 * 用户管理页面（仅管理员）：列表、搜索、新增、停用/启用、调整角色。
 */

import { api } from "./api.js?v=0.9.1";
import { getUser } from "./auth.js?v=0.9.1";
import {
  el, icon, toast, confirmDialog, openModal, runBusy, pagination, emptyState, errorState,
  loadingRows, debounce, isAuthError, errorMessage, formErrorBox, showFormError,
  hideFormError, roleLabel,
} from "./ui.js?v=0.9.1";

const PAGE_SIZE = 10;
const ROLES = [
  { value: "admin", label: "管理员" },
  { value: "staff", label: "工作人员" },
  { value: "viewer", label: "访客" },
];

function describeError(error) {
  if (error && Array.isArray(error.details) && error.details.length) {
    const first = error.details[0];
    if (first && first.msg) return `${error.message}：${first.msg}`;
  }
  return errorMessage(error);
}

export async function renderUsers(view) {
  const me = getUser();
  const state = { items: [], keyword: "", role: "all", page: 1, loading: true, error: null };

  const hero = el("div", { class: "page-hero" }, [
    el("div", {}, [
      el("h1", { class: "hero-title", text: "用户管理" }),
      el("p", { class: "hero-sub", text: "管理系统账号、角色与启用状态，停用和角色调整会立即生效" }),
    ]),
  ]);

  const notice = el("div", { class: "modal-note", style: { marginBottom: "18px", marginTop: "0" } }, [
    el("span", { html: icon("shield") }),
    el("span", { text: "账号被停用后，其已登录的令牌会立即失效；调整角色后，该用户下一次请求即按新角色授权。管理员不能停用或修改自己的账号。" }),
  ]);

  const listSlot = el("div");
  const pagerSlot = el("div");
  const countLabel = el("span", { class: "result-count" });

  const searchInput = el("input", {
    class: "input", type: "search", placeholder: "搜索用户名", "aria-label": "搜索用户名",
  });
  searchInput.addEventListener("input", debounce(() => {
    state.keyword = searchInput.value;
    state.page = 1;
    paint();
  }, 250));

  const roleFilter = el("select", { class: "select", "aria-label": "按角色筛选" }, [
    el("option", { value: "all", text: "全部角色" }),
    ...ROLES.map((role) => el("option", { value: role.value, text: role.label })),
  ]);
  roleFilter.addEventListener("change", () => {
    state.role = roleFilter.value;
    state.page = 1;
    paint();
  });

  const refreshButton = el("button", {
    class: "btn btn-ghost btn-sm", type: "button", html: icon("refresh"),
  }, [el("span", { text: "刷新" })]);
  refreshButton.addEventListener("click", () => runBusy(refreshButton, load, "刷新中…"));

  const addButton = el("button", { class: "btn btn-primary btn-sm", type: "button" }, [
    el("span", { html: icon("plus") }),
    el("span", { text: "新增用户" }),
  ]);
  addButton.addEventListener("click", openCreateForm);

  const toolbar = el("div", { class: "toolbar" }, [
    el("div", { class: "toolbar-left" }, [
      el("div", { class: "search-box" }, [el("span", { html: icon("search") }), searchInput]),
      el("div", { class: "select-wrap" }, [roleFilter]),
      countLabel,
    ]),
    el("div", { class: "toolbar-right" }, [refreshButton, addButton]),
  ]);

  const card = el("section", { class: "card" }, [toolbar, listSlot, pagerSlot]);
  view.append(hero, notice, card);

  function filteredItems() {
    const keyword = state.keyword.trim().toLowerCase();
    return state.items.filter((user) => {
      if (state.role !== "all" && user.role !== state.role) return false;
      if (!keyword) return true;
      return String(user.username).toLowerCase().includes(keyword);
    });
  }

  function statusPill(user) {
    return user.is_active
      ? el("span", { class: "pill pill-ok", text: "启用中" })
      : el("span", { class: "pill pill-muted", text: "已停用" });
  }

  function paint() {
    if (state.loading) {
      listSlot.replaceChildren(loadingRows(5));
      pagerSlot.replaceChildren();
      countLabel.textContent = "加载中…";
      return;
    }
    if (state.error) {
      listSlot.replaceChildren(errorState(state.error, load));
      pagerSlot.replaceChildren();
      countLabel.textContent = "";
      return;
    }

    const filtered = filteredItems();
    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    state.page = Math.min(Math.max(1, state.page), totalPages);
    const start = (state.page - 1) * PAGE_SIZE;
    const pageItems = filtered.slice(start, start + PAGE_SIZE);

    countLabel.textContent = `共 ${filtered.length} 个账号`;

    if (!filtered.length) {
      listSlot.replaceChildren(emptyState({
        iconName: state.items.length ? "search" : "users",
        title: state.items.length ? "没有匹配的账号" : "暂无账号",
        text: state.items.length ? "试试调整关键词或角色筛选。" : "点击右上角新增第一个账号。",
      }));
      pagerSlot.replaceChildren();
      return;
    }

    const tbody = el("tbody");
    for (const user of pageItems) tbody.append(buildRow(user));

    listSlot.replaceChildren(el("div", { class: "table-wrap" }, [
      el("table", { class: "table" }, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "用户名" }),
          el("th", { text: "角色" }),
          el("th", { text: "状态" }),
          el("th", { text: "操作" }),
        ])]),
        tbody,
      ]),
    ]));

    pagerSlot.replaceChildren(pagination({
      page: state.page,
      totalPages,
      total: filtered.length,
      onChange: (page) => {
        state.page = page;
        paint();
      },
    }));
  }

  function buildRow(user) {
    const isSelf = user.id === me.id;

    const roleCell = isSelf
      ? el("span", { class: "tag", text: `${roleLabel(user.role)}（当前账号）` })
      : el("select", {
          class: "select",
          style: { height: "32px", width: "132px" },
          "aria-label": `修改 ${user.username} 的角色`,
        }, ROLES.map((role) =>
          el("option", { value: role.value, text: role.label, selected: role.value === user.role }),
        ));

    if (!isSelf) {
      roleCell.addEventListener("change", async () => {
        const newRole = roleCell.value;
        if (newRole === user.role) return;
        roleCell.disabled = true;
        const confirmed = await confirmDialog({
          title: "调整角色",
          message: `确认把「${user.username}」的角色改为「${roleLabel(newRole)}」？该用户下一次请求就会按新角色授权。`,
          confirmText: "确认调整",
        });
        if (!confirmed) {
          roleCell.value = user.role;
          roleCell.disabled = false;
          return;
        }
        try {
          await api.changeRole(user.id, newRole);
          toast("角色已调整", "success");
          await load();
        } catch (error) {
          roleCell.value = user.role;
          if (!isAuthError(error)) toast(errorMessage(error), "error");
        } finally {
          roleCell.disabled = false;
        }
      });
    }

    const actions = el("div", { class: "row-actions" });
    if (isSelf) {
      actions.append(el("span", { class: "field-hint", text: "不可操作自己" }));
    } else if (user.is_active) {
      const disableButton = el("button", {
        class: "btn btn-danger btn-sm", type: "button", html: icon("ban"),
      }, [el("span", { text: "停用" })]);
      disableButton.addEventListener("click", async () => {
        await runBusy(disableButton, async () => {
          const confirmed = await confirmDialog({
            title: "停用账号",
            message: `确认停用「${user.username}」？停用后该账号无法登录，已登录的令牌也会立即失效。`,
            confirmText: "确认停用",
            danger: true,
          });
          if (!confirmed) return;

          try {
            await api.disableUser(user.id);
            toast("账号已停用", "success");
            await load();
          } catch (error) {
            if (!isAuthError(error)) toast(errorMessage(error), "error");
          }
        }, "处理中…");
      });
      actions.append(disableButton);
    } else {
      const enableButton = el("button", {
        class: "btn btn-secondary btn-sm", type: "button", html: icon("check"),
      }, [el("span", { text: "启用" })]);
      enableButton.addEventListener("click", async () => {
        await runBusy(enableButton, async () => {
          const confirmed = await confirmDialog({
            title: "启用账号",
            message: `确认启用「${user.username}」？启用后该账号可以重新登录。`,
            confirmText: "确认启用",
          });
          if (!confirmed) return;

          try {
            await api.enableUser(user.id);
            toast("账号已启用", "success");
            await load();
          } catch (error) {
            if (!isAuthError(error)) toast(errorMessage(error), "error");
          }
        }, "处理中…");
      });
      actions.append(enableButton);
    }

    return el("tr", {}, [
      el("td", {}, [
        el("div", { class: "cell-main", text: user.username }),
        el("div", { class: "cell-sub", text: `用户 ID ${user.id}` }),
      ]),
      el("td", {}, [roleCell]),
      el("td", {}, [statusPill(user)]),
      el("td", {}, [actions]),
    ]);
  }

  function openCreateForm() {
    const usernameInput = el("input", {
      class: "input", type: "text", maxlength: 50, autocomplete: "off",
      "aria-label": "用户名",
    });
    const passwordInput = el("input", {
      class: "input", type: "password", autocomplete: "new-password",
      "aria-label": "初始密码",
    });
    const roleSelect = el("select", { class: "select", "aria-label": "角色" },
      ROLES.map((role) =>
        el("option", { value: role.value, text: role.label, selected: role.value === "viewer" }),
      ),
    );

    const errorBox = formErrorBox();
    const form = el("form", { novalidate: true }, [
      el("div", { class: "form-grid" }, [
        el("div", { class: "field" }, [
          el("label", { class: "field-label" }, ["用户名", el("span", { class: "required", text: "*" })]),
          usernameInput,
          el("span", { class: "field-hint", text: "大小写不敏感，不能与已有用户名重复" }),
        ]),
        el("div", { class: "field" }, [
          el("label", { class: "field-label" }, ["初始密码", el("span", { class: "required", text: "*" })]),
          passwordInput,
          el("span", { class: "field-hint", text: "至少 6 位" }),
        ]),
        el("div", { class: "field full" }, [
          el("label", { class: "field-label" }, ["角色"]),
          roleSelect,
        ]),
      ]),
      errorBox,
    ]);

    let modal = null;
    const cancelButton = el("button", {
      class: "btn btn-secondary", type: "button", text: "取消",
      onclick: () => modal && modal.close(),
    });
    const submitButton = el("button", { class: "btn btn-primary", type: "button", text: "创建用户" });

    let creating = false;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (creating) return;
      hideFormError(errorBox);
      const username = usernameInput.value.trim();
      const password = passwordInput.value;
      if (!username) {
        showFormError(errorBox, "请输入用户名");
        usernameInput.focus();
        return;
      }
      if (password.length < 6) {
        showFormError(errorBox, "密码至少需要 6 个字符");
        passwordInput.focus();
        return;
      }

      creating = true;
      try {
        await runBusy(submitButton, async () => {
          try {
            await api.createUser({ username, password, role: roleSelect.value });
            toast("用户创建成功", "success");
            if (modal) modal.close();
            await load();
          } catch (error) {
            if (isAuthError(error)) return;
            showFormError(errorBox, describeError(error));
          }
        }, "创建中…");
      } finally {
        creating = false;
      }
    });

    modal = openModal({
      title: "新增用户",
      body: form,
      footer: [cancelButton, submitButton],
    });
    submitButton.addEventListener("click", () => form.requestSubmit());
    usernameInput.focus();
  }

  async function load() {
    state.loading = true;
    state.error = null;
    paint();
    try {
      state.items = await api.users();
    } catch (error) {
      state.error = error;
    } finally {
      state.loading = false;
      paint();
    }
  }

  paint();
  await load();
}
