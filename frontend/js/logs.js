/**
 * 操作日志页面（仅管理员）：筛选、分页、CSV 导出与归档清理。
 */

import { api } from "./api.js?v=0.9.1";
import {
  el, icon, toast, runBusy, pagination, emptyState, errorState, loadingRows,
  formatDateTime, roleLabel, isAuthError, errorMessage, downloadBlob, openModal,
  localDateToUtcStart, localDateToUtcEnd,
} from "./ui.js?v=0.9.1";

const PAGE_SIZE = 15;

function exportFilename() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `操作日志_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_`
    + `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.csv`;
}

function defaultArchiveDate() {
  const date = new Date();
  date.setDate(date.getDate() - 90);
  return date.toISOString().slice(0, 10);
}

export async function renderLogs(view) {
  const state = {
    items: [], total: 0, page: 1, loading: true, error: null,
    username: "", action: "", start: "", end: "",
  };

  const hero = el("div", { class: "page-hero" }, [
    el("div", {}, [
      el("h1", { class: "hero-title", text: "操作日志" }),
      el("p", { class: "hero-sub", text: "查看登录、资料维护、借阅归还和用户管理留下的操作记录" }),
    ]),
  ]);

  const listSlot = el("div");
  const pagerSlot = el("div");
  const countLabel = el("span", { class: "result-count" });

  const usernameInput = el("input", {
    class: "input", type: "search", placeholder: "操作人",
    "aria-label": "按操作人筛选",
  });
  const actionInput = el("input", {
    class: "input", type: "search", placeholder: "动作，如 新增资料",
    "aria-label": "按动作筛选",
  });
  const startInput = el("input", {
    class: "input", type: "date", "aria-label": "开始日期",
  });
  const endInput = el("input", {
    class: "input", type: "date", "aria-label": "结束日期",
  });

  const filterButton = el("button", {
    class: "btn btn-primary btn-sm", type: "button",
  }, [el("span", { text: "查询" })]);
  filterButton.addEventListener("click", () => {
    state.username = usernameInput.value.trim();
    state.action = actionInput.value.trim();
    state.start = startInput.value;
    state.end = endInput.value;
    state.page = 1;
    load();
  });

  const resetButton = el("button", {
    class: "btn btn-ghost btn-sm", type: "button",
  }, [el("span", { text: "重置" })]);
  resetButton.addEventListener("click", () => {
    usernameInput.value = "";
    actionInput.value = "";
    startInput.value = "";
    endInput.value = "";
    state.username = "";
    state.action = "";
    state.start = "";
    state.end = "";
    state.page = 1;
    load();
  });

  const refreshButton = el("button", {
    class: "btn btn-ghost btn-sm", type: "button", html: icon("refresh"),
  }, [el("span", { text: "刷新" })]);
  refreshButton.addEventListener("click", () => runBusy(refreshButton, load, "刷新中…"));

  const exportButton = el("button", {
    class: "btn btn-primary btn-sm", type: "button", html: icon("records"),
  }, [el("span", { text: "导出 CSV" })]);

  const archiveButton = el("button", {
    class: "btn btn-danger btn-sm", type: "button", html: icon("box"),
  }, [el("span", { text: "归档旧日志" })]);

  const toolbar = el("div", { class: "toolbar" }, [
    el("div", { class: "toolbar-left" }, [
      usernameInput, actionInput, startInput, endInput,
      filterButton, resetButton, countLabel,
    ]),
    el("div", { class: "toolbar-right" }, [refreshButton, exportButton, archiveButton]),
  ]);

  const card = el("section", { class: "card" }, [toolbar, listSlot, pagerSlot]);
  view.append(hero, card);

  function filterQuery() {
    return {
      username: state.username,
      action: state.action,
      start: state.start ? localDateToUtcStart(state.start) : "",
      end: state.end ? localDateToUtcEnd(state.end) : "",
    };
  }

  function paint() {
    if (state.loading) {
      listSlot.replaceChildren(loadingRows(6));
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

    const totalPages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
    state.page = Math.min(Math.max(1, state.page), totalPages);
    countLabel.textContent = `共 ${state.total} 条操作记录`;

    if (!state.items.length) {
      listSlot.replaceChildren(emptyState({
        iconName: "records",
        title: "没有匹配的操作日志",
        text: "试试调整操作人、动作或时间范围，或者重置筛选条件。",
      }));
      pagerSlot.replaceChildren();
      return;
    }

    const tbody = el("tbody", {}, state.items.map((log) => el("tr", {}, [
      el("td", {}, [
        el("div", { class: "cell-main", text: formatDateTime(log.created_at) }),
        el("div", { class: "cell-sub cell-mono", text: log.created_at }),
      ]),
      el("td", {}, [
        el("div", { class: "cell-main", text: log.username || "—" }),
        el("div", { class: "cell-sub", text: roleLabel(log.role) }),
      ]),
      el("td", { text: log.ip || "—" }),
      el("td", { text: log.action }),
      el("td", {}, [
        el("div", { class: "cell-main", text: log.target_type || "—" }),
        el("div", { class: "cell-sub", text: log.target_id ? `#${log.target_id}` : "" }),
      ]),
      el("td", { text: log.detail || "—" }),
    ])));

    listSlot.replaceChildren(el("div", { class: "table-wrap" }, [
      el("table", { class: "table" }, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "时间" }),
          el("th", { text: "操作人" }),
          el("th", { text: "客户端IP" }),
          el("th", { text: "动作" }),
          el("th", { text: "对象" }),
          el("th", { text: "详情" }),
        ])]),
        tbody,
      ]),
    ]));

    pagerSlot.replaceChildren(pagination({
      page: state.page,
      totalPages,
      total: state.total,
      onChange: (page) => {
        state.page = page;
        load();
      },
    }));
  }

  async function load() {
    state.loading = true;
    state.error = null;
    paint();
    try {
      const offset = (state.page - 1) * PAGE_SIZE;
      const data = await api.logs({ ...filterQuery(), limit: PAGE_SIZE, offset });
      state.items = data.items;
      state.total = data.total;
    } catch (error) {
      state.error = error;
    } finally {
      state.loading = false;
      paint();
    }
  }

  exportButton.addEventListener("click", () => runBusy(exportButton, async () => {
    try {
      const blob = await api.exportLogs(filterQuery());
      downloadBlob(blob, exportFilename());
      toast("操作日志已导出为 CSV", "success");
    } catch (error) {
      if (isAuthError(error)) return;
      toast(errorMessage(error), "error");
    }
  }, "导出中…"));

  archiveButton.addEventListener("click", () => {
    const dateInput = el("input", {
      class: "input", type: "date", value: defaultArchiveDate(),
      "aria-label": "归档截止日期",
    });
    const cancelButton = el("button", {
      class: "btn btn-ghost", type: "button",
    }, [el("span", { text: "取消" })]);
    const submitButton = el("button", {
      class: "btn btn-danger", type: "button", html: icon("box"),
    }, [el("span", { text: "导出并归档" })]);

    const body = el("div", {}, [
      el("div", { class: "modal-note", style: { marginTop: "0" } }, [
        el("span", { html: icon("alert") }),
        el("span", { text: "归档会先把截止日期之前的日志导出到服务器 backups 目录，然后从数据库删除。删除后不可恢复，请确认日期。" }),
      ]),
      el("div", { class: "field", style: { marginTop: "14px" } }, [
        el("label", { class: "field-label", text: "归档截止日期（UTC）" }),
        dateInput,
      ]),
    ]);

    const modal = openModal({
      title: "归档旧日志",
      body,
      footer: [cancelButton, submitButton],
    });
    cancelButton.addEventListener("click", () => modal.close());

    submitButton.addEventListener("click", () => runBusy(submitButton, async () => {
      if (!dateInput.value) {
        toast("请选择归档截止日期", "warn");
        return;
      }
      try {
        const result = await api.archiveLogs(dateInput.value);
        if (!result.archived_count) {
          toast("截止日期之前没有可归档的日志", "warn");
          return;
        }
        toast(`已归档 ${result.archived_count} 条，文件：${result.file}`, "success");
        modal.close();
        state.page = 1;
        await load();
      } catch (error) {
        if (isAuthError(error)) return;
        toast(errorMessage(error), "error");
      }
    }, "归档中…"));
  });

  paint();
  await load();
}
