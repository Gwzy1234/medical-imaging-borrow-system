/**
 * 应用入口：恢复登录状态、在登录页与主界面之间切换。
 */

import { clearSession, restore } from "./auth.js?v=0.9.1";
import { mountApp, renderLogin } from "./views.js?v=0.9.1";

const root = document.getElementById("app");
let booting = true;

function showLogin(message = "") {
  // 登录失效时可能还有未关闭的弹窗或提示，先清理再渲染登录页
  document.querySelectorAll(".modal-overlay").forEach((node) => node.remove());
  document.body.classList.remove("modal-open");
  document.querySelectorAll(".toast").forEach((node) => node.remove());
  renderLogin(root, {
    message,
    onSuccess: () => {
      if (!location.hash || location.hash === "#/login" || location.hash === "#/") {
        location.hash = "#/dashboard";
      }
      mount();
    },
  });
}

function mount() {
  mountApp(root, {
    onLoggedOut: () => showLogin(),
  });
}

window.addEventListener("yy:unauthorized", () => {
  if (booting) return;
  clearSession();
  showLogin("登录已失效，请重新登录");
});

(async () => {
  let restored = false;
  try {
    restored = await restore();
  } finally {
    booting = false;
  }
  if (restored) mount();
  else showLogin();
})();
