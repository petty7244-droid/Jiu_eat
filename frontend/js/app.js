/**
 * Jiu-Eat 前端應用程式
 * ==============================
 * 單頁應用程式（SPA）的主邏輯，功能包括：
 *  - 活動列表與搜尋、分類、城市篩選
 *  - 活動詳細頁（申請參加 / 發起人審核 / 編輯刪除）
 *  - 會員中心（個人資料、我建立的、我的申請）
 *  - 認證（登入 / 註冊 / 登出，使用 sessionStorage 保存狀態）
 *
 * 流程概覽：
 *  1. 頁面載入後依 location.hash 呼叫 route() 切換頁面
 *  2. 所有 API 呼叫皆透過 api() 函式統一處理錯誤
 *  3. 所有按鈕點擊事件使用「事件委派」統一在 document 上處理
 */

// ── 全域設定與狀態 ──────────────────────────────────────

const API_BASE = window.__API_BASE__ || "";                  // API 基礎路徑（可由 window.__API_BASE__ 覆寫，預設為同源）
const state = { activities: [], visible: 8, currentActivity: null, favoriteIds: new Set() };  // 全域狀態（活動列表、顯示數量、目前檢視的活動、追蹤的活動編號）
const $ = (selector) => document.querySelector(selector);     // 單一元素選擇器簡寫
const $$ = (selector) => [...document.querySelectorAll(selector)];    // 多元素選擇器（展開為陣列）
// 從 sessionStorage 讀取目前登入的會員編號；未登入或發生例外時回傳 null
const memberId = () => { try { const val = sessionStorage.getItem("memberId"); return val ? Number(val) : null; } catch { return null; } };
// 從 sessionStorage 讀取登入憑證 token；未登入或發生例外時回傳 null
const authToken = () => { try { return sessionStorage.getItem("token") || null; } catch { return null; } };


// ── API 請求封裝 ────────────────────────────────────────

async function api(path, options = {}) {
  /** 統一的 API 請求函式，自動帶入 JSON header、登入憑證與錯誤處理 */
  const token = authToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;   // 已登入時自動帶上 token
  const response = await fetch(`${API_BASE}${path}`, { headers, ...options });
  const data = response.status === 204 ? null : await response.json();
  // 曾攜帶 token 卻收到 401：代表憑證已失效（例如伺服器重啟），自動清除登入狀態避免殘留
  if (response.status === 401 && token) { sessionStorage.clear(); updateAuthUi(); }
  if (!response.ok) throw new Error(data?.detail || "操作失敗");
  return data;
}


// ── 工具函式 ────────────────────────────────────────────

function escapeHtml(value = "") {
  /** 轉義 HTML 特殊字元，防止 XSS 攻擊 */
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function showToast(message) {
  /** 顯示 Toast 提示訊息（2.8 秒後自動隱藏） */
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 2800);
}

function formatDate(value) {
  /** 將日期時間格式化為台灣慣用格式（月/日 星期 時:分） */
  return new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Taipei" }).format(new Date(value.endsWith("Z") || value.includes("+") ? value : value + "+08:00"));
}

function parseTaipei(value) {
  /** 解析後端回傳時間：無時區資訊的分數視為台北時間（UTC+8），避免跨時區誤判 */
  const s = String(value);
  return new Date(s.endsWith("Z") || s.includes("+") ? s : s + "+08:00");
}

function categoryIcon(category) {
  /** 根據活動分類回傳對應的圖示 */
  return ({ "美食饗宴": "🍱", "桌遊派對": "🎲", "歡唱KTV": "🎤", "戶外運動": "⛰️", "咖啡閒聊": "☕" })[category] || "✨";
}


// ── 通知 ────────────────────────────────────────────────

function updateNotificationBadge(count) {
  /** 更新鈴鐺圖示上的未讀數量徽章 */
  const badge = $("#notification-badge");
  badge.classList.toggle("hidden", !count);
  badge.textContent = count > 99 ? "99+" : count;
}

async function loadUnreadCount() {
  /** 取得目前會員的未讀通知數量並更新鈴鐺徽章 */
  if (!memberId()) return;
  try { const data = await api("/api/notifications/unread-count"); updateNotificationBadge(data.count); } catch { /* 連線失敗時忽略 */ }
}

async function loadNotifications() {
  /** 載入未讀通知列表並渲染到通知面板（已讀通知不顯示） */
  const list = $("#notification-list");
  try {
    const items = await api("/api/notifications");
    const unread = items.filter((n) => !n.is_read);          // 只顯示未讀通知
    updateNotificationBadge(unread.length);
    list.innerHTML = unread.length ? unread.map((n) => `<div class="notification-item" data-notification-id="${n.id}" data-activity-id="${n.activity_id}"><div class="notification-message">${escapeHtml(n.message)}</div><div class="notification-meta">${formatDate(n.created_at)}・${escapeHtml(n.activity_title)}</div></div>`).join("") : `<p class="notification-empty">目前沒有通知。</p>`;
  } catch (error) { showToast(error.message); }
}

async function markNotificationRead(id) {
  /** 將單筆通知標記為已讀，並從通知面板移除 */
  try { await api(`/api/notifications/${id}/read`, { method: "PUT" }); } catch { /* 忽略 */ }
  document.querySelector(`[data-notification-id="${id}"]`)?.remove();
  const list = $("#notification-list");
  if (!list.querySelector(".notification-item")) list.innerHTML = `<p class="notification-empty">目前沒有通知。</p>`;
  loadUnreadCount();
}

async function toggleNotificationPanel() {
  /** 切換通知面板開關：開啟時載入最新通知 */
  const panel = $("#notification-panel");
  if (panel.classList.contains("hidden")) { panel.classList.remove("hidden"); await loadNotifications(); }
  else panel.classList.add("hidden");
}


// ── 活動追蹤 ───────────────────────────────────────────

async function loadFavoriteIds() {
  /** 載入目前會員追蹤的活動編號集合（供愛心圖示狀態判斷） */
  if (!memberId()) { state.favoriteIds = new Set(); return; }
  try { const data = await api("/api/favorites/ids"); state.favoriteIds = new Set(data.ids); } catch { state.favoriteIds = new Set(); }
}


// ── 活動卡片渲染 ────────────────────────────────────────

function cardHtml(item) {
  /** 將活動資料轉換為卡片 HTML */
  const remaining = Math.max(item.max_participants - item.approved_count, 0);
  const image = item.image_url || `https://picsum.photos/seed/jiueat${item.id}/600/400`;  // 無圖片時使用隨機圖片
  const isFav = state.favoriteIds.has(item.id);
  return `<button class="event-card" data-activity-id="${item.id}"><div class="card-img" style="background-image:url('${escapeHtml(image)}')"><span class="card-tag">${categoryIcon(item.category)} ${escapeHtml(item.category)}</span></div><div class="card-content"><div class="event-title"><span class="event-title-text">${escapeHtml(item.title)}</span><span class="fav-heart ${isFav ? "active" : ""}" data-favorite-id="${item.id}" role="button" aria-label="${isFav ? "取消追蹤" : "加入追蹤"}" title="${isFav ? "取消追蹤" : "加入追蹤"}">${isFav ? "♥" : "♡"}</span></div><div class="event-info"><span>📍 ${escapeHtml(item.city)}・${escapeHtml(item.location_name)}</span><span>🗓 ${formatDate(item.activity_date)}</span></div><div class="card-footer"><span>發起人 ${escapeHtml(item.organizer_name)}</span><span class="status-badge">${remaining ? `還有 ${remaining} 個名額` : "已額滿"}</span></div></div></button>`;
}

function renderCards(container, items) {
  /** 批次渲染活動卡片到指定容器 */
  $(container).innerHTML = items.map(cardHtml).join("");
}


// ── 首頁 ────────────────────────────────────────────────

async function loadHome() {
  /** 載入首頁資料：熱門活動 + 推薦活動 */
  try {
    await loadFavoriteIds();                                   // 先載入追蹤狀態，讓愛心圖示正確顯示
    const activities = await api("/api/activities?limit=8");
    renderCards("#popular-grid", activities.slice(0, 4));     // 前 4 筆為熱門活動
    $("#home-empty").classList.toggle("hidden", activities.length > 0);
    if (memberId()) {
      // 已登入：使用推薦 API
      const recommendations = await api(`/api/recommendations/${memberId()}`);
      renderCards("#recommendation-grid", recommendations.slice(0, 4));
      $("#recommendation-note").textContent = recommendations.length ? "依你的興趣與居住縣市排序。" : "目前沒有新的推薦活動。";
    } else {
      // 未登入：不顯示推薦活動，僅顯示提示文字
      renderCards("#recommendation-grid", []);
      $("#recommendation-note").textContent = "登入後，系統會依你的興趣與居住縣市推薦活動。";
    }
  } catch (error) {
    $("#home-empty").classList.remove("hidden");
    $("#home-empty").textContent = "無法連接後端，請確認 FastAPI 已在 8000 埠啟動。";
  }
}


// ── 活動列表頁 ──────────────────────────────────────────

async function loadActivities() {
  /** 載入活動列表：依據篩選條件查詢 */
  await loadFavoriteIds();                                     // 先載入追蹤狀態，讓愛心圖示正確顯示
  const params = new URLSearchParams();
  const keyword = $("#filter-keyword").value.trim();
  const category = $("#filter-category").value;
  const city = $("#filter-city").value.trim();
  if (keyword) params.set("keyword", keyword);
  if (category) params.set("category", category);
  if (city) params.set("city", city);
  state.activities = await api(`/api/activities?${params}`);
  state.visible = 8;                                         // 重置顯示數量
  renderActivityList();
}

function renderActivityList() {
  /** 渲染活動列表與「載入更多」按鈕 */
  renderCards("#activities-grid", state.activities.slice(0, state.visible));
  $("#activities-empty").classList.toggle("hidden", state.activities.length > 0);
  $("#load-more-button").classList.toggle("hidden", state.visible >= state.activities.length);
}


// ── 登入檢查 ────────────────────────────────────────────

function requireLogin() {
  /** 檢查是否已登入，未登入則開啟認證視窗 */
  if (memberId()) return true;
  openAuth();
  showToast("請先登入會員");
  return false;
}


// ── 活動詳細頁 ──────────────────────────────────────────

async function openDetail(id) {
  /** 開啟活動詳細頁：載入資料並渲染 */
  try {
    await loadFavoriteIds();                                   // 先載入追蹤狀態，讓愛心圖示正確顯示
    const item = await api(`/api/activities/${id}`);
    state.currentActivity = item;
    const mine = memberId() === item.organizer_id;            // 是否為發起人
    const remaining = Math.max(item.max_participants - item.approved_count, 0);
    const pastDeadline = parseTaipei(item.deadline) <= new Date();
    const appStatus = item.my_application_status;
    const isFav = state.favoriteIds.has(item.id);
    let applyDisabled, applyText;
    const canCancel = appStatus === "pending";
    if (appStatus === "pending") {
      applyDisabled = true; applyText = "覆核中";
    } else if (appStatus === "rejected") {
      applyDisabled = true; applyText = "已被拒絕";
    } else if (appStatus === "approved") {
      applyDisabled = true; applyText = "成功申請";
    } else if (pastDeadline) {
      applyDisabled = true; applyText = "報名已截止";
    } else if (!remaining) {
      applyDisabled = true; applyText = "已額滿";
    } else {
      applyDisabled = false; applyText = "申請參加";
    }
    // 渲染活動詳細內容（發起人可看到編輯/刪除按鈕，一般用戶看到申請按鈕）
    showPage("activity-detail");
    const applyBtn = `<button class="button button-primary" data-apply-activity ${applyDisabled ? "disabled" : ""}>${applyText}</button>`;
    const cancelBtn = canCancel ? `<button class="button button-outline" data-activity-cancel="${item.my_application_id}">取消報名</button>` : "";
    $("#activity-detail").innerHTML = `<div class="detail-image" style="background-image:url('${escapeHtml(item.image_url || `https://picsum.photos/seed/jiueat${item.id}/900/500`)}')"></div><div class="detail-body"><span class="section-kicker">${categoryIcon(item.category)} ${escapeHtml(item.category)}</span><div class="detail-title-row"><h1>${escapeHtml(item.title)}</h1><button class="fav-heart fav-heart-lg ${isFav ? "active" : ""}" data-favorite-id="${item.id}" aria-label="${isFav ? "取消追蹤" : "加入追蹤"}" title="${isFav ? "取消追蹤" : "加入追蹤"}">${isFav ? "♥" : "♡"}</button></div><div class="detail-meta"><span>📍 ${escapeHtml(item.city)}・${escapeHtml(item.location_name)}</span><span>🗓 ${formatDate(item.activity_date)}</span><span>⏳ 報名至 ${formatDate(item.deadline)}</span><span>👥 ${item.approved_count} / ${item.max_participants} 人</span></div><p class="detail-description">${escapeHtml(item.description || "發起人尚未填寫詳細說明。")}</p><p>發起人：<strong>${escapeHtml(item.organizer_name)}</strong></p><div class="detail-actions">${mine ? `<button class="button button-primary" data-edit-activity>編輯活動</button><button class="button button-outline" data-review-applicants>查看申請</button><button class="button button-outline" data-exit-activity>退出返回</button><button class="button button-outline" data-delete-activity>刪除活動</button>` : `${applyBtn}${cancelBtn}`}</div><div id="applicant-list" class="member-list"></div></div>`;
    if (location.hash !== `#activity/${id}`) location.hash = `#activity/${id}`;
  } catch (error) { showToast(error.message); }
}


// ── 頁面切換 ────────────────────────────────────────────

function showPage(name) {
  /** 切換顯示的頁面區塊 */
  $$(".page").forEach((page) => page.classList.remove("active"));
  $(`#${name}-page`)?.classList.add("active");
  $("#main-nav").classList.remove("open");                   // 關閉導覽選單
  $("#notification-panel").classList.add("hidden");          // 切頁時關閉通知面板
  window.scrollTo(0, 0);                                     // 捲動到頂部
}


// ── 路由控制 ────────────────────────────────────────────

async function route() {
  /** 根據 URL hash 切換頁面並載入對應資料 */
  const hash = location.hash || "#home";
  if (hash.startsWith("#activity/")) { showPage("activity-detail"); return openDetail(Number(hash.split("/")[1])); }
  if (hash === "#activities") { showPage("activities"); try { await loadActivities(); } catch (e) { showToast(e.message); } return; }
  if (hash === "#member") { if (!requireLogin()) return; showPage("member"); await loadMember(); return; }
  if (hash === "#create") { if (!requireLogin()) return; prepareActivityForm(); showPage("activity-form"); return; }
  showPage("home"); loadHome();                              // 預設首頁
}


// ── 認證視窗 ────────────────────────────────────────────

function openAuth(tab = "login-form") {
  /** 開啟認證視窗 */
  $("#auth-modal").classList.remove("hidden");
  switchAuthTab(tab);
}

function closeAuth() { $("#auth-modal").classList.add("hidden"); }

function switchAuthTab(id) {
  /** 切換登入/註冊分頁 */
  $$(".auth-form").forEach((form) => form.classList.toggle("active", form.id === id));
  $$(".auth-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.authTab === id));
}

function updateAuthUi() {
  /** 根據登入狀態更新 UI（顯示/隱藏會員專用元素、按鈕文字） */
  const loggedIn = Boolean(memberId());
  $$(".member-only").forEach((item) => item.classList.toggle("hidden", !loggedIn));
  $("#auth-button").textContent = loggedIn ? `登出 ${sessionStorage.getItem("displayName") || ""}` : "登入／註冊";
  if (!loggedIn) {                                             // 登出後清除通知徽章與面板
    $("#notification-badge").classList.add("hidden");
    $("#notification-panel").classList.add("hidden");
    state.favoriteIds = new Set();                             // 清空追蹤狀態
  }
  $("#main-nav").classList.remove("open");                     // 登入/登出後關閉行動版選單
}


// ── 會員中心 ────────────────────────────────────────────

async function loadMember() {
  /** 載入會員中心資料：個人資料 + 建立的活動 + 申請的活動 + 追蹤的活動 */
  try {
    const [member, data, favorites] = await Promise.all([api(`/api/members/${memberId()}`), api(`/api/members/${memberId()}/activities`), api("/api/favorites")]);
    state.favoriteIds = new Set(favorites.map((item) => item.id));   // 同步愛心狀態
    $("#member-welcome").textContent = `${member.display_name}，在這裡管理你的資料與聚會。`;
    const form = $("#profile-form");
    // 填入文字欄位
    ["email", "display_name", "gender", "age", "zodiac", "occupation", "city", "district", "bio"].forEach((key) => form.elements[key].value = member[key] || "");
    // 勾選興趣複選框
    const interests = (member.interests || "").split(",").map(s => s.trim()).filter(Boolean);
    form.querySelectorAll('input[name="interests"]').forEach(cb => cb.checked = interests.includes(cb.value));
    // 勾選偏好料理複選框
    const cuisines = (member.preferred_cuisine || "").split(",").map(s => s.trim()).filter(Boolean);
    form.querySelectorAll('input[name="preferred_cuisine"]').forEach(cb => cb.checked = cuisines.includes(cb.value));
    // 渲染建立的活動列表
    $("#created-list").innerHTML = data.created.length ? data.created.map((item) => `<div class="member-item"><div><h3>${escapeHtml(item.title)}</h3><p>${formatDate(item.activity_date)}・${escapeHtml(item.city)}</p></div><div class="member-actions"><button class="button button-outline small" data-activity-id="${item.id}">查看</button><button class="button button-primary small" data-edit-id="${item.id}">編輯</button></div></div>`).join("") : `<p class="empty-state">你還沒有建立活動。</p>`;
    // 渲染申請的活動列表
    $("#applied-list").innerHTML = data.applications.length ? data.applications.map((item) => `<div class="member-item"><div><h3 class="link-title" data-activity-id="${item.activity_id}" title="查看活動">${escapeHtml(item.activity_title)}</h3><p>申請時間 ${formatDate(item.created_at)}</p></div><div class="member-actions"><span class="status ${item.status}">${({ pending: "待審核", approved: "已核准", rejected: "已拒絕", cancelled: "取消報名" })[item.status]}</span>${item.status === "pending" ? `<button class="button button-outline small" data-cancel-id="${item.id}">取消申請</button>` : ""}</div></div>`).join("") : `<p class="empty-state">你目前沒有活動申請。</p>`;
    // 渲染追蹤的活動列表（活動名稱 / 活動時間 / 取消追蹤）
    $("#tracked-list").innerHTML = favorites.length ? favorites.map((item) => `<div class="member-item"><div><h3 class="link-title" data-activity-id="${item.id}" title="查看活動">${escapeHtml(item.title)}</h3><p>${formatDate(item.activity_date)}・${escapeHtml(item.city)}</p></div><div class="member-actions"><button class="button button-outline small" data-untrack-id="${item.id}">取消追蹤</button></div></div>`).join("") : `<p class="empty-state">你還沒有追蹤任何活動。</p>`;
  } catch (error) { showToast(error.message); }
}


// ── 活動表單 ────────────────────────────────────────────

function prepareActivityForm(item = null) {
  /** 準備活動表單：新增模式或編輯模式 */
  const form = $("#activity-form"); form.reset(); $("#activity-id").value = item?.id || "";
  $("#activity-form-title").textContent = item ? "編輯聚會" : "發起聚會";
  $("#activity-form").querySelector("[data-delete-form]").hidden = !item;
  if (!item) return;
  // 編輯模式：填入現有資料
  ["title", "description", "category", "city", "location_name", "max_participants", "image_url"].forEach((key) => form.elements[key].value = item[key] || "");
  form.elements.activity_date.value = item.activity_date.slice(0, 16); form.elements.deadline.value = item.deadline.slice(0, 16);
}


// ── 申請審核 ────────────────────────────────────────────

async function reviewApplicants() {
  /** 載入並顯示活動的申請人列表 */
  try {
    const items = await api(`/api/activities/${state.currentActivity.id}/applications`);
    $("#applicant-list").innerHTML = items.length ? items.map((item) => `<div class="member-item"><div><h3>${escapeHtml(item.member_name)}</h3><p>${escapeHtml(item.message || "沒有留言")}</p></div><div class="member-actions"><span class="status ${item.status}">${item.status}</span>${item.status === "pending" ? `<button class="button button-primary small" data-approve-id="${item.id}">核准</button><button class="button button-outline small" data-reject-id="${item.id}">拒絕</button>` : ""}</div></div>`).join("") : `<p class="empty-state">目前還沒有申請人。</p>`;
  } catch (error) { showToast(error.message); }
}


// ── 全域點擊事件處理（事件委派）─────────────────────────

document.addEventListener("click", async (event) => {
  // 點擊通知項目 → 標記已讀並前往該活動詳情
  const notifItem = event.target.closest("[data-notification-id]");
  if (notifItem) { markNotificationRead(Number(notifItem.dataset.notificationId)); location.hash = `#activity/${notifItem.dataset.activityId}`; return; }
  // 點擊愛心 → 加入／取消活動追蹤（需在活動卡片判斷之前，避免觸發跳頁）
  const favHeart = event.target.closest("[data-favorite-id]");
  if (favHeart) {
    if (!requireLogin()) return;
    const id = Number(favHeart.dataset.favoriteId);
    const isFav = state.favoriteIds.has(id);
    try {
      if (isFav) { await api(`/api/favorites/${id}`, { method: "DELETE" }); state.favoriteIds.delete(id); showToast("已取消追蹤"); }
      else { await api(`/api/favorites/${id}`, { method: "POST" }); state.favoriteIds.add(id); showToast("已加入追蹤"); }
      // 同步更新頁面上所有同一活動的愛心圖示
      document.querySelectorAll(`[data-favorite-id="${id}"]`).forEach((el) => {
        const active = state.favoriteIds.has(id);
        el.classList.toggle("active", active);
        el.textContent = active ? "♥" : "♡";
        el.setAttribute("aria-label", active ? "取消追蹤" : "加入追蹤");
        el.setAttribute("title", active ? "取消追蹤" : "加入追蹤");
      });
    } catch (e) { showToast(e.message); }
    return;
  }
  // 點擊活動卡片 → 開啟詳細頁
  const activityButton = event.target.closest("[data-activity-id]"); if (activityButton) return openDetail(Number(activityButton.dataset.activityId));
  // 返回首頁
  if (event.target.closest("[data-back]")) { location.hash = "#home"; return; }
  // 刪除活動表單（從表單內刪除）
  if (event.target.matches("[data-delete-form]")) { if (!confirm("確定刪除這場活動嗎？")) return; const id = $("#activity-id").value; try { await api(`/api/activities/${id}`, { method: "DELETE" }); showToast("活動已刪除"); state.currentActivity = null; location.hash = "#home"; } catch (e) { showToast(e.message); } return; }
  // 編輯活動（從詳細頁進入）
  if (event.target.matches("[data-edit-activity]")) { prepareActivityForm(state.currentActivity); showPage("activity-form"); return; }
  // 查看申請列表
  if (event.target.matches("[data-review-applicants]")) return reviewApplicants();
  // 退出返回（從詳細頁回到首頁）
  if (event.target.matches("[data-exit-activity]")) { location.hash = "#home"; return; }
  // 申請參加活動
  if (event.target.matches("[data-apply-activity]")) { if (!requireLogin()) return; if (parseTaipei(state.currentActivity.deadline) <= new Date()) { showToast("報名已截止"); return; } const message = prompt("想對發起人說什麼？（可留空）") ?? ""; try { await api(`/api/activities/${state.currentActivity.id}/applications`, { method: "POST", body: JSON.stringify({ message }) }); showToast("申請已送出"); openDetail(state.currentActivity.id); } catch (e) { showToast(e.message); } return; }
  // 取消報名（從活動詳細頁）
  const cancelActivity = event.target.closest("[data-activity-cancel]"); if (cancelActivity) { if (!confirm("確定取消報名？")) return; try { await api(`/api/applications/${cancelActivity.dataset.activityCancel}/cancel`, { method: "PUT" }); showToast("已取消報名"); openDetail(state.currentActivity.id); } catch (e) { showToast(e.message); } return; }
  // 刪除活動（從詳細頁）
  if (event.target.matches("[data-delete-activity]")) { if (!confirm("確定刪除這場活動嗎？")) return; try { await api(`/api/activities/${state.currentActivity.id}`, { method: "DELETE" }); showToast("活動已刪除"); state.currentActivity = null; location.hash = "#home"; } catch (e) { showToast(e.message); } return; }
  // 編輯活動（從會員中心列表）
  const edit = event.target.closest("[data-edit-id]"); if (edit) { const item = await api(`/api/activities/${edit.dataset.editId}`); prepareActivityForm(item); showPage("activity-form"); return; }
  // 核准/拒絕申請
  for (const action of ["approve", "reject"]) { const btn = event.target.closest(`[data-${action}-id]`); if (btn) { try { await api(`/api/applications/${btn.dataset[`${action}Id`]}/${action}`, { method: "PUT" }); await reviewApplicants(); showToast("申請狀態已更新"); } catch (e) { showToast(e.message) } return; } }
  // 取消申請
  const cancel = event.target.closest("[data-cancel-id]"); if (cancel) { try { await api(`/api/applications/${cancel.dataset.cancelId}/cancel`, { method: "PUT" }); await loadMember(); showToast("已取消申請"); } catch (e) { showToast(e.message) } }
  // 取消追蹤（從會員中心追蹤活動列表）
  const untrack = event.target.closest("[data-untrack-id]"); if (untrack) { try { await api(`/api/favorites/${untrack.dataset.untrackId}`, { method: "DELETE" }); state.favoriteIds.delete(Number(untrack.dataset.untrackId)); showToast("已取消追蹤"); loadMember(); } catch (e) { showToast(e.message) } }
});


// ── 綁定事件監聽器 ──────────────────────────────────────

// 登入/登出按鈕
$("#auth-button").addEventListener("click", async () => { if (memberId()) { try { await api("/api/logout", { method: "POST" }); } catch { } sessionStorage.clear(); updateAuthUi(); loadHome(); showToast("已登出"); } else openAuth(); });
// 建立活動按鈕
$("#create-button").addEventListener("click", () => { if (requireLogin()) location.hash = "#create"; });
// 表單選單開關
$("#menu-button").addEventListener("click", () => $("#main-nav").classList.toggle("open"));
// 通知鈴鐺：切換通知面板
$("#notification-bell").addEventListener("click", toggleNotificationPanel);
// 全部標記已讀
$("#notification-read-all").addEventListener("click", async () => { try { await api("/api/notifications/read-all", { method: "PUT" }); await loadNotifications(); showToast("已全部標記為已讀"); } catch (e) { showToast(e.message); } });
// 點擊面板外區域時關閉通知面板
document.addEventListener("click", (event) => {
  const panel = $("#notification-panel");
  if (!panel.classList.contains("hidden") && !event.target.closest("#notification-bell") && !event.target.closest("#notification-panel")) panel.classList.add("hidden");
});
// 關閉認證視窗
$("#close-auth").addEventListener("click", closeAuth);
// 點擊遮罩關閉認證視窗
$("#auth-modal").addEventListener("click", (e) => { if (e.target.id === "auth-modal") closeAuth(); });
// 認證分頁切換
$$(".auth-tab").forEach((tab) => tab.addEventListener("click", () => switchAuthTab(tab.dataset.authTab)));

// 登入表單送出
$("#login-form").addEventListener("submit", async (e) => { e.preventDefault(); const form = new FormData(e.target); try { const data = await api("/api/login", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) }); sessionStorage.setItem("memberId", data.member_id); sessionStorage.setItem("displayName", data.display_name); sessionStorage.setItem("token", data.token); updateAuthUi(); loadUnreadCount(); closeAuth(); loadHome(); showToast("登入成功"); } catch (error) { showToast(error.message) } });
// 註冊表單送出
$("#register-form").addEventListener("submit", async (e) => { e.preventDefault(); const btn = e.target.querySelector('button[type="submit"]'); if (btn.disabled) return; btn.disabled = true; const payload = Object.fromEntries(new FormData(e.target)); try { await api("/api/register", { method: "POST", body: JSON.stringify(payload) }); showToast("註冊成功，請登入"); switchAuthTab("login-form"); $("#login-form").elements.email.value = payload.email; $("#login-form").elements.password.value = ""; } catch (error) { showToast(error.message) } finally { btn.disabled = false; } });

// 首頁搜尋表單
$("#home-search-form").addEventListener("submit", (e) => { e.preventDefault(); $("#filter-keyword").value = $("#home-keyword").value; location.hash = "#activities"; });
// 首頁分類篩選
$$("#home-categories .category-chip").forEach((chip) => chip.addEventListener("click", () => { $("#filter-category").value = chip.dataset.category; location.hash = "#activities"; }));
// 活動列表篩選表單
$("#filter-form").addEventListener("submit", (e) => { e.preventDefault(); loadActivities().catch(error => showToast(error.message)); });
// 載入更多按鈕
$("#load-more-button").addEventListener("click", () => { state.visible += 8; renderActivityList(); });
// 會員中心分頁切換
$$(".tab").forEach((tab) => tab.addEventListener("click", () => { $$(".tab").forEach(t => t.classList.remove("active")); $$(".tab-panel").forEach(p => p.classList.remove("active")); tab.classList.add("active"); $(`#${tab.dataset.tab}`).classList.add("active"); }));

// 個人資料表單送出（含興趣與偏好料理驗證）
$("#profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  // 收集已勾選的興趣（至少 3 項）
  const checkedInterests = [...form.querySelectorAll('input[name="interests"]:checked')].map(cb => cb.value);
  // 前端驗證：至少勾選 3 項興趣，未達標則中止送出
  if (checkedInterests.length < 3) { showToast("請至少選擇 3 項興趣"); return; }
  // 收集已勾選的偏好料理
  const checkedCuisines = [...form.querySelectorAll('input[name="preferred_cuisine"]:checked')].map(cb => cb.value);
  // 組裝表單資料並送出
  const fd = new FormData(form);
  fd.set("interests", checkedInterests.join(","));
  fd.set("preferred_cuisine", checkedCuisines.join(","));
  const payload = Object.fromEntries(fd);
  delete payload.email;                                     // Email 不可修改
  try { const data = await api(`/api/members/${memberId()}`, { method: "PUT", body: JSON.stringify(payload) }); sessionStorage.setItem("displayName", data.display_name); updateAuthUi(); showToast("個人資料已更新"); loadHome(); } catch (error) { showToast(error.message) }
});

// 活動表單送出（新增或編輯）
$("#activity-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = Object.fromEntries(new FormData(e.target));
  if (payload.image_url && !/^https?:\/\//i.test(payload.image_url)) { showToast("封面圖片網址必須以 http:// 或 https:// 開頭"); return; }  // 與後端一致：只允許 http/https
  payload.max_participants = Number(payload.max_participants);
  payload.activity_date = payload.activity_date + ":00";        // 補齊秒數
  payload.deadline = payload.deadline + ":00";
  const id = $("#activity-id").value;
  try { const data = await api(id ? `/api/activities/${id}` : "/api/activities", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) }); showToast(id ? "活動已更新" : "活動已建立"); openDetail(data.id); } catch (error) { showToast(error.message) }
});


// ── 初始化 ──────────────────────────────────────────────

// 監聽 URL hash 變化（點擊連結或瀏覽器上一頁/下一頁）→ 重新路由
window.addEventListener("hashchange", route);
// 已登入時每 30 秒輪詢未讀通知數量，更新鈴鐺徽章
setInterval(() => { if (memberId()) loadUnreadCount(); }, 30000);
// 頁面載入時：先依登入狀態更新 UI，再依目前 hash 載入對應頁面
try { updateAuthUi(); loadUnreadCount(); route(); } catch (e) { console.error("初始化失敗", e); showToast("頁面載入異常，請重新整理"); }
