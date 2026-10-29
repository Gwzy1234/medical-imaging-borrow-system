/**
 * 登录状态管理。
 * 令牌保存在 sessionStorage（关闭标签页即失效）；
 * 用户信息只包含 id / username / role / is_active，不含任何敏感字段。
 */

import { api, getToken, setToken, clearToken } from "./api.js?v=0.9.1";

const USER_KEY = "yy.user";

let currentUser = null;

function readStoredUser() {
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    return null;
  }
}

function storeUser(user) {
  currentUser = user;
  try {
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch (error) {
    /* 忽略存储失败 */
  }
}

export function getUser() {
  if (!currentUser) currentUser = readStoredUser();
  return currentUser;
}

export function isLoggedIn() {
  return Boolean(getToken() && getUser());
}

export function hasRole(...roles) {
  const user = getUser();
  return Boolean(user && roles.includes(user.role));
}

export async function login(username, password) {
  const data = await api.login(username, password);
  setToken(data.token);
  storeUser(data.user);
  return data.user;
}

export async function restore() {
  if (!getToken()) return false;
  try {
    const user = await api.me();
    storeUser(user);
    return true;
  } catch (error) {
    clearSession();
    return false;
  }
}

export async function logout() {
  try {
    await api.logout();
  } catch (error) {
    /* 令牌可能已失效，仍然清理本地状态 */
  } finally {
    clearSession();
  }
}

export function clearSession() {
  clearToken();
  currentUser = null;
  try {
    sessionStorage.removeItem(USER_KEY);
  } catch (error) {
    /* 忽略 */
  }
}
