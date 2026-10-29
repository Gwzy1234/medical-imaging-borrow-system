/**
 * 资料管理页面：列表、搜索、筛选、分页、详情、新增、编辑、停用、借阅。
 */

import { api } from "./api.js?v=0.9.1";
import { getUser } from "./auth.js?v=0.9.1";
import {
  el, icon, toast, confirmDialog, openModal, detailList, runBusy, formatDateTime,
  materialStatusPill, pagination, emptyState, errorState, loadingRows, debounce,
  isAuthError, errorMessage, formErrorBox, showFormError, hideFormError, downloadBlob,
  localDateKey,
} from "./ui.js?v=0.9.1";

const PAGE_SIZE = 10;

const FIELD_LABELS = {
  material_code: "资料编号",
  title: "资料名称",
  modality: "影像检查类型",
  body_part: "检查部位",
  material_type: "资料载体",
  storage_location: "存放位置",
};

function describeError(error) {
  if (error && Array.isArray(error.details) && error.details.length) {
    const first = error.details[0];
    if (first && first.msg) return `${error.message}：${first.msg}`;
  }
  return errorMessage(error);
}

export async function renderMaterials(view, ctx) {
  const user = getUser();
  const canManage = user.role === "admin";
  const canBorrow = user.role !== "viewer";

  const state = {
    items: [], keyword: "", status: "all", modality: "all", sort: "default",
    dateFrom: "", dateTo: "", page: 1, loading: true, error: null,
  };

  const hero = el("div", { class: "page-hero" }, [
    el("div", {}, [
      el("h1", { class: "hero-title", text: "医学影像资料" }),
      el("p", { class: "hero-sub", text: "查询资料档案、借阅状态与存放位置，管理员可维护资料信息" }),
    ]),
  ]);

  const listSlot = el("div");
  const pagerSlot = el("div");
  const countLabel = el("span", { class: "result-count", text: "" });

  const searchInput = el("input", {
    class: "input",
    type: "search",
    placeholder: "搜索资料名称、编号、检查类型或存放位置",
    "aria-label": "搜索资料",
  });
  searchInput.addEventListener("input", debounce(() => {
    state.keyword = searchInput.value;
    state.page = 1;
    paint();
  }, 250));

  const statusSelect = el("select", { class: "select", "aria-label": "按状态筛选" }, [
    el("option", { value: "all", text: "全部状态" }),
    el("option", { value: "available", text: "可借阅" }),
    el("option", { value: "borrowed", text: "已借出" }),
    el("option", { value: "disabled", text: "已停用" }),
  ]);
  statusSelect.addEventListener("change", () => {
    state.status = statusSelect.value;
    state.page = 1;
    paint();
  });

  const modalitySelect = el("select", {
    class: "select", "aria-label": "按检查类型筛选",
  }, [el("option", { value: "all", text: "全部类型" })]);
  modalitySelect.addEventListener("change", () => {
    state.modality = modalitySelect.value;
    state.page = 1;
    paint();
  });

  const sortSelect = el("select", { class: "select", "aria-label": "排序方式" }, [
    el("option", { value: "default", text: "默认排序" }),
    el("option", { value: "title", text: "按名称" }),
    el("option", { value: "code", text: "按编号" }),
    el("option", { value: "status", text: "按状态" }),
  ]);
  sortSelect.addEventListener("change", () => {
    state.sort = sortSelect.value;
    state.page = 1;
    paint();
  });

  const dateFromInput = el("input", {
    class: "input", type: "date", "aria-label": "入库开始日期",
  });
  dateFromInput.addEventListener("change", () => {
    state.dateFrom = dateFromInput.value;
    state.page = 1;
    paint();
  });
  const dateToInput = el("input", {
    class: "input", type: "date", "aria-label": "入库结束日期",
  });
  dateToInput.addEventListener("change", () => {
    state.dateTo = dateToInput.value;
    state.page = 1;
    paint();
  });

  const refreshButton = el("button", {
    class: "btn btn-ghost btn-sm",
    type: "button",
    html: icon("refresh"),
  }, [el("span", { text: "刷新" })]);
  refreshButton.addEventListener("click", () => runBusy(refreshButton, load, "刷新中…"));

  const addButton = canManage
    ? el("button", { class: "btn btn-primary btn-sm", type: "button" }, [
        el("span", { html: icon("plus") }),
        el("span", { text: "新增资料" }),
      ])
    : null;
  if (addButton) addButton.addEventListener("click", () => openMaterialForm(null));

  const importButton = canManage
    ? el("button", { class: "btn btn-secondary btn-sm", type: "button" }, [
        el("span", { html: icon("records") }),
        el("span", { text: "批量导入" }),
      ])
    : null;
  if (importButton) importButton.addEventListener("click", openImportForm);

  const toolbar = el("div", { class: "toolbar" }, [
    el("div", { class: "toolbar-left" }, [
      el("div", { class: "search-box" }, [el("span", { html: icon("search") }), searchInput]),
      el("div", { class: "select-wrap" }, [statusSelect]),
      el("div", { class: "select-wrap" }, [modalitySelect]),
      el("div", { class: "select-wrap" }, [sortSelect]),
      dateFromInput, dateToInput,
      countLabel,
    ]),
    el("div", { class: "toolbar-right" }, [refreshButton, importButton, addButton].filter(Boolean)),
  ]);

  const card = el("section", { class: "card" }, [toolbar, listSlot, pagerSlot]);
  view.append(hero, card);

  function refreshModalityOptions() {
    const values = [...new Set(state.items.map((item) => item.modality).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "zh-CN"));
    if (!values.includes(state.modality)) state.modality = "all";
    modalitySelect.replaceChildren(
      el("option", { value: "all", text: "全部类型" }),
      ...values.map((value) => el("option", { value, text: value })),
    );
    modalitySelect.value = state.modality;
  }

  function filteredItems() {
    const keyword = state.keyword.trim().toLowerCase();
    const filtered = state.items.filter((item) => {
      if (state.status !== "all" && item.status !== state.status) return false;
      if (state.modality !== "all" && item.modality !== state.modality) return false;
      const createdDay = localDateKey(item.created_at);
      if (state.dateFrom && createdDay < state.dateFrom) return false;
      if (state.dateTo && createdDay > state.dateTo) return false;
      if (!keyword) return true;
      return [
        item.material_code, item.title, item.modality, item.body_part,
        item.material_type, item.storage_location,
      ].some((value) => String(value || "").toLowerCase().includes(keyword));
    });

    if (state.sort === "title") {
      filtered.sort((a, b) => String(a.title).localeCompare(String(b.title), "zh-CN"));
    } else if (state.sort === "code") {
      filtered.sort((a, b) => String(a.material_code).localeCompare(String(b.material_code)));
    } else if (state.sort === "status") {
      filtered.sort((a, b) => String(a.status).localeCompare(String(b.status)));
    }
    return filtered;
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

    const filtered = filteredItems();
    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    state.page = Math.min(Math.max(1, state.page), totalPages);
    const start = (state.page - 1) * PAGE_SIZE;
    const pageItems = filtered.slice(start, start + PAGE_SIZE);

    countLabel.textContent = `共 ${filtered.length} 条资料`;

    if (!filtered.length) {
      const emptyText = state.items.length
        ? "没有找到匹配的资料，试试调整关键词、状态、检查类型或入库日期。"
        : "系统中还没有资料，管理员可以新增第一份资料。";
      listSlot.replaceChildren(emptyState({
        iconName: state.items.length ? "search" : "inbox",
        title: state.items.length ? "没有匹配的资料" : "暂无资料",
        text: emptyText,
        action: canManage && !state.items.length
          ? { label: "新增资料", onClick: () => openMaterialForm(null) }
          : null,
      }));
      pagerSlot.replaceChildren();
      return;
    }

    const tbody = el("tbody");
    for (const item of pageItems) tbody.append(buildRow(item));

    listSlot.replaceChildren(el("div", { class: "table-wrap" }, [
      el("table", { class: "table" }, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "资料" }),
          el("th", { text: "检查类型 / 部位" }),
          el("th", { text: "载体" }),
          el("th", { text: "存放位置" }),
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
        card.scrollIntoView({ behavior: "smooth", block: "start" });
      },
    }));
  }

  function buildRow(item) {
    const actions = el("div", { class: "row-actions" });

    const detailButton = el("button", {
      class: "btn btn-ghost btn-sm", type: "button", html: icon("info"),
    }, [el("span", { text: "详情" })]);
    detailButton.addEventListener("click", () => showDetail(item));
    actions.append(detailButton);

    if (canBorrow && item.status === "available") {
      const borrowButton = el("button", {
        class: "btn btn-primary btn-sm", type: "button", html: icon("borrow"),
      }, [el("span", { text: "借阅" })]);
      borrowButton.addEventListener("click", () => borrowItem(item, borrowButton));
      actions.append(borrowButton);
    }

    if (canManage) {
      const editButton = el("button", {
        class: "btn btn-ghost btn-sm", type: "button", html: icon("edit"),
      }, [el("span", { text: "编辑" })]);
      editButton.addEventListener("click", () => openMaterialForm(item));
      actions.append(editButton);

      if (item.status === "available") {
        const disableButton = el("button", {
          class: "btn btn-ghost btn-sm", type: "button", html: icon("ban"),
        }, [el("span", { text: "停用" })]);
        disableButton.addEventListener("click", () => disableItem(item, disableButton));
        actions.append(disableButton);
      } else if (item.status === "disabled") {
        const enableButton = el("button", {
          class: "btn btn-ghost btn-sm", type: "button", html: icon("check"),
        }, [el("span", { text: "启用" })]);
        enableButton.addEventListener("click", () => enableItem(item, enableButton));
        actions.append(enableButton);
      }

      const deleteButton = el("button", {
        class: "btn btn-danger btn-sm", type: "button", html: icon("x"),
      }, [el("span", { text: "删除" })]);
      deleteButton.addEventListener("click", () => deleteItem(item, deleteButton));
      actions.append(deleteButton);
    }

    return el("tr", {}, [
      el("td", {}, [
        el("div", { class: "cell-main", text: item.title }),
        el("div", { class: "cell-sub cell-mono", text: item.material_code }),
      ]),
      el("td", {}, [
        el("div", { class: "cell-main", text: item.modality }),
        el("div", { class: "cell-sub", text: item.body_part }),
      ]),
      el("td", { text: item.material_type }),
      el("td", { text: item.storage_location }),
      el("td", {}, [materialStatusPill(item.status)]),
      el("td", {}, [actions]),
    ]);
  }

  function showDetail(item) {
    let modal = null;
    const closeButton = el("button", {
      class: "btn btn-secondary", type: "button", text: "关闭",
      onclick: () => modal && modal.close(),
    });
    modal = openModal({
      title: "资料详情",
      large: true,
      body: detailList([
        ["资料编号", item.material_code],
        ["资料名称", item.title],
        ["影像检查类型", item.modality],
        ["检查部位", item.body_part],
        ["资料载体", item.material_type],
        ["存放位置", item.storage_location],
        ["当前状态", materialStatusPill(item.status)],
        ["创建时间", formatDateTime(item.created_at)],
      ]),
      footer: [closeButton],
    });
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
        toast(errorMessage(error), "error");
        if (error.status === 409) await load();
      }
    }, "办理中…");
  }

  async function disableItem(item, button) {
    await runBusy(button, async () => {
      const confirmed = await confirmDialog({
        title: "停用资料",
        message: `确认停用《${item.title}》？停用后将不能再办理借阅，历史记录仍会保留。`,
        confirmText: "确认停用",
        danger: true,
      });
      if (!confirmed) return;

      try {
        await api.disableMaterial(item.id);
        toast("资料已停用", "success");
        await load();
      } catch (error) {
        if (isAuthError(error)) return;
        toast(errorMessage(error), "error");
        if (error.status === 409) await load();
      }
    }, "处理中…");
  }

  async function enableItem(item, button) {
    await runBusy(button, async () => {
      const confirmed = await confirmDialog({
        title: "启用资料",
        message: `确认启用《${item.title}》？启用后将恢复为可借阅状态。`,
        confirmText: "确认启用",
      });
      if (!confirmed) return;

      try {
        await api.enableMaterial(item.id);
        toast("资料已启用，恢复为可借阅", "success");
        await load();
      } catch (error) {
        if (isAuthError(error)) return;
        toast(errorMessage(error), "error");
        if (error.status === 409) await load();
      }
    }, "处理中…");
  }

  async function deleteItem(item, button) {
    await runBusy(button, async () => {
      const confirmed = await confirmDialog({
        title: "删除资料",
        message: `确认永久删除《${item.title}》（${item.material_code}）？删除后不可恢复。若存在借阅记录，会先提示是否连同历史一起删除。`,
        confirmText: "确认删除",
        danger: true,
      });
      if (!confirmed) return;

      try {
        const result = await api.deleteMaterial(item.id);
        toast(
          result.deleted_records
            ? `资料已删除，同时删除 ${result.deleted_records} 条借阅记录`
            : "资料已删除",
          "success",
        );
        await load();
        return;
      } catch (error) {
        if (isAuthError(error)) return;
        if (error.status !== 409 || !String(error.message).includes("借阅记录")) {
          toast(errorMessage(error), "error");
          return;
        }

        const force = await confirmDialog({
          title: "该资料存在借阅记录",
          message: `《${item.title}》已有借阅历史。强制删除会同时删除它的全部借阅记录，且不可恢复。确认继续？`,
          confirmText: "连同历史删除",
          danger: true,
        });
        if (!force) return;

        try {
          const result = await api.deleteMaterial(item.id, true);
          toast(`资料已删除，同时删除 ${result.deleted_records} 条借阅记录`, "success");
          await load();
        } catch (forceError) {
          if (isAuthError(forceError)) return;
          toast(errorMessage(forceError), "error");
        }
      }
    }, "删除中…");
  }

  function openMaterialForm(item) {
    const editing = Boolean(item);
    const inputs = {};
    for (const field of Object.keys(FIELD_LABELS)) {
      inputs[field] = el("input", {
        class: "input",
        type: "text",
        value: item ? String(item[field] ?? "") : "",
        maxlength: 100,
        "aria-label": FIELD_LABELS[field],
      });
      if (editing && field === "material_code") inputs[field].disabled = true;
    }

    const grid = el("div", { class: "form-grid" }, Object.entries(FIELD_LABELS).map(([field, label]) =>
      el("div", { class: `field${field === "storage_location" ? " full" : ""}` }, [
        el("label", { class: "field-label" }, [
          label,
          field !== "storage_location" ? el("span", { class: "required", text: "*" }) : null,
        ]),
        inputs[field],
        field === "material_code" && editing
          ? el("span", { class: "field-hint", text: "资料编号创建后不可修改" })
          : null,
      ]),
    ));

    const errorBox = formErrorBox();
    const form = el("form", { novalidate: true }, [grid, errorBox]);

    let modal = null;
    const cancelButton = el("button", {
      class: "btn btn-secondary", type: "button", text: "取消",
      onclick: () => modal && modal.close(),
    });
    const submitButton = el("button", {
      class: "btn btn-primary", type: "button", text: editing ? "保存修改" : "创建资料",
    });

    let saving = false;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (saving) return;
      hideFormError(errorBox);

      const payload = {};
      for (const field of Object.keys(FIELD_LABELS)) {
        const value = inputs[field].value.trim();
        if (!value) {
          showFormError(errorBox, `请填写${FIELD_LABELS[field]}`);
          inputs[field].focus();
          return;
        }
        payload[field] = value;
      }

      const body = editing
        ? {
            title: payload.title,
            modality: payload.modality,
            body_part: payload.body_part,
            material_type: payload.material_type,
            storage_location: payload.storage_location,
          }
        : payload;

      saving = true;
      try {
        await runBusy(submitButton, async () => {
          try {
            if (editing) await api.updateMaterial(item.id, body);
            else await api.createMaterial(body);
            toast(editing ? "资料信息已更新" : "资料创建成功", "success");
            if (modal) modal.close();
            await load();
          } catch (error) {
            if (isAuthError(error)) return;
            showFormError(errorBox, describeError(error));
          }
        }, editing ? "保存中…" : "创建中…");
      } finally {
        saving = false;
      }
    });

    modal = openModal({
      title: editing ? "编辑资料" : "新增资料",
      large: true,
      body: form,
      footer: [cancelButton, submitButton],
    });
    submitButton.addEventListener("click", () => form.requestSubmit());
  }

  const IMPORT_COLUMNS = [
    { field: "material_code", label: "资料编号", aliases: ["material_code", "资料编号", "编号"] },
    { field: "title", label: "资料名称", aliases: ["title", "资料名称", "名称"] },
    { field: "modality", label: "影像检查类型", aliases: ["modality", "影像检查类型", "检查类型"] },
    { field: "body_part", label: "检查部位", aliases: ["body_part", "检查部位", "部位"] },
    { field: "material_type", label: "资料载体", aliases: ["material_type", "资料载体", "载体"] },
    { field: "storage_location", label: "存放位置", aliases: ["storage_location", "存放位置", "位置"] },
  ];

  function parseCsv(text) {
    const rows = [];
    let row = [];
    let field = "";
    let quoted = false;
    for (let index = 0; index < text.length; index += 1) {
      const char = text[index];
      if (quoted) {
        if (char === '"') {
          if (text[index + 1] === '"') {
            field += '"';
            index += 1;
          } else {
            quoted = false;
          }
        } else {
          field += char;
        }
      } else if (char === '"') {
        quoted = true;
      } else if (char === ",") {
        row.push(field);
        field = "";
      } else if (char === "\n") {
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
      } else if (char !== "\r") {
        field += char;
      }
    }
    if (field.length || row.length) {
      row.push(field);
      rows.push(row);
    }
    return rows.filter((cells) => cells.some((cell) => String(cell).trim() !== ""));
  }

  function parseImportFile(text) {
    const matrix = parseCsv(text.replace(/^\ufeff/, ""));
    if (matrix.length < 2) {
      throw new Error("CSV 至少需要一行表头和一行数据");
    }
    const header = matrix[0].map((cell) => String(cell).trim().toLowerCase());
    const indexes = {};
    const missing = [];
    for (const column of IMPORT_COLUMNS) {
      const index = header.findIndex((cell) => column.aliases.map((a) => a.toLowerCase()).includes(cell));
      if (index === -1) missing.push(column.label);
      else indexes[column.field] = index;
    }
    if (missing.length) {
      throw new Error(`CSV 缺少列：${missing.join("、")}`);
    }

    const rows = matrix.slice(1).map((cells) => {
      const row = {};
      for (const column of IMPORT_COLUMNS) {
        row[column.field] = String(cells[indexes[column.field]] ?? "").trim();
      }
      return row;
    });
    if (rows.length > 500) {
      throw new Error("单次最多导入 500 行");
    }
    return rows;
  }

  function downloadTemplate() {
    const header = IMPORT_COLUMNS.map((column) => column.field).join(",");
    const example = "IMG-2026-001,示例资料,CT,胸部,胶片,一号库 A-01";
    const content = "\ufeff" + header + "\r\n" + example + "\r\n";
    downloadBlob(new Blob([content], { type: "text/csv;charset=utf-8" }), "资料导入模板.csv");
  }

  function openImportForm() {
    let rows = [];
    let modal = null;

    const fileInput = el("input", {
      class: "input", type: "file", accept: ".csv,text/csv",
      "aria-label": "选择 CSV 文件",
    });
    const preview = el("div", { class: "field-hint", text: "尚未选择文件" });
    const errorBox = formErrorBox();
    const resultBox = el("div", { class: "modal-note", style: { display: "none" } });
    const templateButton = el("button", {
      class: "btn btn-ghost btn-sm", type: "button", html: icon("records"),
    }, [el("span", { text: "下载导入模板" })]);
    templateButton.addEventListener("click", downloadTemplate);

    const body = el("div", {}, [
      el("p", { class: "field-hint", style: { marginBottom: "10px" }, text:
        "支持 UTF-8 CSV，首行必须是字段名（可用中文表头）。资料编号不能与已有资料重复。" }),
      el("div", { class: "field" }, [
        el("label", { class: "field-label" }, ["选择 CSV 文件"]),
        fileInput,
      ]),
      el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "8px" } }, [
        preview,
        templateButton,
      ]),
      resultBox,
      errorBox,
    ]);

    const cancelButton = el("button", {
      class: "btn btn-secondary", type: "button", text: "取消",
      onclick: () => modal && modal.close(),
    });
    const importButton = el("button", {
      class: "btn btn-primary", type: "button", text: "开始导入", disabled: true,
    });

    fileInput.addEventListener("change", async () => {
      hideFormError(errorBox);
      resultBox.style.display = "none";
      rows = [];
      importButton.disabled = true;
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        preview.textContent = "尚未选择文件";
        return;
      }
      if (file.size > 2 * 1024 * 1024) {
        preview.textContent = "文件过大";
        showFormError(errorBox, "CSV 文件不能超过 2 MB");
        return;
      }
      if (file.size === 0) {
        preview.textContent = "文件为空";
        showFormError(errorBox, "CSV 文件为空，请重新选择");
        return;
      }

      let text;
      try {
        const buffer = await file.arrayBuffer();
        text = new TextDecoder("utf-8").decode(buffer);
        if (text.includes("\uFFFD")) {
          try {
            const gbk = new TextDecoder("gbk", { fatal: true }).decode(buffer);
            if (gbk && !gbk.includes("\uFFFD")) text = gbk;
          } catch (fallbackError) {
            // 浏览器不支持 GBK 或无法解码时保留 UTF-8 结果
          }
        }
      } catch (error) {
        preview.textContent = "文件读取失败";
        showFormError(errorBox, "文件不存在或无法读取，请重新选择");
        return;
      }

      try {
        rows = parseImportFile(text);
        preview.textContent = `已读取 ${rows.length} 行，请确认后导入`;
        importButton.disabled = rows.length === 0;
      } catch (error) {
        preview.textContent = "文件解析失败";
        showFormError(errorBox, error.message || "CSV 格式错误，请检查后重试");
      }
    });

    importButton.addEventListener("click", async () => {
      if (!rows.length) {
        showFormError(errorBox, "请先选择有效的 CSV 文件");
        return;
      }
      hideFormError(errorBox);
      await runBusy(importButton, async () => {
        try {
          const result = await api.importMaterials(rows);
          const summary = `成功 ${result.success_count} 条，失败 ${result.failed_count} 条`;
          resultBox.style.display = "flex";
          resultBox.replaceChildren(
            el("span", { html: icon(result.failed_count ? "alert" : "check") }),
            el("span", {}, [
              el("div", { text: summary }),
              ...result.errors.slice(0, 10).map((item) =>
                el("div", { class: "cell-sub", text: `第 ${item.row} 行：${item.message}` }),
              ),
            ]),
          );
          toast(summary, result.failed_count ? "warn" : "success");
          await load();
          if (!result.failed_count && modal) {
            modal.close();
          }
        } catch (error) {
          if (isAuthError(error)) return;
          showFormError(errorBox, errorMessage(error));
        }
      }, "导入中…");
    });

    modal = openModal({
      title: "批量导入资料",
      large: true,
      body,
      footer: [cancelButton, importButton],
    });
  }

  async function load() {
    state.loading = true;
    state.error = null;
    paint();
    try {
      state.items = await api.materials();
      refreshModalityOptions();
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
