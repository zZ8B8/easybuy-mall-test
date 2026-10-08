/* ============================================================
   易淘商城 · 前端公共脚本
   只做三件事：管 token、发请求、渲染导航栏用户状态
   ============================================================ */
"use strict";

const API = {
  token: localStorage.getItem("easybuy_token") || "",
  username: localStorage.getItem("easybuy_user") || "",

  setLogin(token, username) {
    this.token = token;
    this.username = username;
    localStorage.setItem("easybuy_token", token);
    localStorage.setItem("easybuy_user", username);
    this.renderNav();
  },

  logout() {
    this.token = "";
    this.username = "";
    localStorage.removeItem("easybuy_token");
    localStorage.removeItem("easybuy_user");
    this.renderNav();
    location.reload();
  },

  /** 发请求。返回 {ok, status, code, data, message} */
  async request(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    if (this.token) headers["Authorization"] = "Bearer " + this.token;

    const opts = { method, headers };
    if (body !== undefined && body !== null) opts.body = JSON.stringify(body);

    let res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      return { ok: false, status: 0, code: "NETWORK_ERROR",
               message: "请求失败，服务是不是没启动？" };
    }

    let json = null;
    try { json = await res.json(); } catch (e) { /* 非 JSON 响应 */ }

    if (res.status === 401 && json && json.code === "UNAUTHORIZED") {
      this.logout();
    }

    return {
      ok: res.ok && json && json.code === "OK",
      status: res.status,
      code: (json && json.code) || "UNKNOWN",
      data: json && json.data,
      message: (json && json.message) || "",
    };
  },

  get(path) { return this.request("GET", path); },
  post(path, body) { return this.request("POST", path, body); },
  put(path, body) { return this.request("PUT", path, body); },
  del(path) { return this.request("DELETE", path); },

  renderNav() {
    const el = document.getElementById("nav-user");
    if (!el) return;
    if (this.username) {
      el.innerHTML = "你好，<b>" + esc(this.username) + "</b>" +
                     '<button class="sm" onclick="API.logout()">退出</button>';
    } else {
      el.innerHTML = '<a href="/login">登录 / 注册</a>';
    }
  },
};

/* ---------- 小工具 ---------- */
function esc(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function money(n) {
  return "¥" + Number(n || 0).toFixed(2);
}

const STATUS_TEXT = { PENDING: "待支付", PAID: "已支付", CANCELLED: "已取消" };

function statusBadge(s) {
  const cls = (s || "").toLowerCase();
  return '<span class="badge ' + cls + '">' + esc(STATUS_TEXT[s] || s) + "</span>";
}

function alertBox(id) { return document.getElementById(id); }

function showAlert(id, type, text) {
  const el = alertBox(id);
  if (!el) return;
  el.className = "alert " + type + " show";
  el.textContent = text;
  if (type === "ok") setTimeout(() => { el.className = "alert"; }, 2500);
}

function hideAlert(id) {
  const el = alertBox(id);
  if (el) el.className = "alert";
}

document.addEventListener("DOMContentLoaded", () => API.renderNav());
