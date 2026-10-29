/**
 * 统一的后端请求封装。
 * - 自动附带 Bearer 令牌
 * - 统一解析 {code, message} 错误格式
 * - 401 时清空本地令牌并广播事件，由应用层回到登录页
 */

const TOKEN_KEY = "yy.token";

const STATUS_MESSAGES = {
  400: "请求有误",
  401: "登录已失效，请重新登录",
  403: "没有权限执行该操作",
  404: "请求的资源不存在",
  405: "请求方法不被允许",
  409: "数据状态冲突，请刷新后重试",
  422: "提交的数据不合法",
  429: "操作过于频繁，请稍后再试",
  500: "服务器内部错误",
  503: "服务暂时繁忙，请稍后重试",
};

export class ApiError extends Error {
  constructor(status, code, message, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch (error) {
    return null;
  }
}

export function setToken(token) {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch (error) {
    /* 浏览器禁用存储时退化为仅当前页面可用 */
  }
}

export function clearToken() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch (error) {
    /* 忽略 */
  }
}

async function parseBody(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (error) {
    return null;
  }
}

async function requestBlob(path, query) {
  let url = path;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        params.set(key, String(value));
      }
    }
    const queryString = params.toString();
    if (queryString) url += `?${queryString}`;
  }

  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(url, { headers });
  } catch (error) {
    throw new ApiError(0, "network", "无法连接服务器，请确认服务已启动");
  }

  if (!response.ok) {
    const data = await parseBody(response);
    if (response.status === 401) {
      clearToken();
      window.dispatchEvent(new CustomEvent("yy:unauthorized"));
    }
    throw new ApiError(
      response.status,
      (data && data.code) || "http_error",
      (data && data.message) || STATUS_MESSAGES[response.status] || "导出失败，请稍后重试",
    );
  }
  return response.blob();
}

async function requestUpload(path, blob) {
  const headers = { "Content-Type": "application/octet-stream" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(path, { method: "POST", headers, body: blob });
  } catch (error) {
    throw new ApiError(0, "network", "无法连接服务器，请确认服务已启动");
  }

  const data = await parseBody(response);
  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
      window.dispatchEvent(new CustomEvent("yy:unauthorized"));
    }
    throw new ApiError(
      response.status,
      (data && data.code) || "http_error",
      (data && data.message) || STATUS_MESSAGES[response.status] || "操作失败，请稍后重试",
    );
  }
  return data;
}

/**
 * 发起请求。
 * @param {string} path
 * @param {{method?: string, body?: object, query?: object, auth?: boolean, timeout?: number}} options
 */
export async function request(path, options = {}) {
  const { method = "GET", body, query, auth = true, timeout = 15000 } = options;

  let url = path;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        params.set(key, String(value));
      }
    }
    const queryString = params.toString();
    if (queryString) url += `?${queryString}`;
  }

  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    const aborted = controller.signal.aborted;
    throw new ApiError(
      0,
      aborted ? "timeout" : "network",
      aborted ? "请求超时，请稍后重试" : "无法连接服务器，请确认服务已启动",
    );
  } finally {
    clearTimeout(timer);
  }

  const data = await parseBody(response);

  if (!response.ok) {
    if (response.status === 401 && auth) {
      clearToken();
      window.dispatchEvent(new CustomEvent("yy:unauthorized"));
    }
    const message =
      (data && data.message) || STATUS_MESSAGES[response.status] || "请求失败，请稍后重试";
    throw new ApiError(response.status, (data && data.code) || "http_error", message, data && data.errors);
  }

  return data;
}

export const api = {
  // 认证
  login: (username, password) =>
    request("/auth/login", { method: "POST", body: { username, password }, auth: false }),
  me: () => request("/auth/me"),
  logout: () => request("/auth/logout", { method: "POST" }),

  // 资料
  materials: (query) => request("/materials", { query }),
  availableMaterials: (query) => request("/materials/available", { query }),
  material: (id) => request(`/materials/${id}`),
  createMaterial: (payload) => request("/materials", { method: "POST", body: payload }),
  importMaterials: (rows) =>
    request("/materials/import", { method: "POST", body: { rows } }),
  updateMaterial: (id, payload) =>
    request(`/materials/${id}`, { method: "PATCH", body: payload }),
  disableMaterial: (id) => request(`/materials/${id}/disable`, { method: "POST" }),
  enableMaterial: (id) => request(`/materials/${id}/enable`, { method: "POST" }),
  deleteMaterial: (id, force = false) =>
    request(`/materials/${id}${force ? "?force=true" : ""}`, { method: "DELETE" }),

  // 用户
  users: (query) => request("/users", { query }),
  createUser: (payload) => request("/users", { method: "POST", body: payload }),
  disableUser: (id) => request(`/users/${id}/disable`, { method: "POST" }),
  enableUser: (id) => request(`/users/${id}/enable`, { method: "POST" }),
  changeRole: (id, role) => request(`/users/${id}/role`, { method: "PATCH", body: { role } }),

  // 借阅
  activeBorrows: (query) => request("/borrows/active", { query }),
  history: (query) => request("/borrows/history", { query }),
  overdue: (query) => request("/borrows/overdue", { query }),
  borrow: (materialId, dueAt) =>
    request("/borrows", {
      method: "POST",
      body: dueAt ? { material_id: materialId, due_at: dueAt } : { material_id: materialId },
    }),
  giveBack: (materialId) =>
    request(`/borrows/${materialId}/return`, { method: "POST" }),

  // 操作日志（仅管理员）
  logs: (query) => request("/logs", { query }),
  exportLogs: (query) => requestBlob("/logs/export.csv", query),
  archiveLogs: (before) =>
    request("/logs/archive", { method: "POST", body: { before } }),

  // 数据备份与恢复（仅管理员）
  downloadDatabase: () => requestBlob("/backup/database"),
  restoreDatabase: (blob) => requestUpload("/backup/restore", blob),
};
