/**
 * 借阅办理、归还办理、借阅记录页面。
 */

import {
  el, icon, toast, confirmDialog, runBusy, formatDateTime, materialStatusPill,
  borrowStatusPill, pagination, emptyState, errorState, loadingRows, debounce,
  isAuthError, errorMessage, isOverdue, localDateKey,
} from "./ui.js?v=0.9.1";
import { api } from "./api.js?v=0.9.1";

function tag(text) {
  return el("span", { class: "tag", text });
}

/* ------------------------------ 借阅办理 ------------------------------ */

export async function renderBorrow(view) {
  const PAGE_SIZE = 9;
  const state = { items: [], keyword: "", page: 1, loading: true, error: null };

  const hero = el("div", { class: "page-hero" }, [
    el("div", {}, [
      el("h1", { class: "hero-title", text: "借阅办理" }),
      el("p", { class: "hero-sub", text: "浏览当前可借阅的影像资料，确认后即可办理借出" }),
    ]),
  ]);

  const listSlot = el("div");
  const pagerSlot = el("div");
  const countLabel = el("span", { class: "result-count" });

  const searchInput = el("input", {
    class: "input", type: "search", placeholder: "搜索资料名称、编号、类型或部位",
    "aria-label": "搜索可借阅资料",
  });
  searchInput.addEventListener("input", debounce(() => {
    state.keyword = searchInput.value;
    state.page = 1;
    paint();
  }, 250));

  const refreshButton = el("button", {
    class: "btn btn-ghost btn-sm", type: "button", html: icon("refresh"),
  }, [el("span", { text: "刷新" })]);
  refreshButton.addEventListener("click", () => runBusy(refreshButton, load, "刷新中…"));

  const toolbar = el("div", { class: "toolbar" }, [
    el("div", { class: "toolbar-left" }, [
      el("div", { class: "search-box" }, [el("span", { html: icon("search") }), searchInput]),
      countLabel,
    ]),
    el("div", { class: "toolbar-right" }, [refreshButton]),
  ]);

  const card = el("section", { class: "card" }, [toolbar, listSlot, pagerSlot]);
  view.append(hero, card);

  function filteredItems() {
    const keyword = state.keyword.trim().toLowerCase();
    if (!keyword) return state.items;
    return state.items.filter((item) =>
      [item.material_code, item.title, item.modality, item.body_part, item.material_type]
        .some((value) => String(value || "").toLowerCase().includes(keyword)),
    );
  }

  function paint() {
    if (state.loading) {
      listSlot.replaceChildren(loadingRows(4));
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

    countLabel.textContent = `可借阅 ${filtered.length} 份`;

    if (!filtered.length) {
      listSlot.replaceChildren(emptyState({
        iconName: state.items.length ? "search" : "inbox",
        title: state.items.length ? "没有匹配的可借阅资料" : "暂无可借阅的资料",
        text: state.items.length
          ? "换一个关键词试试，或到资料管理页面查看已借出、已停用的资料。"
          : "所有资料都已借出或停用，请稍后再来。",
      }));
      pagerSlot.replaceChildren();
      return;
    }

    const grid = el("div", { class: "borrow-grid" }, pageItems.map(buildCard));
    listSlot.replaceChildren(grid);
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

  function buildCard(item) {
    const borrowButton = el("button", {
      class: "btn btn-primary btn-sm", type: "button", html: icon("borrow"),
    }, [el("span", { text: "借阅" })]);
    borrowButton.addEventListener("click", () => borrowItem(item, borrowButton));

    return el("article", { class: "borrow-card" }, [
      el("div", { class: "borrow-card-top" }, [
        el("div", {}, [
          el("div", { class: "borrow-card-title", text: item.title }),
          el("div", { class: "borrow-card-code", text: item.material_code }),
        ]),
        materialStatusPill(item.status),
      ]),
      el("div", { class: "borrow-card-meta" }, [
        tag(item.modality), tag(item.body_part), tag(item.material_type),
      ]),
      el("div", { class: "location" }, [
        el("span", { html: icon("box") }),
        el("span", { text: item.storage_location }),
      ]),
      el("div", { class: "borrow-card-foot" }, [
        el("span", { class: "field-hint", text: `登记于 ${formatDateTime(item.created_at)}` }),
        borrowButton,
      ]),
    ]);
  }

  async function borrowItem(item, button) {
    await runBusy(button, async () => {
      const confirmed = await confirmDialog({
        title: "确认借阅",
        message: `确认为《${item.title}》（${item.material_code}）办理借阅？应还时间默认为 14 天后。`,
        confirmText: "确认借阅",
      });
      if (!confirmed) return;

      try {
        const record = await api.borrow(item.id);
        toast(`借阅成功，应还时间 ${formatDateTime(record.due_at)}`, "success");
        await load();
      } catch (error) {
        if (isAuthError(error)) return;
        if (error.status === 409) {
          toast("该资料刚刚被他人借出，列表已刷新", "warn");
          await load();
        } else {
          toast(errorMessage(error), "error");
        }
      }
    }, "办理中…");
  }

  async function load() {
    state.loading = true;
    state.error = null;
    paint();
    try {
      state.items = await api.availableMaterials();
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

/* ------------------------------ 归还办理 ------------------------------ */

export async function renderReturn(view) {
  const PAGE_SIZE = 10;
  const state = { items: [], keyword: "", page: 1, loading: true, error: null };

  const hero = el("div", { class: "page-hero" }, [
    el("div", {}, [
      el("h1", { class: "hero-title", text: "归还办理" }),
      el("p", { class: "hero-sub", text: "查看当前未归还的借阅记录，确认后办理归还" }),
    ]),
  ]);

  const listSlot = el("div");
  const pagerSlot = el("div");
  const countLabel = el("span", { class: "result-count" });

  const searchInput = el("input", {
    class: "input", type: "search", placeholder: "搜索资料名称、编号或借阅人",
    "aria-label": "搜索未归还记录",
  });
  searchInput.addEventListener("input", debounce(() => {
    state.keyword = searchInput.value;
    state.page = 1;
    paint();
  }, 250));

  const refreshButton = el("button", {
    class: "btn btn-ghost btn-sm", type: "button", html: icon("refresh"),
  }, [el("span", { text: "刷新" })]);
  refreshButton.addEventListener("click", () => runBusy(refreshButton, load, "刷新中…"));

  const toolbar = el("div", { class: "toolbar" }, [
    el("div", { class: "toolbar-left" }, [
      el("div", { class: "search-box" }, [el("span", { html: icon("search") }), searchInput]),
      countLabel,
    ]),
    el("div", { class: "toolbar-right" }, [refreshButton]),
  ]);

  const card = el("section", { class: "card" }, [toolbar, listSlot, pagerSlot]);
  view.append(hero, card);

  function filteredItems() {
    const keyword = state.keyword.trim().toLowerCase();
    if (!keyword) return state.items;
    return state.items.filter((record) =>
      [record.material_code, record.title, record.borrower_username]
        .some((value) => String(value || "").toLowerCase().includes(keyword)),
    );
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

    countLabel.textContent = `未归还 ${filtered.length} 条`;

    if (!filtered.length) {
      listSlot.replaceChildren(emptyState({
        iconName: state.items.length ? "search" : "inbox",
        title: state.items.length ? "没有匹配的记录" : "当前没有未归还的借阅",
        text: state.items.length ? "试试调整搜索关键词。" : "所有借出的资料都已归还。",
      }));
      pagerSlot.replaceChildren();
      return;
    }

    const tbody = el("tbody");
    for (const record of pageItems) tbody.append(buildRow(record));

    listSlot.replaceChildren(el("div", { class: "table-wrap" }, [
      el("table", { class: "table" }, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "资料" }),
          el("th", { text: "借阅人" }),
          el("th", { text: "借出时间" }),
          el("th", { text: "应还时间" }),
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

  function buildRow(record) {
    const returnButton = el("button", {
      class: "btn btn-primary btn-sm", type: "button", html: icon("return"),
    }, [el("span", { text: "归还" })]);
    returnButton.addEventListener("click", () => returnItem(record, returnButton));

    return el("tr", {}, [
      el("td", {}, [
        el("div", { class: "cell-main", text: record.title }),
        el("div", { class: "cell-sub cell-mono", text: record.material_code }),
      ]),
      el("td", { text: record.borrower_username }),
      el("td", { text: formatDateTime(record.borrowed_at) }),
      el("td", {}, [
        el("div", { text: formatDateTime(record.due_at) }),
        isOverdue(record) ? el("span", { class: "pill pill-danger", text: "已逾期" }) : null,
      ]),
      el("td", {}, [borrowStatusPill(record)]),
      el("td", {}, [returnButton]),
    ]);
  }

  async function returnItem(record, button) {
    await runBusy(button, async () => {
      const confirmed = await confirmDialog({
        title: "确认归还",
        message: `确认归还《${record.title}》（${record.material_code}）？归还后资料将恢复为可借阅状态。`,
        confirmText: "确认归还",
      });
      if (!confirmed) return;

      try {
        await api.giveBack(record.material_id);
        toast("归还成功，资料已恢复为可借阅", "success");
        await load();
      } catch (error) {
        if (isAuthError(error)) return;
        if (error.status === 409) {
          toast("该记录状态已变化，列表已刷新", "warn");
          await load();
        } else {
          toast(errorMessage(error), "error");
        }
      }
    }, "处理中…");
  }

  async function load() {
    state.loading = true;
    state.error = null;
    paint();
    try {
      state.items = await api.activeBorrows();
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

/* ------------------------------ 借阅记录 ------------------------------ */

export async function renderRecords(view) {
  const PAGE_SIZE = 12;
  const state = {
    items: [], keyword: "", status: "all", dateFrom: "", dateTo: "",
    page: 1, loading: true, error: null,
  };

  const hero = el("div", { class: "page-hero" }, [
    el("div", {}, [
      el("h1", { class: "hero-title", text: "借阅记录" }),
      el("p", { class: "hero-sub", text: "查看全部借阅历史，包括尚未归还与已归还记录" }),
    ]),
  ]);

  const listSlot = el("div");
  const pagerSlot = el("div");
  const countLabel = el("span", { class: "result-count" });

  const searchInput = el("input", {
    class: "input", type: "search", placeholder: "搜索资料名称、编号或借阅人",
    "aria-label": "搜索借阅记录",
  });
  searchInput.addEventListener("input", debounce(() => {
    state.keyword = searchInput.value;
    state.page = 1;
    paint();
  }, 250));

  const statusSelect = el("select", { class: "select", "aria-label": "按状态筛选" }, [
    el("option", { value: "all", text: "全部状态" }),
    el("option", { value: "active", text: "借阅中" }),
    el("option", { value: "overdue", text: "已逾期" }),
    el("option", { value: "returned", text: "已归还" }),
  ]);
  statusSelect.addEventListener("change", () => {
    state.status = statusSelect.value;
    state.page = 1;
    paint();
  });

  const dateFromInput = el("input", {
    class: "input", type: "date", "aria-label": "借出开始日期",
  });
  dateFromInput.addEventListener("change", () => {
    state.dateFrom = dateFromInput.value;
    state.page = 1;
    paint();
  });
  const dateToInput = el("input", {
    class: "input", type: "date", "aria-label": "借出结束日期",
  });
  dateToInput.addEventListener("change", () => {
    state.dateTo = dateToInput.value;
    state.page = 1;
    paint();
  });

  const refreshButton = el("button", {
    class: "btn btn-ghost btn-sm", type: "button", html: icon("refresh"),
  }, [el("span", { text: "刷新" })]);
  refreshButton.addEventListener("click", () => runBusy(refreshButton, load, "刷新中…"));

  const toolbar = el("div", { class: "toolbar" }, [
    el("div", { class: "toolbar-left" }, [
      el("div", { class: "search-box" }, [el("span", { html: icon("search") }), searchInput]),
      el("div", { class: "select-wrap" }, [statusSelect]),
      dateFromInput, dateToInput,
      countLabel,
    ]),
    el("div", { class: "toolbar-right" }, [refreshButton]),
  ]);

  const card = el("section", { class: "card" }, [toolbar, listSlot, pagerSlot]);
  view.append(hero, card);

  function statusOf(record) {
    if (record.returned_at) return "returned";
    return isOverdue(record) ? "overdue" : "active";
  }

  function filteredItems() {
    const keyword = state.keyword.trim().toLowerCase();
    return state.items.filter((record) => {
      if (state.status !== "all" && statusOf(record) !== state.status) return false;
      const borrowedDay = localDateKey(record.borrowed_at);
      if (state.dateFrom && borrowedDay < state.dateFrom) return false;
      if (state.dateTo && borrowedDay > state.dateTo) return false;
      if (!keyword) return true;
      return [record.material_code, record.title, record.borrower_username]
        .some((value) => String(value || "").toLowerCase().includes(keyword));
    });
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

    countLabel.textContent = `共 ${filtered.length} 条记录`;

    if (!filtered.length) {
      listSlot.replaceChildren(emptyState({
        iconName: state.items.length ? "search" : "inbox",
        title: state.items.length ? "没有匹配的记录" : "还没有借阅记录",
        text: state.items.length ? "试试调整关键词、状态或借出日期。" : "办理借阅后，记录会显示在这里。",
      }));
      pagerSlot.replaceChildren();
      return;
    }

    const tbody = el("tbody");
    for (const record of pageItems) {
      tbody.append(el("tr", {}, [
        el("td", {}, [
          el("div", { class: "cell-main", text: record.title }),
          el("div", { class: "cell-sub cell-mono", text: record.material_code }),
        ]),
        el("td", { text: record.borrower_username }),
        el("td", { text: formatDateTime(record.borrowed_at) }),
        el("td", { text: formatDateTime(record.due_at) }),
        el("td", { text: formatDateTime(record.returned_at) }),
        el("td", {}, [borrowStatusPill(record)]),
      ]));
    }

    listSlot.replaceChildren(el("div", { class: "table-wrap" }, [
      el("table", { class: "table" }, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "资料" }),
          el("th", { text: "借阅人" }),
          el("th", { text: "借出时间" }),
          el("th", { text: "应还时间" }),
          el("th", { text: "归还时间" }),
          el("th", { text: "状态" }),
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

  async function load() {
    state.loading = true;
    state.error = null;
    paint();
    try {
      state.items = await api.history();
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
