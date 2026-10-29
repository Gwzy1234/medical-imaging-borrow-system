/**
 * 数据备份与恢复页面（仅管理员）。
 */

import { api } from "./api.js?v=0.9.1";
import { clearSession } from "./auth.js?v=0.9.1";
import {
  el, icon, toast, confirmDialog, runBusy, downloadBlob,
  isAuthError, errorMessage, formErrorBox, showFormError, hideFormError,
} from "./ui.js?v=0.9.1";

function fileStamp() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_`
    + `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

export async function renderBackup(view) {
  const errorBox = formErrorBox();

  const downloadButton = el("button", {
    class: "btn btn-primary", type: "button", html: icon("box"),
  }, [el("span", { text: "下载数据库备份" })]);
  downloadButton.addEventListener("click", () => runBusy(downloadButton, async () => {
    hideFormError(errorBox);
    try {
      const blob = await api.downloadDatabase();
      downloadBlob(blob, `yy_backup_${fileStamp()}.db`);
      toast("数据库备份已下载", "success");
    } catch (error) {
      if (isAuthError(error)) return;
      showFormError(errorBox, errorMessage(error));
    }
  }, "打包中…"));

  let fileBuffer = null;
  const fileInput = el("input", {
    class: "input", type: "file", accept: ".db,application/octet-stream",
    "aria-label": "选择数据库备份文件",
  });
  const fileName = el("div", { class: "field-hint", text: "尚未选择文件" });

  const restoreButton = el("button", {
    class: "btn btn-danger", type: "button", html: icon("refresh"), disabled: true,
  }, [el("span", { text: "恢复数据库" })]);

  restoreButton.addEventListener("click", async () => {
    if (!fileBuffer) {
      showFormError(errorBox, "请选择有效的数据库备份文件");
      return;
    }
    const confirmed = await confirmDialog({
      title: "恢复数据库",
      message: "恢复会用备份文件覆盖当前全部数据（用户、资料、借阅记录、操作日志），操作不可撤销。系统会先自动保存一份当前数据库作为安全备份。确认继续？",
      confirmText: "确认恢复",
      danger: true,
    });
    if (!confirmed) return;

    await runBusy(restoreButton, async () => {
      try {
        const blob = new Blob([fileBuffer], { type: "application/octet-stream" });
        const result = await api.restoreDatabase(blob);
        toast(`数据库已恢复，安全备份：${result.safety_backup}`, "success");
        clearSession();
        window.setTimeout(() => window.location.reload(), 1500);
      } catch (error) {
        if (isAuthError(error)) return;
        showFormError(errorBox, errorMessage(error));
      }
    }, "恢复中…");
  });

  fileInput.addEventListener("change", async () => {
    hideFormError(errorBox);
    restoreButton.disabled = true;
    fileBuffer = null;
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      fileName.textContent = "尚未选择文件";
      return;
    }
    if (file.size === 0) {
      fileName.textContent = "文件为空";
      showFormError(errorBox, "备份文件为空，请重新选择");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      fileName.textContent = "文件过大";
      showFormError(errorBox, "备份文件不能超过 50 MB");
      return;
    }

    try {
      fileBuffer = await file.arrayBuffer();
    } catch (error) {
      fileName.textContent = "文件读取失败";
      showFormError(errorBox, "文件不存在或无法读取，请重新选择");
      return;
    }

    fileName.textContent = `已选择：${file.name}（${(file.size / 1024).toFixed(0)} KB）`;
    restoreButton.disabled = false;
  });

  const downloadCard = el("section", { class: "card" }, [
    el("div", { class: "card-head" }, [
      el("div", {}, [
        el("div", { class: "card-title" }, [el("span", { html: icon("box") }), el("span", { text: "下载数据库备份" })]),
        el("div", { class: "card-sub", text: "生成当前数据库的一致性快照，下载后可离线保存" }),
      ]),
    ]),
    el("div", { class: "card-body" }, [
      el("p", { class: "field-hint", style: { marginBottom: "14px" }, text:
        "备份文件是标准 SQLite 数据库，包含全部用户、资料、借阅记录和操作日志。建议在批量导入、恢复或演示前先下载一份。" }),
      downloadButton,
    ]),
  ]);

  const restoreCard = el("section", { class: "card" }, [
    el("div", { class: "card-head" }, [
      el("div", {}, [
        el("div", { class: "card-title" }, [el("span", { html: icon("refresh") }), el("span", { text: "从备份恢复" })]),
        el("div", { class: "card-sub", text: "用备份文件覆盖当前数据库，恢复前会自动保存安全备份" }),
      ]),
    ]),
    el("div", { class: "card-body" }, [
      el("div", { class: "modal-note", style: { marginTop: "0", marginBottom: "14px" } }, [
        el("span", { html: icon("alert") }),
        el("span", { text: "恢复会覆盖当前数据并让所有账号退出登录。请确认选择的文件是本系统的 .db 备份，且包含启用的管理员账号。" }),
      ]),
      el("div", { class: "field" }, [
        el("label", { class: "field-label" }, ["选择备份文件"]),
        fileInput,
        fileName,
      ]),
      el("div", { style: { marginTop: "14px" } }, [restoreButton]),
    ]),
  ]);

  const content = el("div", { class: "grid-2" }, [downloadCard, restoreCard]);
  view.append(
    el("div", { class: "page-hero" }, [
      el("div", {}, [
        el("h1", { class: "hero-title", text: "数据备份与恢复" }),
        el("p", { class: "hero-sub", text: "备份当前数据库，或从备份文件恢复数据" }),
      ]),
    ]),
    content,
    el("div", { style: { marginTop: "16px" } }, [errorBox]),
  );
}
