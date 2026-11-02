/**
 * 猫迹 CatTrace - 全局通用交互逻辑模块
 * 城市流浪猫生命共同体 (增强版 v2.0)
 *
 * 本文件包含项目全局共享的工具函数、API 封装、UI 组件和业务模块：
 * - 工具函数：debounce（防抖）、throttle（节流）
 * - API 模块：统一封装 fetch 请求（GET/POST/PUT/DELETE），自动携带认证 token
 * - Toast 提示系统：全局轻量级消息提示
 * - Auth 认证系统：登录/登出/游客模式管理
 * - DarkMode 深色模式：主题切换与持久化
 * - CatUI 猫咪工具：emoji/背景色/头像颜色映射
 * - CatDiary 日记生成：基于模板随机生成猫咪日记文本
 * - CommunityMediation 社区共治：调解建议报告生成
 * - ResourceAllocation 资源分配：绝育比例计算
 * - MissingCatTracker 失踪追踪：失踪等级判定与推送文本
 * - LiveRoom 直播间：投喂、日志、环境数据模拟
 * - ShareUI 分享功能：分享弹窗与社交平台跳转
 * - CatsPage 猫咪档案页：筛选、搜索、排行榜
 * - AdoptPage 领养页面：领养表单与提交
 * - StatsDashboard 统计看板：统计卡片与图表渲染
 * - NotificationCenter 通知系统：通知列表与轮询
 * - AIVerifier AI 验证指示器：模拟 AI 识别状态
 * - 全局辅助函数：举报、面板切换、排行榜、滚动定位等
 */

// ============================================
// 工具函数模块
// ============================================

/**
 * 防抖函数：在连续触发时，只有最后一次触发后等待指定时间才会执行
 * 常用于搜索框输入、窗口 resize 等高频事件
 * @param {Function} func - 需要防抖的回调函数
 * @param {number} [wait=300] - 等待时间（毫秒）
 * @returns {Function} 防抖包装后的函数
 */
function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => { clearTimeout(timeout); func(...args); };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * 节流函数：在指定时间间隔内最多执行一次
 * 常用于滚动事件、按钮点击防重复等场景
 * @param {Function} func - 需要节流的回调函数
 * @param {number} [limit=1000] - 节流间隔（毫秒）
 * @returns {Function} 节流包装后的函数
 */
function throttle(func, limit = 1000) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) { func.apply(this, args); inThrottle = true; setTimeout(() => inThrottle = false, limit); }
    };
}

/**
 * API 模块 - 统一封装后端接口请求
 * 所有 HTTP 请求通过此模块发起，自动处理认证 token 和错误提示
 * @constant {Object}
 * @property {string} BASE - API 基础路径
 */
const API = {
    BASE: '/api',

    /**
     * 从 localStorage 获取认证 token
     * @private
     * @returns {string} token 字符串，未登录时返回空字符串
     */
    _token() { return localStorage.getItem('auth_token') || ''; },

    /**
     * 发送 HTTP 请求的底层方法
     * @private
     * @param {string} method - HTTP 方法（GET/POST/PUT/DELETE）
     * @param {string} path - 请求路径（会自动拼接 BASE 前缀）
     * @param {Object|null} [body=null] - 请求体对象（GET 请求时忽略）
     * @param {boolean} [auth=true] - 是否需要携带认证 token
     * @returns {Promise<Object>} 后端返回的 JSON 数据
     * @throws {Error} 网络异常或需要登录时抛出错误
     */
    async _request(method, path, body = null, auth = true) {
        const headers = { 'Content-Type': 'application/json' };
        const token = this._token();
        /* 需要认证且 token 存在时，添加 Authorization 请求头 */
        if (auth && token) headers['Authorization'] = 'Bearer ' + token;
        const opts = { method, headers };
        /* GET 请求不携带 body */
        if (body && method !== 'GET') opts.body = JSON.stringify(body);
        try {
            const res = await fetch(this.BASE + path, opts);
            const data = await res.json();
            /* 后端返回 need_login 标记时，弹出登录框并抛错 */
            if (data.need_login) { Auth.showLogin(); throw new Error(data.message || '请先登录'); }
            return data;
        } catch (err) {
            /* 网络不可达时显示全局提示 */
            if (err.message === 'Failed to fetch') Toast.show('网络异常，请检查连接', 3000, 'error');
            throw err;
        }
    },

    /**
     * 发送 GET 请求
     * @param {string} path - 请求路径
     * @param {boolean} [auth=false] - 是否需要认证
     * @returns {Promise<Object>}
     */
    get(path, auth = false) { return this._request('GET', path, null, auth); },

    /**
     * 发送 POST 请求
     * @param {string} path - 请求路径
     * @param {Object} body - 请求体
     * @param {boolean} [auth=false] - 是否需要认证
     * @returns {Promise<Object>}
     */
    post(path, body, auth = false) { return this._request('POST', path, body, auth); },

    /**
     * 发送 PUT 请求（默认需要认证）
     * @param {string} path - 请求路径
     * @param {Object} body - 请求体
     * @param {boolean} [auth=true] - 是否需要认证
     * @returns {Promise<Object>}
     */
    put(path, body, auth = true) { return this._request('PUT', path, body, auth); },

    /**
     * 发送 DELETE 请求（默认需要认证）
     * @param {string} path - 请求路径
     * @param {boolean} [auth=true] - 是否需要认证
     * @returns {Promise<Object>}
     */
    delete(path, auth = true) { return this._request('DELETE', path, null, auth); }
};

// ============================================
// Toast 提示系统
// ============================================

/**
 * Toast 模块 - 全局轻量级消息提示系统
 * 在页面顶部/中央显示短暂的消息通知，支持 success/error/warning/info 四种类型
 * 目标 DOM：#toast
 * @constant {Object}
 */
const Toast = {
    /** @type {HTMLElement|null} toast 容器 DOM 元素 */
    element: null,
    /** @type {number|null} 自动关闭定时器 ID */
    timer: null,

    /** 初始化：获取 #toast DOM 元素 */
    init() { this.element = document.getElementById('toast'); },

    /**
     * 显示一条 Toast 消息
     * @param {string} message - 消息文本
     * @param {number} [duration=3000] - 显示持续时间（毫秒）
     * @param {string} [type='info'] - 消息类型：'success' | 'error' | 'warning' | 'info'
     */
    show(message, duration = 3000, type = 'info') {
        if (!this.element) this.init();
        if (!this.element) return;
        this.element.className = 'toast show';
        /* 非 info 类型添加对应的 CSS 类名以显示不同颜色 */
        if (type !== 'info') this.element.classList.add('toast-' + type);
        /* 根据类型显示不同图标 */
        this.element.innerHTML = '<span class="toast-icon">' + (type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️') + '</span><span class="toast-message">' + this._esc(message) + '</span>';
        if (this.timer) clearTimeout(this.timer);
        this.timer = setTimeout(() => this.element.classList.remove('show'), duration);
    },

    /**
     * HTML 转义，防止 XSS
     * @private
     * @param {string} text - 待转义文本
     * @returns {string} 转义后的安全字符串
     */
    _esc(text) { const d = document.createElement('div'); d.textContent = text; return d.innerHTML; },

    /** 显示成功提示 @param {string} m - 消息 @param {number} d - 持续时间 */
    success(m,d) { this.show(m,d,'success'); },
    /** 显示错误提示 @param {string} m - 消息 @param {number} d - 持续时间 */
    error(m,d) { this.show(m,d,'error'); },
    /** 显示警告提示 @param {string} m - 消息 @param {number} d - 持续时间 */
    warning(m,d) { this.show(m,d,'warning'); }
};

// ============================================
// 认证系统模块
// ============================================

/**
 * Auth 模块 - 用户认证系统
 * 管理登录/登出/游客模式，包括：
 * - token 持久化（localStorage 键名：auth_token）
 * - 游客 ID 生成与持久化（localStorage 键名：guest_id）
 * - 登录弹窗的注入与交互（手机号 + 验证码）
 * - 导航栏登录状态 UI 同步
 * 目标 DOM：#loginModal, #loginBtn
 * @constant {Object}
 */
const Auth = {
    /** @type {Object|null} 当前登录用户信息 */
    user: null,
    /** @type {boolean} 是否为游客模式 */
    isGuest: true,

    /**
     * 认证系统初始化
     * 1. 检查 localStorage 中是否有 token，有则拉取用户信息，否则生成游客 ID
     * 2. 注入登录弹窗 HTML
     * 3. 绑定导航栏登录按钮事件
     */
    init() {
        const token = localStorage.getItem('auth_token');
        if (token) this._fetchUser(); else { this.isGuest = true; this._generateGuestId(); }
        this._injectModal(); this._bindNavButton();
    },

    /**
     * 从后端拉取当前登录用户信息
     * 调用 /auth/me 接口，成功后更新用户状态和 UI；失败则清除 token 降级为游客
     * @private
     * @returns {Promise<void>}
     */
    async _fetchUser() {
        try { const data = await API.get('/auth/me', true); if (data.success && data.user) { this.user = data.user; this.isGuest = false; this._updateNavUI(); } else this._logoutLocal(); } catch { this._logoutLocal(); }
    },

    /**
     * 本地登出处理（清除 token、重置状态、更新 UI）
     * @private
     */
    _logoutLocal() { localStorage.removeItem('auth_token'); this.user = null; this.isGuest = true; this._generateGuestId(); this._updateNavUI(); },

    /**
     * 生成游客 ID 并存入 localStorage
     * 格式：guest_{随机字符串}{时间戳}，仅在不存在时生成
     * @private
     */
    _generateGuestId() { if (!localStorage.getItem('guest_id')) localStorage.setItem('guest_id', 'guest_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36)); },

    /**
     * 获取当前游客 ID
     * @returns {string} 游客 ID 字符串
     */
    getGuestId() { return localStorage.getItem('guest_id') || ''; },

    /**
     * 向页面注入登录弹窗 HTML 并绑定弹窗内的事件
     * 弹窗包含：手机号输入、验证码输入、发送验证码按钮、登录按钮
     * 目标 DOM：注入到 body 末尾，ID 为 loginModal
     * @private
     */
    _injectModal() {
        if (document.getElementById('loginModal')) return;
        const html = `<div id="loginModal" class="modal" style="display:none;"><div class="modal-overlay" id="loginOverlay"></div><div class="modal-content login-modal-content"><div class="modal-header"><h3>📱 登录 猫迹 CatTrace</h3><button class="modal-close" id="loginClose">&times;</button></div><div class="modal-body"><p class="login-desc">登录后无限畅喂，记录你的爱心足迹</p><div class="form-group"><label>📞 手机号</label><input type="tel" id="loginPhone" placeholder="请输入手机号" maxlength="11" class="form-input" /></div><div class="form-group"><label>🔑 验证码</label><div class="code-row"><input type="text" id="loginCode" placeholder="验证码" maxlength="6" class="form-input" style="flex:1;" /><button id="sendCodeBtn" class="btn btn-outline" style="width:120px;">发送验证码</button></div><span class="form-hint">测试验证码：8888</span></div><button id="loginSubmit" class="btn btn-primary btn-block">登 录</button><p class="login-footer-text">登录即表示同意《用户协议》和《隐私政策》</p></div></div></div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        /* 绑定弹窗内各按钮事件 */
        document.getElementById('loginClose').addEventListener('click', () => this.hideLogin());
        document.getElementById('loginOverlay').addEventListener('click', () => this.hideLogin());
        document.getElementById('sendCodeBtn').addEventListener('click', () => this._sendCode());
        document.getElementById('loginSubmit').addEventListener('click', () => this._doLogin());
    },

    /**
     * 绑定导航栏登录按钮的点击事件
     * 游客点击 → 弹出登录框；已登录用户点击 → 执行登出
     * 目标 DOM：#loginBtn
     * @private
     */
    _bindNavButton() { setTimeout(() => { const btn = document.getElementById('loginBtn'); if (btn) { btn.addEventListener('click', () => { if (this.isGuest) this.showLogin(); else this._doLogout(); }); this._updateNavUI(); } }, 100); },

    /**
     * 更新导航栏登录按钮的 UI 状态
     * - 游客模式：显示"登录"，移除 logged-in 类
     * - 已登录：显示用户昵称，添加 logged-in 类
     * 目标 DOM：#loginBtn
     * @private
     */
    _updateNavUI() { const btn = document.getElementById('loginBtn'); if (!btn) return; const textEl = btn.querySelector('.nav-text') || btn.querySelector('span:not(.avatar)') || btn; if (this.isGuest || !this.user) { btn.classList.remove('logged-in'); textEl.textContent = '登录'; } else { btn.classList.add('logged-in'); textEl.textContent = this.user.nickname || '我的'; } },

    /**
     * 显示登录弹窗，清空输入框
     * 目标 DOM：#loginModal, #loginPhone, #loginCode
     */
    showLogin() { const m = document.getElementById('loginModal'); if (m) { m.style.display = 'flex'; document.getElementById('loginPhone').value = ''; document.getElementById('loginCode').value = ''; } },

    /**
     * 隐藏登录弹窗
     * 目标 DOM：#loginModal
     */
    hideLogin() { const m = document.getElementById('loginModal'); if (m) m.style.display = 'none'; },

    /**
     * 发送验证码（模拟）
     * 校验手机号格式（11 位），启动 60 秒倒计时，显示测试验证码提示
     * 目标 DOM：#loginPhone, #sendCodeBtn
     * @private
     */
    _sendCode() { const phone = document.getElementById('loginPhone').value.trim(); if (!phone || phone.length < 11) { Toast.show('请输入正确的手机号', 2500, 'warning'); return; } const btn = document.getElementById('sendCodeBtn'); btn.disabled = true; btn.textContent = '60s后重发'; let sec = 60; const t = setInterval(() => { sec--; btn.textContent = sec + 's后重发'; if (sec <= 0) { clearInterval(t); btn.disabled = false; btn.textContent = '发送验证码'; } }, 1000); Toast.show('验证码已发送（测试：8888）', 2500, 'info'); },

    /**
     * 执行登录操作
     * 校验手机号和验证码 → 调用 /auth/login 接口 → 成功后保存 token、更新 UI、关闭弹窗
     * 目标 DOM：#loginPhone, #loginCode, #loginSubmit
     * @private
     * @returns {Promise<void>}
     */
    async _doLogin() { const phone = document.getElementById('loginPhone').value.trim(); const code = document.getElementById('loginCode').value.trim(); if (!phone || phone.length < 11) { Toast.show('请输入正确的手机号', 2500, 'warning'); return; } if (!code || code.length < 4) { Toast.show('请输入验证码', 2500, 'warning'); return; } const submitBtn = document.getElementById('loginSubmit'); submitBtn.disabled = true; submitBtn.textContent = '登录中...'; try { const data = await API.post('/auth/login', { phone, code }); if (data.success) { localStorage.setItem('auth_token', data.token); this.user = data.user; this.isGuest = false; this._updateNavUI(); this.hideLogin(); Toast.show('欢迎回来，' + data.user.nickname + '！🐱', 3000, 'success'); } else Toast.show(data.message || '登录失败', 3000, 'error'); } catch { Toast.show('登录失败，请重试', 3000, 'error'); } finally { submitBtn.disabled = false; submitBtn.textContent = '登 录'; } },

    /**
     * 执行登出操作
     * 调用 /auth/logout 接口（允许失败），然后清除本地状态并提示
     * @private
     * @returns {Promise<void>}
     */
    async _doLogout() { try { await API.post('/auth/logout', {}); } catch {} this._logoutLocal(); Toast.show('已退出登录', 2000, 'info'); }
};

// ============================================
// 深色模式切换
// ============================================

/**
 * DarkMode 模块 - 深色模式管理
 * 支持三种优先级：用户手动选择 > 系统偏好 > 默认浅色
 * 持久化键名：localStorage 'darkMode'（值为 'true'/'false'）
 * 目标 DOM：#darkModeToggle, <body> data-theme 属性
 * @constant {Object}
 */
const DarkMode = {
    /** @type {boolean} 当前是否为深色模式 */
    isDark: false,

    /**
     * 初始化深色模式
     * 1. 读取 localStorage 中的用户偏好
     * 2. 无偏好时跟随系统 prefers-color-scheme
     * 3. 监听系统主题变化（仅在用户未手动设置时生效）
     */
    init() {
        const saved = localStorage.getItem('darkMode');
        /* 优先级：用户手动选择 > 系统偏好 */
        if (saved === 'true') this.enable(); else if (saved === 'false') this.disable();
        else { this.isDark = window.matchMedia('(prefers-color-scheme: dark)').matches; if (this.isDark) this.enable(); }
        /* 监听系统主题变化，仅在用户未手动设置时跟随 */
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => { if (localStorage.getItem('darkMode') === null) { if (e.matches) this.enable(); else this.disable(); } });
    },

    /** 启用深色模式：设置 body data-theme='dark'，持久化偏好，更新按钮图标 */
    enable() { this.isDark = true; document.body.setAttribute('data-theme', 'dark'); localStorage.setItem('darkMode', 'true'); this.updateIcon(); },

    /** 禁用深色模式：移除 data-theme 属性，持久化偏好，更新按钮图标 */
    disable() { this.isDark = false; document.body.removeAttribute('data-theme'); localStorage.setItem('darkMode', 'false'); this.updateIcon(); },

    /** 切换深色/浅色模式 */
    toggle() { if (this.isDark) this.disable(); else this.enable(); },

    /**
     * 更新深色模式切换按钮的图标和提示文本
     * 目标 DOM：#darkModeToggle
     */
    updateIcon() { const btn = document.getElementById('darkModeToggle'); if (btn) { btn.textContent = this.isDark ? '☀️' : '🌙'; btn.setAttribute('aria-label', this.isDark ? '切换到浅色模式' : '切换到深色模式'); btn.setAttribute('title', this.isDark ? '切换到浅色模式' : '切换到深色模式'); } }
};

// ============================================
// 格式化函数
// ============================================

/**
 * 将时间字符串格式化为相对时间显示
 * 规则：< 1分钟 → "刚刚"，< 1小时 → "X分钟前"，< 1天 → "X小时前"，
 *        < 7天 → "X天前"，>= 7天 → 显示短日期（如 "1月15日 14:30"）
 * @param {string|Date} timeString - 时间字符串或 Date 对象
 * @returns {string} 格式化后的相对时间文本，解析失败返回空字符串
 */
function formatTime(timeString) {
    if (!timeString) return '';
    try {
        const now = new Date();
        /* 将空格分隔符替换为 T 以兼容 ISO 8601 格式 */
        const normalized = typeof timeString === 'string' ? timeString.replace(' ', 'T') : timeString;
        const time = new Date(normalized);
        if (isNaN(time.getTime())) return '';
        const diff = now - time;
        const minute = 60000, hour = 3600000, day = 86400000;
        if (diff < minute) return '刚刚';
        if (diff < hour) return Math.floor(diff / minute) + '分钟前';
        if (diff < day) return Math.floor(diff / hour) + '小时前';
        if (diff < 7 * day) return Math.floor(diff / day) + '天前';
        return time.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
}

/**
 * 将数字格式化为中文千分位显示
 * @param {number} num - 待格式化的数字
 * @returns {string} 千分位格式化后的字符串（如 "1,234"），非数字返回 "0"
 */
function formatNumber(num) { if (typeof num !== 'number' || isNaN(num)) return '0'; return num.toLocaleString('zh-CN'); }

// ============================================
// 猫咪工具模块
// ============================================

/**
 * CatUI 模块 - 猫咪 UI 工具集
 * 提供猫咪颜色到 emoji、背景渐变、头像颜色的映射
 * 模拟数据：emojiMap、bgMap 中的颜色映射为预设数据
 * @constant {Object}
 */
const CatUI = {
    /** @type {Object} 猫咪花色关键词 → emoji 映射（模拟数据） */
    emojiMap: { '黑': '🐱', '白': '🐱', '橘': '🐱', '灰': '🐱', '花': '🐱', '相间': '🐱' },
    /** @type {Object} 猫咪花色关键词 → 背景渐变 CSS 映射（模拟数据） */
    bgMap: { '黑': 'linear-gradient(135deg, #1a1a2e, #16213e)', '白': 'linear-gradient(135deg, #fff, #f0f0f0)', '橘': 'linear-gradient(135deg, #f6d365, #fda085)', '灰': 'linear-gradient(135deg, #4b6cb7, #182848)', '花': 'linear-gradient(135deg, #ffd89b, #19547b)', '相间': 'linear-gradient(135deg, #fff5e6, #ffe0b2)' },
    /** @type {string[]} 头像背景颜色池，按 ID 取模循环使用 */
    avatarColors: ['#d88da3', '#6c5ce7', '#00b894', '#fdcb6e', '#74b9ff', '#fd79a8', '#a29bfe', '#55efc4'],
    /** @type {string[]} 猫咪 emoji 池，按 ID 取模循环使用 */
    avatarEmojis: ['🐱', '😺', '😸', '😻', '😼', '😽', '🙀', '🐈'],

    /**
     * 根据花色名称获取对应 emoji
     * @param {string} color - 花色描述（如 "橘色"、"黑白相间"）
     * @returns {string} 匹配的 emoji，默认返回 🐱
     */
    getEmoji(color) { if (!color) return '🐱'; for (const [k, e] of Object.entries(this.emojiMap)) if (color.includes(k)) return e; return '🐱'; },

    /**
     * 根据花色名称获取对应背景渐变 CSS
     * @param {string} color - 花色描述
     * @returns {string} CSS 渐变字符串，默认返回灰色渐变
     */
    getBg(color) { if (!color) return 'linear-gradient(135deg, #f5f7fa, #c3cfe2)'; for (const [k, bg] of Object.entries(this.bgMap)) if (color.includes(k)) return bg; return 'linear-gradient(135deg, #f5f7fa, #c3cfe2)'; },

    /**
     * 根据猫咪 ID 获取头像背景颜色（循环取色）
     * @param {number} id - 猫咪 ID
     * @returns {string} 十六进制颜色值
     */
    getColor(id) { return this.avatarColors[id % this.avatarColors.length]; },

    /**
     * 根据猫咪 ID 获取对应 emoji（循环取 emoji）
     * @param {number} id - 猫咪 ID
     * @returns {string} 猫咪 emoji
     */
    getEmojiById(id) { return this.avatarEmojis[id % this.avatarEmojis.length]; },

    /**
     * HTML 特殊字符转义，防止 XSS
     * @param {string} text - 待转义文本
     * @returns {string} 转义后的安全字符串
     */
    esc(text) { if (!text) return ''; const d = document.createElement('div'); d.textContent = text; return d.innerHTML; }
};

// ============================================
// 猫咪日记生成模块
// ============================================

/**
 * CatDiary 模块 - 基于模板随机生成猫咪日记文本
 * 所有模板和词库均为模拟数据，用于在前端生成拟真的猫咪日记内容
 * @constant {Object}
 */
const CatDiary = {
    /** @type {string[]} 日记文本模板数组，包含 {name}、{cnt}、{action} 等占位符（模拟数据） */
    templates: [
        '今天{name}来了{cnt}次，最喜欢{prefer}那顿。它吃得很安心，还对着摄像头{action}。',
        '{name}今天特别活跃，在猫屋周围{action}了几圈。{weather_desc}，它{emotion}地蹭了蹭猫屋。',
        '{name}今天似乎有些{emotion}，在猫屋待了{time}分钟。它{action}，可能是在等它的猫朋友。',
        '清晨{time}点，{name}第一个来到猫屋。它{action}，开启了元气满满的一天。'
    ],
    /** @type {string[]} 动作词库（模拟数据） */
    actions: ['打了个哈欠', '伸了个懒腰', '甩了甩尾巴', '舔了舔爪子', '眯了眯眼睛', '轻轻叫了一声'],
    /** @type {string[]} 天气描述词库（模拟数据） */
    weathers: ['阳光很好', '微风习习', '有些凉意', '刚下过雨', '天气暖和', '夜幕降临'],
    /** @type {string[]} 心情词库（模拟数据） */
    emotions: ['开心', '慵懒', '警惕', '放松', '好奇', '温柔'],
    /** @type {string[]} 时段词库（模拟数据） */
    prefers: ['早上', '中午', '下午', '晚上', '深夜'],

    /**
     * 根据猫咪信息和来访数据生成一篇日记文本
     * 随机选取模板，替换其中的占位符为实际内容
     * @param {Object} cat - 猫咪对象，至少包含 name 属性
     * @param {Object|null} visits - 来访统计对象，包含 count 和 avg_duration；为 null 时使用随机值
     * @returns {string} 生成的日记文本
     */
    generate(cat, visits) {
        const tpl = this._pick(this.templates);
        return tpl.replace(/\{name\}/g, cat.name || '猫咪')
            .replace(/\{cnt\}/g, visits?.count || Math.floor(Math.random() * 4) + 1)
            .replace(/\{action\}/g, this._pick(this.actions))
            .replace(/\{weather_desc\}/g, this._pick(this.weathers))
            .replace(/\{emotion\}/g, this._pick(this.emotions))
            .replace(/\{prefer\}/g, this._pick(this.prefers))
            .replace(/\{time\}/g, visits?.avg_duration || Math.floor(Math.random() * 20) + 5);
    },

    /**
     * 从数组中随机选取一个元素
     * @private
     * @param {Array} arr - 源数组
     * @returns {*} 随机选中的元素
     */
    _pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; },

    /**
     * 获取今天的中文日期字符串
     * @returns {string} 格式如 "12月15日 周三"
     */
    today() { const d = new Date(); return d.getMonth() + 1 + '月' + d.getDate() + '日 周' + '日一二三四五六'[d.getDay()]; }
};

// ============================================
// 社区共治调解模块
// ============================================

/**
 * CommunityMediation 模块 - 社区共治调解建议生成
 * 根据投诉内容匹配问题类型，输出禁止清单、替代方案和两周闭环计划
 * 所有数据均为模拟数据
 * @constant {Object}
 */
const CommunityMediation = {
    /** @type {string[]} 禁止行为清单（模拟数据） */
    forbiddenActions: ['私自捕捉猫咪', '擅自转移或遗弃猫咪', '破坏猫屋设备', '投喂有害食物', '驱赶或虐待猫咪'],
    /** @type {Array<{problem: string, solutions: string[]}>} 常见问题及替代方案列表（模拟数据） */
    alternatives: [
        { problem: '夜间猫叫声', solutions: ['加强绝育', '迁移猫屋至远离居民楼', '分时段投喂', '安装超声波驱避器'] },
        { problem: '猫咪聚集', solutions: ['分散投喂点', '控制投喂量', 'TNR计划', '引导至非居民区'] },
        { problem: '粪便问题', solutions: ['设置猫砂盆区域', '定期清理', '引导至绿化带', '与物业协商'] },
        { problem: '过敏/卫生', solutions: ['保持猫屋清洁', '定期消毒', '远离居民楼', '科普科学管理'] }
    ],

    /**
     * 根据投诉内容生成治理建议报告
     * 匹配逻辑：在 alternatives 中查找 problem 包含于投诉文本的条目，未匹配则使用第一条
     * @param {Object} complaint - 投诉对象
     * @param {string} complaint.problem - 投诉问题描述
     * @returns {{forbidden: string[], alternatives: string[], plan: {week1: string, week2: string}}}
     *   返回禁止清单、替代方案和两周执行计划
     */
    generateReport(complaint) {
        const problem = complaint?.problem || '猫咪相关问题';
        const matched = this.alternatives.find(a => problem.includes(a.problem)) || this.alternatives[0];
        return { forbidden: this.forbiddenActions, alternatives: matched.solutions, plan: { week1: '评估现状，制定调整方案', week2: '实施方案，监测效果' } };
    }
};

// ============================================
// 资源分配可视化模块
// ============================================

/**
 * ResourceAllocation 模块 - 资源分配与绝育比例计算
 * 根据猫咪列表计算绝育/未绝育比例，用于可视化展示
 * @constant {Object}
 */
const ResourceAllocation = {
    /**
     * 计算猫咪群体的绝育比例统计
     * 百分比有上下限保护：未绝育最低 30%，已绝育最高 70%
     * @param {Array<Object>} cats - 猫咪数组，每个元素需有 neutered 布尔属性
     * @returns {{unneuteredPct: number, neuteredPct: number, total: number, neutered: number, unneutered: number, month: string}}
     *   绝育/未绝育百分比、总数、当月月份
     */
    calculate(cats) {
        const total = cats.length;
        const neutered = cats.filter(c => c.neutered).length;
        const unneutered = total - neutered;
        return { unneuteredPct: Math.max(total > 0 ? Math.round((unneutered / total) * 100) : 50, 30), neuteredPct: Math.min(total > 0 ? Math.round((neutered / total) * 100) : 50, 70), total, neutered, unneutered, month: (new Date().getMonth() + 1) + '月' };
    },

    /**
     * 获取资源分配策略说明文本
     * @returns {string} 说明文案
     */
    getExplanation() { return '已绝育猫已无繁殖压力，适当减少投喂可鼓励其保留自然捕食能力，更健康、更有野性。可使用"爱心加餐"功能专门投喂已绝育猫（消耗积分或小额支付）。'; }
};

// ============================================
// 失踪猫咪追踪模块
// ============================================

/**
 * MissingCatTracker 模块 - 失踪猫咪追踪与通知
 * 根据猫咪失踪天数判定预警等级，生成推送文本
 * @constant {Object}
 */
const MissingCatTracker = {
    /**
     * 预警等级定义（模拟数据）
     * @type {Object.<string, {days: number, label: string, icon: string}>}
     */
    LEVELS: { warning: { days: 5, label: '预警', icon: '🟡' }, response: { days: 7, label: '正式响应', icon: '🟠' }, escalated: { days: 14, label: '升级响应', icon: '🔴' } },

    /**
     * 根据失踪天数获取预警等级
     * - >= 14 天 → 'escalated'（升级响应）
     * - >= 7 天 → 'response'（正式响应）
     * - >= 5 天 → 'warning'（预警）
     * - < 5 天 → null（无需预警）
     * @param {number} daysAbsent - 失踪天数
     * @returns {string|null} 预警等级键名或 null
     */
    getLevel(daysAbsent) { if (daysAbsent >= 14) return 'escalated'; if (daysAbsent >= 7) return 'response'; if (daysAbsent >= 5) return 'warning'; return null; },

    /**
     * 生成猫咪失踪推送通知文本
     * @param {Object} cat - 猫咪对象，包含 name 属性
     * @returns {string} 失踪提醒文本
     */
    pushText(cat) { return '🐾 【猫咪失踪提醒】您身边的"' + (cat.name || '猫咪') + '"已7天未出现。如果您在小区看到它，请点击上报位置或照片。无需主动搜索，路过时留意即可。'; },

    /**
     * 生成猫咪回归通知文本
     * @param {Object} cat - 猫咪对象，包含 name 属性
     * @returns {string} 回归通知文本
     */
    returnText(cat) { return '🎉 【回归通知】好消息！消失了一段时间的"' + (cat.name || '猫咪') + '"刚刚回到猫屋啦！'; }
};

// ============================================
// 直播间模块
// ============================================

/**
 * LiveRoom 模块 - 猫咪直播间功能
 * 管理直播间猫咪切换、投喂操作、投喂日志加载、在线人数和环境数据模拟
 * 目标 DOM：#roomSelect, #feedBtn, #liveCatEmoji, #liveCatTitle, #liveCatLocation,
 *           #todayFeeds, #feedLogs, #onlineViewers, #temperature, #humidity, #totalFeeds
 * @constant {Object}
 */
const LiveRoom = {
    /** @type {number} 当前直播间猫咪 ID */
    currentCatId: 1,
    /** @type {Object|null} 当前猫咪数据对象 */
    currentCat: null,
    /** @type {Array} 猫咪列表数据 */
    cats: [],
    /** @type {Object} 全局统计数据 */
    stats: {},
    /** @type {number|null} 在线人数模拟定时器 ID */
    viewerTimer: null,
    /** @type {number|null} 环境数据模拟定时器 ID */
    envTimer: null,

    /**
     * 直播间初始化
     * 1. 从 URL 参数读取初始猫咪 ID（?cat=X）
     * 2. 加载猫咪列表和统计数据
     * 3. 渲染房间选择下拉框
     * 4. 应用初始猫咪信息到 UI
     * 5. 绑定投喂按钮和房间切换事件
     * 6. 启动在线人数和环境数据模拟定时器
     * @returns {Promise<void>}
     */
    async init() {
        const roomSelect = document.getElementById('roomSelect');
        const feedBtn = document.getElementById('feedBtn');
        if (!roomSelect || !feedBtn) return;
        /* 从 URL 查询参数中获取初始猫咪 ID */
        const urlParams = new URLSearchParams(window.location.search);
        const catId = parseInt(urlParams.get('cat') || '', 10);
        if (!isNaN(catId) && catId > 0) this.currentCatId = catId;
        await this.loadData();
        this.renderRoomSelect(roomSelect);
        const initialCat = this.getCatById(this.currentCatId) || this.cats[0];
        if (initialCat) { this.currentCatId = initialCat.id; roomSelect.value = String(this.currentCatId); this.currentCat = initialCat; this.applyCat(initialCat); }
        /* 绑定投喂按钮点击事件 */
        feedBtn.addEventListener('click', () => this.feed());
        /* 绑定房间切换下拉框变更事件 */
        roomSelect.addEventListener('change', e => { const newId = parseInt(e.target.value, 10); if (!isNaN(newId) && newId > 0 && newId !== this.currentCatId) { this.currentCatId = newId; this.loadCurrentCat(); } });
        this.startTimers();
    },

    /**
     * 加载猫咪列表和全局统计数据
     * 并行请求 /cats 和 /stats 接口，成功后更新 totalFeeds 显示
     * @returns {Promise<void>}
     */
    async loadData() { try { const [cats, stats] = await Promise.all([API.get('/cats'), API.get('/stats')]); this.cats = Array.isArray(cats) ? cats : []; this.stats = stats || {}; const el = document.getElementById('totalFeeds'); if (el && this.stats.total_feeds !== undefined) el.textContent = formatNumber(this.stats.total_feeds); } catch {} },

    /**
     * 渲染房间选择下拉框的选项列表
     * @param {HTMLElement} selectEl - <select> DOM 元素
     */
    renderRoomSelect(selectEl) { selectEl.innerHTML = this.cats.map(c => '<option value="' + c.id + '">🐱 ' + CatUI.esc(c.name) + ' · ' + CatUI.esc(c.location) + '</option>').join(''); },

    /**
     * 重新加载当前猫咪信息（切换猫咪后调用）
     * 刷新数据 → 应用猫咪信息 → 加载投喂日志 → 同步下拉框选中状态
     * @returns {Promise<void>}
     */
    async loadCurrentCat() { await this.loadData(); const cat = this.getCatById(this.currentCatId) || this.cats[0]; if (cat) { this.currentCat = cat; this.currentCatId = cat.id; this.applyCat(cat); this.loadFeedLogs(cat.id); const select = document.getElementById('roomSelect'); if (select) select.value = String(cat.id); } },

    /**
     * 将猫咪信息应用到直播间 UI
     * 更新 emoji、标题、位置、今日投喂次数
     * 目标 DOM：#liveCatEmoji, #liveCatTitle, #liveCatLocation, #todayFeeds
     * @param {Object} cat - 猫咪数据对象
     */
    applyCat(cat) {
        const liveCatEmoji = document.getElementById('liveCatEmoji');
        const liveCatTitle = document.getElementById('liveCatTitle');
        const liveCatLocation = document.getElementById('liveCatLocation');
        if (liveCatEmoji) liveCatEmoji.textContent = CatUI.getEmoji(cat.color);
        if (liveCatTitle) liveCatTitle.textContent = CatUI.esc(cat.name) + '的直播间';
        if (liveCatLocation) liveCatLocation.textContent = '📍 ' + CatUI.esc(cat.location);
        const todayFeeds = document.getElementById('todayFeeds');
        if (todayFeeds && typeof cat.feed_count === 'number') todayFeeds.textContent = formatNumber(cat.feed_count);
    },

    /**
     * 执行投喂操作
     * 1. 禁用按钮并显示加载状态
     * 2. 根据是否游客调用不同接口（/feed-as-guest 或 /feed）
     * 3. 成功后触发粒子动画、更新投喂次数、刷新日志
     * 4. 失败时提示错误，需要登录时弹出登录框
     * 5. 最终恢复按钮状态
     * 目标 DOM：#feedBtn, #todayFeeds
     * @returns {Promise<void>}
     */
    async feed() {
        const feedBtn = document.getElementById('feedBtn');
        if (!feedBtn || feedBtn.disabled) return;
        const isGuest = Auth.isGuest;
        feedBtn.disabled = true;
        const orig = feedBtn.innerHTML;
        feedBtn.innerHTML = '<span class="button-loading"><span class="spinner-small"></span><span>投喂中...</span></span>';
        try {
            let result;
            /* 游客和登录用户调用不同接口 */
            if (isGuest) result = await API.post('/feed-as-guest', { cat_id: this.currentCatId, guest_id: Auth.getGuestId() });
            else result = await API.post('/feed', { cat_id: this.currentCatId }, true);
            if (result.success) {
                Toast.success(result.message);
                triggerFeedParticles();
                /* 更新投喂次数显示 */
                if (typeof result.feed_count === 'number') {
                    const el = document.getElementById('todayFeeds'); if (el) el.textContent = formatNumber(result.feed_count);
                    const cat = this.getCatById(this.currentCatId); if (cat) cat.feed_count = result.feed_count;
                }
                this.loadFeedLogs(this.currentCatId);
            } else { Toast.error(result.message || '投喂失败'); if (result.need_login) Auth.showLogin(); }
        } catch { Toast.error('投喂失败，请检查网络连接'); }
        finally { const btn = document.getElementById('feedBtn'); if (btn) { btn.disabled = false; btn.innerHTML = orig; } }
    },

    /**
     * 加载并渲染指定猫咪的投喂日志
     * 调用 /feed-logs 接口获取最近 10 条记录
     * 目标 DOM：#feedLogs
     * @param {number} catId - 猫咪 ID
     * @returns {Promise<void>}
     */
    async loadFeedLogs(catId) {
        try {
            const logs = await API.get('/feed-logs?cat_id=' + catId + '&limit=10');
            const el = document.getElementById('feedLogs');
            if (el && logs.length > 0) el.innerHTML = logs.map(l => '<div class="log-item"><span class="log-time">' + formatTime(l.time) + '</span><span class="log-user">' + CatUI.esc(l.user_name || '匿名') + '</span><span class="log-action">投喂了' + CatUI.esc(this.getCatNameById(l.cat_id) || '猫咪') + '</span></div>').join('');
            else if (el) el.innerHTML = '<div class="log-empty">暂无投喂记录</div>';
        } catch {}
    },

    /**
     * 根据 ID 查找猫咪对象
     * @param {number} id - 猫咪 ID
     * @returns {Object|undefined} 匹配的猫咪对象
     */
    getCatById(id) { return this.cats.find(c => c.id === id); },

    /**
     * 根据 ID 获取猫咪名称
     * @param {number} id - 猫咪 ID
     * @returns {string} 猫咪名称，未找到返回空字符串
     */
    getCatNameById(id) { const cat = this.getCatById(id); return cat ? cat.name : ''; },

    /**
     * 启动模拟数据定时器
     * - 每 5 秒微调在线观众数（±10 随机波动，最低 100）
     * - 每 10 秒微调温度和湿度（模拟数据）
     * 目标 DOM：#onlineViewers, #temperature, #humidity
     */
    startTimers() {
        this.viewerTimer = setInterval(() => { const el = document.getElementById('onlineViewers'); if (el) { let v = parseInt(el.textContent.replace(/[^0-9]/g,'')) || 1234; v = Math.max(100, v + Math.floor(Math.random() * 21) - 10); el.textContent = formatNumber(v); } }, 5000);
        this.envTimer = setInterval(() => { const t = document.getElementById('temperature'), h = document.getElementById('humidity'); if (t) t.textContent = (20 + Math.random() * 4 - 2).toFixed(1) + '°C'; if (h) h.textContent = Math.floor(55 + Math.random() * 10 - 5) + '%'; }, 10000);
    }
};

// ============================================
// 分享功能模块
// ============================================

/**
 * ShareUI 模块 - 猫咪分享弹窗功能
 * 管理分享弹窗的创建、展示和关闭，支持微信/微博/QQ/复制链接
 * 目标 DOM：#shareModal（动态注入到 body）
 * @constant {Object}
 */
const ShareUI = {
    /** @type {Object|null} 当前分享的猫咪数据 */
    currentCat: null,
    /** @type {HTMLElement|null} 分享弹窗 DOM 元素 */
    modal: null,

    /** 初始化：创建分享弹窗 HTML 并绑定事件 */
    init() { this._createModal(); this._bindEvents(); },

    /**
     * 创建分享弹窗 HTML 并注入到页面
     * 包含猫咪预览区、社交平台分享按钮、分享链接输入框
     * 目标 DOM：注入到 body 末尾，ID 为 shareModal
     * @private
     */
    _createModal() {
        if (document.getElementById('shareModal')) return;
        document.body.insertAdjacentHTML('beforeend', '<div class="share-modal" id="shareModal"><div class="share-modal-content"><button class="share-modal-close" onclick="ShareUI.close()">✕</button><div class="share-modal-header"><h3>分享猫咪档案</h3><p>邀请更多人关注这只可爱的猫咪</p></div><div class="share-cat-preview"><div class="share-cat-avatar" id="shareCatAvatar">🐱</div><div class="share-cat-name" id="shareCatName"></div><div class="share-cat-nickname" id="shareCatNickname"></div><div class="share-cat-info"><span id="shareCatGender"></span><span id="shareCatAge"></span><span id="shareCatColor"></span></div></div><div class="share-options"><div class="share-option" onclick="shareTo(\'wechat\')"><span class="share-option-icon">💚</span><span class="share-option-label">微信</span></div><div class="share-option" onclick="shareTo(\'weibo\')"><span class="share-option-icon">🔴</span><span class="share-option-label">微博</span></div><div class="share-option" onclick="shareTo(\'qq\')"><span class="share-option-icon">🐧</span><span class="share-option-label">QQ</span></div><div class="share-option" onclick="shareTo(\'copy\')"><span class="share-option-icon">📋</span><span class="share-option-label">复制链接</span></div></div><div class="share-link-section"><label class="share-link-label">分享链接</label><div class="share-link-container"><input type="text" class="share-link-input" id="shareLinkInput" readonly><button class="share-link-btn" onclick="shareTo(\'copy\')">复制</button></div></div></div></div>');
        this.modal = document.getElementById('shareModal');
    },

    /**
     * 绑定弹窗点击事件
     * 点击弹窗蒙层（背景）时关闭弹窗
     * @private
     */
    _bindEvents() { if (!this.modal) return; this.modal.addEventListener('click', e => { if (e.target === this.modal) this.close(); }); },

    /**
     * 打开分享弹窗并加载猫咪信息
     * 调用 /cat/{id} 接口获取猫咪详情，填充到弹窗预览区
     * 目标 DOM：#shareCatAvatar, #shareCatName, #shareCatNickname, #shareCatGender, #shareCatAge, #shareCatColor, #shareLinkInput
     * @param {number} catId - 要分享的猫咪 ID
     * @returns {Promise<void>}
     */
    async shareCat(catId) {
        try {
            const cat = await API.get('/cat/' + catId);
            this.currentCat = cat;
            document.getElementById('shareCatAvatar').textContent = CatUI.getEmoji(cat.color);
            document.getElementById('shareCatName').textContent = CatUI.esc(cat.name);
            document.getElementById('shareCatNickname').textContent = '"' + CatUI.esc(cat.nickname || '') + '"';
            document.getElementById('shareCatGender').textContent = cat.gender === 'male' ? '♂ 公' : '♀ 母';
            document.getElementById('shareCatAge').textContent = CatUI.esc(cat.age);
            document.getElementById('shareCatColor').textContent = CatUI.esc(cat.color);
            /* 生成分享链接 */
            document.getElementById('shareLinkInput').value = window.location.origin + '/cats?cat=' + catId;
            this.modal?.classList.add('show');
            document.body.style.overflow = 'hidden';
        } catch { Toast.error('加载猫咪信息失败'); }
    },

    /** 关闭分享弹窗，恢复页面滚动 */
    close() { this.modal?.classList.remove('show'); document.body.style.overflow = ''; this.currentCat = null; }
};

// ============================================
// 猫咪档案页模块
// ============================================

/**
 * CatsPage 模块 - 猫咪档案列表页面
 * 负责猫咪档案页的筛选、搜索、卡片渲染和积分排行榜
 * 目标 DOM：#catsGrid, #leaderboardList, #catsSearch, .filter-btn
 * @constant {Object}
 */
const CatsPage = {
    /** @type {string} 当前筛选条件：'all' | 'adoption' | 'neutered' */
    currentFilter: 'all',
    /** @type {string} 搜索关键词 */
    searchQuery: '',
    /** @type {Array} 猫咪列表数据 */
    cats: [],

    /**
     * 猫咪档案页初始化
     * 加载猫咪数据 → 渲染排行榜 → 渲染卡片列表 → 绑定事件
     * @returns {Promise<void>}
     */
    async init() { this.cats = await API.get('/cats'); this.renderLeaderboard(); this.render(); this.bindEvents(); },

    /**
     * 渲染积分排行榜（前 10 名）
     * 按积分降序排列，前三名显示奖牌 emoji（🥇🥈🥉）
     * 点击条目可打开猫咪详情弹窗
     * 目标 DOM：#leaderboardList
     */
    renderLeaderboard() {
        const list = document.getElementById('leaderboardList');
        if (!list) return;
        const sorted = [...this.cats].sort((a, b) => (b.points || 0) - (a.points || 0)).slice(0, 10);
        if (sorted.length === 0) { list.innerHTML = '<div class="empty-state">暂无积分数据</div>'; return; }
        const medals = ['🥇', '🥈', '🥉'];
        list.innerHTML = sorted.map((cat, i) => '<div class="leaderboard-item' + (i < 3 ? ' top-3' : '') + '" onclick="showCatDetailPopup(' + cat.id + ')" style="cursor:pointer"><span class="leaderboard-rank">' + (i < 3 ? medals[i] : (i + 1)) + '</span><span class="leaderboard-avatar" style="display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:50%;background:' + CatUI.getColor(cat.id) + ';color:#fff;font-size:1.1rem;">' + CatUI.getEmojiById(cat.id) + '</span><span class="leaderboard-name">' + CatUI.esc(cat.name) + '</span><span class="leaderboard-score">' + formatNumber(cat.points || 0) + ' 分</span></div>').join('');
    },

    /**
     * 渲染猫咪卡片网格
     * 筛选逻辑：
     * - currentFilter='all' → 显示全部
     * - currentFilter='adoption' → 仅显示 adoption_ready 为 true 的
     * - currentFilter='neutered' → 仅显示 neutered 为 true 的
     * 搜索逻辑：在 name、nickname、location、color 中模糊匹配关键词
     * 目标 DOM：#catsGrid
     */
    render() {
        const grid = document.getElementById('catsGrid');
        if (!grid) return;
        const filtered = this.cats.filter(cat => {
            const matchesFilter = this.currentFilter === 'all' || (this.currentFilter === 'adoption' && cat.adoption_ready) || (this.currentFilter === 'neutered' && cat.neutered);
            const searchAttrs = [cat.name, cat.nickname, cat.location, cat.color].filter(Boolean).join(' ').toLowerCase();
            return matchesFilter && (!this.searchQuery || searchAttrs.includes(this.searchQuery.toLowerCase()));
        });
        if (filtered.length === 0) { grid.innerHTML = '<div class="empty-state"><div class="empty-icon">🐱</div><p class="empty-text">没有找到匹配的猫咪</p><button class="empty-btn" onclick="CatsPage.resetFilter()">重置筛选</button></div>'; return; }
        grid.innerHTML = filtered.map(cat => '</div>' + CatUI.getEmoji(cat.color) + '</div><div class="cat-card-info"><h3 class="cat-name">' + CatUI.esc(cat.name) + '</h3><p class="cat-nickname">"' + CatUI.esc(cat.nickname || '') + '"</p><div class="cat-tags"><span class="tag">' + (cat.gender === 'male' ? '♂ 公' : '♀ 母') + ' ' + CatUI.esc(cat.age) + '</span><span class="tag">' + CatUI.esc(cat.color) + '</span>' + (cat.neutered ? '<span class="tag tag-success">已绝育</span>' : '') + '</div><p class="cat-card-location">📍 ' + CatUI.esc(cat.location) + '</p></div><div class="cat-card-actions"><button class="btn btn-primary btn-sm" onclick="showCatDetailPopup(' + cat.id + ')">查看详情</button><button class="btn btn-secondary btn-sm" onclick="ShareUI.shareCat(' + cat.id + ')">📤</button></div>')).join(''));
    },

    /**
     * 绑定档案页事件监听器
     * 1. 筛选按钮点击 → 切换 active 样式 → 更新筛选条件 → 重新渲染
     * 2. 搜索框输入 → 防抖 300ms → 更新搜索词 → 重新渲染
     * 目标 DOM：.filter-btn, #catsSearch
     */
    bindEvents() {
        document.querySelectorAll('.filter-btn').forEach(btn => btn.addEventListener('click', () => { document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); this.currentFilter = btn.dataset.filter; this.render(); }));
        const searchInput = document.getElementById('catsSearch');
        if (searchInput) searchInput.addEventListener('input', debounce(e => { this.searchQuery = e.target.value; this.render(); }, 300));
    },

    /**
     * 重置筛选条件和搜索关键词
     * 恢复所有筛选按钮为未选中状态，激活"全部"按钮，清空搜索框
     * 目标 DOM：.filter-btn, #catsSearch
     */
    resetFilter() { this.currentFilter = 'all'; this.searchQuery = ''; document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active')); document.querySelector('.filter-btn[data-filter="all"]')?.classList.add('active'); const si = document.getElementById('catsSearch'); if (si) si.value = ''; this.render(); }
};

// ============================================
// 领养页面模块
// ============================================

/**
 * AdoptPage 模块 - 猫咪领养页面
 * 管理可领养猫咪列表展示、领养申请表单和提交
 * 目标 DOM：#adoptCatsGrid, #formSection, #adoptForm, #cancelBtn, #formClose
 * @constant {Object}
 */
const AdoptPage = {
    /** @type {number|null} 当前申请领养的猫咪 ID */
    selectedCatId: null,

    /**
     * 领养页面初始化
     * 1. 加载猫咪列表，筛选出可领养的猫咪
     * 2. 渲染可领养猫咪卡片
     * 3. 绑定表单事件
     * 4. 检查 URL 参数 ?cat=X，自动打开对应猫咪的申请表单
     * @returns {Promise<void>}
     */
    async init() { const cats = await API.get('/cats'); const adoptable = cats.filter(c => c.adoption_ready); this.renderCats(adoptable); this.bindEvents(); const urlParams = new URLSearchParams(window.location.search); const catId = parseInt(urlParams.get('cat') || '', 10); if (!isNaN(catId) && catId > 0) { const cat = cats.find(c => c.id === catId); if (cat && cat.adoption_ready) this.openForm(catId); } },

    /**
     * 渲染可领养猫咪卡片列表
     * 每张卡片显示猫咪头像、名称、昵称、标签（性别/年龄/花色/绝育状态）、描述和申请按钮
     * 目标 DOM：#adoptCatsGrid
     * @param {Array<Object>} cats - 可领养猫咪数组
     */
    renderCats(cats) { const grid = document.getElementById('adoptCatsGrid'); if (!grid) return; if (cats.length === 0) { grid.innerHTML = '<div class="empty-state"><div class="empty-icon">🏠</div><p class="empty-text">暂无可领养的猫咪</p></div>'; return; } grid.innerHTML = cats.map(c => '<div class="cat-card adopt-card"><div class="cat-card-image" style="background:' + CatUI.getBg(c.color) + '"><div class="cat-avatar large">' + CatUI.getEmoji(c.color) + '</div><div class="cat-status-badge" style="background:var(--success);color:#fff;position:absolute;top:10px;right:10px;">🏠 可领养</div></div><div class="cat-card-info"><h3 class="cat-name">' + CatUI.esc(c.name) + '</h3><p class="cat-nickname">"' + CatUI.esc(c.nickname || '') + '"</p><div class="cat-tags"><span class="tag">' + (c.gender === 'male' ? '♂ 公' : '♀ 母') + ' ' + CatUI.esc(c.age) + '</span><span class="tag">' + CatUI.esc(c.color) + '</span>' + (c.neutered ? '<span class="tag tag-success">已绝育</span>' : '') + '</div><p class="cat-description">' + CatUI.esc(c.description || '') + '</p><button class="adopt-apply-btn" onclick="AdoptPage.openForm(' + c.id + ')">🏠 申请领养</button></div></div>').join(''); },

    /**
     * 打开领养申请表单
     * 记录选中的猫咪 ID，显示表单区域，禁止页面滚动
     * 目标 DOM：#formSection
     * @param {number} catId - 要申请的猫咪 ID
     */
    openForm(catId) { this.selectedCatId = catId; const fs = document.getElementById('formSection'); if (fs) { fs.classList.add('show'); document.body.style.overflow = 'hidden'; } },

    /**
     * 关闭领养申请表单
     * 隐藏表单区域，恢复页面滚动，重置表单内容
     * 目标 DOM：#formSection, #adoptForm
     */
    closeForm() { const fs = document.getElementById('formSection'); if (fs) { fs.classList.remove('show'); document.body.style.overflow = ''; } document.getElementById('adoptForm')?.reset(); this.selectedCatId = null; },

    /**
     * 绑定领养表单相关事件
     * 1. 表单提交 → handleSubmit
     * 2. 取消按钮 → closeForm
     * 3. 关闭按钮 → closeForm
     * 目标 DOM：#adoptForm, #cancelBtn, #formClose
     */
    bindEvents() { const form = document.getElementById('adoptForm'); if (form) form.addEventListener('submit', e => this.handleSubmit(e)); document.getElementById('cancelBtn')?.addEventListener('click', () => this.closeForm()); document.getElementById('formClose')?.addEventListener('click', () => this.closeForm()); },
    /**
     * 处理领养申请表单提交
     * 1. 阻止默认提交行为，检查按钮是否已禁用（防重复提交）
     * 2. 收集表单字段：猫咪 ID、申请人姓名/年龄/电话/邮箱/住房类型/住房面积/家人同意/养宠经验/曾养宠物/领养动机
     * 3. 校验必填字段（姓名、电话、领养动机），不通过则 Toast 提示
     * 4. 禁用按钮并显示加载状态，POST /adopt/apply
     * 5. 成功 → Toast 提示并关闭表单；失败 → Toast 错误信息
     * 6. finally 中恢复按钮状态
     * 目标 DOM：#applicantName, #applicantAge, #applicantPhone, #applicantEmail,
     *           #housingType, #housingSize, #familyAgree, #petExperience,
     *           #previousPets, #adoptionReason
     * @param {Event} e - 表单 submit 事件
     * @returns {Promise<void>}
     */
    async handleSubmit(e) { e.preventDefault(); const submitBtn = e.target.querySelector('.btn-submit'); if (!submitBtn || submitBtn.disabled) return; const fd = { cat_id: this.selectedCatId, applicant: { name: document.getElementById('applicantName').value.trim(), age: parseInt(document.getElementById('applicantAge').value, 10), phone: document.getElementById('applicantPhone').value.trim(), email: document.getElementById('applicantEmail').value.trim(), housingType: document.getElementById('housingType').value, housingSize: document.getElementById('housingSize').value, familyAgree: document.getElementById('familyAgree').value, petExperience: document.getElementById('petExperience').value, previousPets: document.getElementById('previousPets').value.trim(), adoptionReason: document.getElementById('adoptionReason').value.trim() } }; if (!fd.applicant.name || !fd.applicant.phone || !fd.applicant.adoptionReason) { Toast.warning('请填写姓名、电话与领养动机'); return; } submitBtn.disabled = true; submitBtn.innerHTML = '<span class="button-loading"><span class="spinner-small"></span><span>提交中...</span></span>'; try { const result = await API.post('/adopt/apply', fd); if (result.success) { Toast.success('申请已提交，我们会尽快联系您！', 5000); this.closeForm(); } else Toast.error(result.message || '提交失败'); } catch { Toast.error('网络异常'); } finally { submitBtn.disabled = false; submitBtn.innerHTML = '📮 提交申请'; } }
};

// ============================================
// 统计数据模块
// ============================================
/**
 * StatsDashboard 模块 - 统计数据看板
 * 展示猫咪总数、累计投喂、累计观看、可领养数量等统计卡片
 * 以及投喂趋势折线图和猫咪积分排行榜柱状图（依赖 Chart.js）
 * 目标 DOM：#statsGrid, #feedChart, #pointsChart
 * @constant {Object}
 */
const StatsDashboard = {
    /** @type {Object} Chart.js 图表实例缓存，key 为图表名称 */
    charts: {},

    /**
     * 初始化统计看板
     * 依次渲染统计卡片和图表
     */
    init() { this.renderStatsCards(); this.renderCharts(); },

    /**
     * 渲染统计卡片
     * 从 GET /stats 获取数据，渲染 4 张卡片：猫咪总数、累计投喂、累计观看、可领养数
     * 目标 DOM：#statsGrid
     * @returns {Promise<void>}
     */
    async renderStatsCards() { const grid = document.getElementById('statsGrid'); if (!grid) return; try { const stats = await API.get('/stats'); grid.innerHTML = '<div class="stat-card primary"><span class="stat-icon">🐱</span><div class="stat-info"><span class="stat-value">' + formatNumber(stats.total_cats || 0) + '</span><span class="stat-label">猫咪总数</span></div></div><div class="stat-card success"><span class="stat-icon">❤️</span><div class="stat-info"><span class="stat-value">' + formatNumber(stats.total_feeds || 0) + '</span><span class="stat-label">累计投喂</span></div></div><div class="stat-card warning"><span class="stat-icon">👁️</span><div class="stat-info"><span class="stat-value">' + formatNumber(stats.total_views || 0) + '</span><span class="stat-label">累计观看</span></div></div><div class="stat-card info"><span class="stat-icon">🏠</span><div class="stat-info"><span class="stat-value">' + formatNumber(stats.adoptable_cats || 0) + '</span><span class="stat-label">可领养</span></div></div>'; } catch {} },

    /**
     * 渲染图表
     * 1. 从 GET /stats/feed-history 获取投喂历史数据，渲染折线图
     * 2. 从 GET /stats/points-history 获取积分历史数据，渲染柱状图
     * 3. 若 API 失败或 Chart.js 未加载，降级使用模拟数据
     * 目标 DOM：#feedChart, #pointsChart
     * @returns {Promise<void>}
     */
    async renderCharts() { try { const feedData = await API.get('/stats/feed-history'); const pointsData = await API.get('/stats/points-history'); const fCanvas = document.getElementById('feedChart'), pCanvas = document.getElementById('pointsChart'); if (fCanvas && typeof Chart !== 'undefined') this._renderFeedChart(fCanvas, feedData); if (pCanvas && typeof Chart !== 'undefined') this._renderPointsChart(pCanvas, pointsData); } catch { this._mockCharts(); } },

    /**
     * 渲染投喂趋势折线图
     * 先销毁已有实例避免重复，再使用 Chart.js 创建新折线图
     * 若 data 为空则使用模拟数据（周一~周日）
     * @param {HTMLCanvasElement} canvas - 画布元素
     * @param {Object} data - 包含 labels（日期标签）和 values（投喂次数）的数据对象
     */
    _renderFeedChart(canvas, data) { if (this.charts.feedChart) this.charts.feedChart.destroy(); const labels = data?.labels || ['周一', '周二', '周三', '周四', '周五', '周六', '周日']; const values = data?.values || [120, 150, 180, 140, 200, 250, 220]; this.charts.feedChart = new Chart(canvas.getContext('2d'), { type: 'line', data: { labels, datasets: [{ label: '投喂次数', data: values, borderColor: '#d88da3', backgroundColor: 'rgba(216,141,163,0.1)', borderWidth: 3, fill: true, tension: 0.4 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } } }); },

    /**
     * 渲染猫咪积分排行榜柱状图
     * 先销毁已有实例避免重复，再使用 Chart.js 创建新柱状图
     * 若 data 为空则使用模拟数据（咪咪/小黑/雪球/大橘）
     * @param {HTMLCanvasElement} canvas - 画布元素
     * @param {Object} data - 包含 labels（猫咪名称）和 values（积分数）的数据对象
     */
    _renderPointsChart(canvas, data) { if (this.charts.pointsChart) this.charts.pointsChart.destroy(); const labels = data?.labels || ['咪咪', '小黑', '雪球', '大橘']; const values = data?.values || [193, 90, 237, 314]; this.charts.pointsChart = new Chart(canvas.getContext('2d'), { type: 'bar', data: { labels, datasets: [{ data: values, backgroundColor: ['rgba(216,141,163,0.8)', 'rgba(135,206,250,0.8)', 'rgba(255,215,0,0.8)', 'rgba(139,225,219,0.8)'], borderRadius: 8 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } } }); },

    /**
     * 降级渲染图表（使用模拟数据）
     * 当 API 请求失败时，使用硬编码的模拟数据渲染折线图和柱状图
     * 目标 DOM：#feedChart, #pointsChart
     */
    _mockCharts() { const fCanvas = document.getElementById('feedChart'), pCanvas = document.getElementById('pointsChart'); if (fCanvas && typeof Chart !== 'undefined') this._renderFeedChart(fCanvas, { labels: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'], values: [120, 150, 180, 140, 200, 250, 220] }); if (pCanvas && typeof Chart !== 'undefined') this._renderPointsChart(pCanvas, { labels: ['咪咪', '小黑', '雪球', '大橘'], values: [193, 90, 237, 314] }); }
};

// ============================================
// 通知系统模块
// ============================================
/**
 * NotificationCenter 模块 - 通知中心
 * 管理系统通知和活动动态的展示、未读计数和轮询刷新
 * 目标 DOM：#notificationList, #notificationBadge
 * @constant {Object}
 */
const NotificationCenter = {
    /** @type {Array<Object>} 通知列表 */
    notifications: [],
    /** @type {number} 未读通知数量 */
    unreadCount: 0,
    /** @type {string} 当前筛选标签：'all' | 'system' | 'activity' */
    currentTab: 'all',

    /**
     * 初始化通知中心
     * 1. 渲染通知列表
     * 2. 启动 30 秒轮询检查新通知
     */
    init() { this.renderNotifications(); this.startPolling(); },

    /**
     * 渲染通知列表
     * 从 GET /notifications 获取通知数据，失败时使用模拟数据
     * 获取后更新未读计数并渲染列表
     * 目标 DOM：#notificationList
     * @returns {Promise<void>}
     */
    async renderNotifications() { const list = document.getElementById('notificationList'); if (!list) return; try { this.notifications = await API.get('/notifications'); } catch { this.notifications = this._mock(); } this.updateUnreadCount(); this.displayN(); },

    /**
     * 生成模拟通知数据（API 失败时的降级方案）
     * 模拟数据：包含一条活动通知和一条系统通知
     * @returns {Array<Object>} 模拟通知数组
     */
    _mock() { return [{ id: 1, type: 'activity', title: '新投喂记录', message: '用户"爱猫人"刚刚给小黑投喂了美食', time: new Date(Date.now() - 300000).toISOString(), unread: true }, { id: 2, type: 'system', title: '系统通知', message: '猫咪档案系统已升级', time: new Date(Date.now() - 7200000).toISOString(), unread: false }]; },

    /**
     * 更新未读通知计数
     * 统计 notifications 中 unread 为 true 的条数，更新 #notificationBadge 的文本和显示状态
     * 目标 DOM：#notificationBadge
     */
    updateUnreadCount() { this.unreadCount = this.notifications.filter(n => n.unread).length; const badge = document.getElementById('notificationBadge'); if (badge) { badge.textContent = this.unreadCount > 0 ? String(this.unreadCount) : ''; badge.style.display = this.unreadCount > 0 ? 'flex' : 'none'; } },

    /**
     * 渲染通知列表到 DOM
     * 根据 currentTab 筛选通知（'all' 显示全部，否则按 type 筛选）
     * 每条通知显示图标（system→⚙️, activity→❤️, 其他→ℹ️）、标题、内容和时间
     * 未读通知添加 'unread' 样式类
     * 目标 DOM：#notificationList
     */
    displayN() { const list = document.getElementById('notificationList'); if (!list) return; const filtered = this.currentTab === 'all' ? this.notifications : this.notifications.filter(n => n.type === this.currentTab); list.innerHTML = filtered.map(n => '<div class="notification-item' + (n.unread ? ' unread' : '') + '"><div class="notification-icon">' + (n.type === 'system' ? '⚙️' : n.type === 'activity' ? '❤️' : 'ℹ️') + '</div><div class="notification-content"><div class="notification-title">' + CatUI.esc(n.title) + '</div><div class="notification-message">' + CatUI.esc(n.message) + '</div><div class="notification-time">' + formatTime(n.time) + '</div></div></div>').join(''); },

    /**
     * 请求浏览器通知权限
     * 若浏览器支持 Notification API 且用户尚未做出选择（permission === 'default'），则弹出授权请求
     */
    requestPermission() { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); },

    /**
     * 启动轮询检查新通知
     * 每 30 秒调用 GET /notifications/unread-count，若未读数增加则重新拉取完整通知列表并更新计数
     */
    startPolling() { setInterval(async () => { try { const newN = await API.get('/notifications/unread-count'); if (newN.count > this.unreadCount) { this.notifications = await API.get('/notifications'); this.updateUnreadCount(); } } catch {} }, 30000); },

    /**
     * 刷新通知显示（displayN 的公开别名）
     * 供外部模块（如 togglePanel）调用以刷新通知列表
     */
    displayNotifications() { this.displayN(); }
};

// ============================================
// 【增强1】AI实时验证指示器
// ============================================
/**
 * AIVerifier 模块 - AI 实时验证指示器
 * 模拟 AI 猫咪检测功能，周期性轮询检测状态并更新指示器徽标
 * 目标 DOM：#aiVerifyBadge
 * @constant {Object}
 */
const AIVerifier = {
    /** @type {boolean} 是否处于活跃检测状态 */
    active: true,
    /** @type {number|null} 轮询定时器 ID */
    _timer: null,

    /**
     * 启动 AI 检测
     * 设置 active 为 true，更新徽标为"已识别"，开始轮询
     */
    start() { this.active = true; this._updateBadge(true); this._pollDetection(); },

    /**
     * 停止 AI 检测
     * 设置 active 为 false，更新徽标为"未检测到"，清除定时器
     */
    stop() { this.active = false; this._updateBadge(false); if (this._timer) clearTimeout(this._timer); },

    /**
     * 更新 AI 验证徽标显示
     * 根据 detected 参数切换徽标的样式和内容
     * - detected=true：显示绿色脉冲动画 + "AI已识别: 有猫"
     * - detected=false：显示灰色 + "AI未检测到猫咪"
     * 目标 DOM：#aiVerifyBadge
     * @param {boolean} detected - 是否检测到猫咪
     */
    _updateBadge(detected) {
        const badge = document.getElementById('aiVerifyBadge');
        if (!badge) return;
        badge.className = 'ai-verify-badge' + (detected ? '' : ' off');
        badge.innerHTML = detected ? '<span class="ai-verify-pulse"></span>AI已识别: 有猫' : '<span>AI未检测到猫咪</span>';
    },

    /**
     * 轮询 AI 检测状态
     * 每 3 秒模拟一次检测结果（90% 概率检测到猫），递归调用自身
     * 若 active 为 false 则停止轮询
     */
    _pollDetection() { if (!this.active) return; this._updateBadge(Math.random() < 0.9); this._timer = setTimeout(() => this._pollDetection(), 3000); }
};

// ============================================
// 【增强2】投喂粒子动画
// ============================================
/**
 * 触发投喂粒子动画效果
 * 在直播间摄像头区域（.live-camera）生成 12 个随机食物/爱心 emoji 粒子
 * 每个粒子具有随机的水平偏移（--tx）、垂直偏移（--ty）和延迟（--delay）
 * 粒子在 1 秒后自动移除
 * 目标 DOM：.live-camera
 */
function triggerFeedParticles() {
    const container = document.querySelector('.live-camera');
    if (!container) return;
    /* 模拟数据：粒子 emoji 池 */
    const particles = ['🐟', '🍗', '🦴', '🐾', '❤️', '✨', '🍖', '🥫'];
    for (let i = 0; i < 12; i++) {
        const p = document.createElement('span');
        p.className = 'feed-particle';
        p.textContent = particles[Math.floor(Math.random() * particles.length)];
        p.style.setProperty('--tx', ((Math.random() - 0.5) * 160) + 'px');
        p.style.setProperty('--ty', -(Math.random() * 100 + 80) + 'px');
        p.style.setProperty('--delay', (Math.random() * 0.2) + 's');
        container.appendChild(p);
        setTimeout(() => p.remove(), 1000);
    }
}

// ============================================
// 【增强3】猫咪详情弹窗
// ============================================
/**
 * 显示猫咪详情弹窗
 * 从 window._allCats 和 LiveRoom.cats 合并查找猫咪，动态创建模态弹窗
 * 弹窗内容包含：
 *   1. 头部：头像、名称、状态徽标（待领养/已绝育/未绝育）、昵称、位置
 *   2. 数据卡片：健康指数（模拟）、心情指数（模拟）、本周投喂次数
 *   3. 标签页：投喂记录（模拟）、健康档案、猫咪日记
 *   4. 操作按钮：远程投喂、投喂记录、分享、举报
 * 点击蒙层关闭弹窗
 * @param {number} catId - 猫咪 ID
 */
function showCatDetailPopup(catId) {
    const allCats = [...(window._allCats || []), ...(LiveRoom.cats || [])];
    const cat = allCats.find(c => c.id === catId);
    if (!cat) { Toast.show('猫咪信息未找到', 2000, 'error'); return; }

    const modal = document.createElement('div');
    modal.className = 'cat-detail-modal show';
    modal.id = 'catDetailPopup_' + catId;

    const color = CatUI.getColor(catId);
    const emoji = CatUI.getEmojiById(catId);
    const healthScore = Math.floor(85 + Math.random() * 15);
    const moodScore = Math.floor(60 + Math.random() * 40);
    const moodEmoji = moodScore > 85 ? '😻' : moodScore > 65 ? '😺' : moodScore > 40 ? '😼' : '🙀';
    const moodLabel = moodScore > 85 ? '非常开心' : moodScore > 65 ? '心情不错' : moodScore > 40 ? '有点忧郁' : '状态不佳';
    const feedCount = cat.feed_count || Math.floor(Math.random() * 200 + 50);

    const statusBadgeHtml = cat.status === 'adoption'
        ? '<span class="cat-status-badge adoption">待领养</span>'
        : cat.is_neutered ? '<span class="cat-status-badge" style="background:#74b9ff;color:#fff;">已绝育</span>'
        : '<span class="cat-status-badge" style="background:#d88da3;color:#fff;">未绝育</span>';

    // 模拟投喂记录
    const feedNames = ['爱心云养人', '张女士', '王先生', '爱猫小分队', '社区居民李', '匿名守护者'];
    const feedTimes = ['3分钟前', '28分钟前', '1小时前', '2小时前', '5小时前', '昨天 20:15'];
    let feedLogsHtml = '';
    for (let i = 0; i < 6; i++) {
        feedLogsHtml += '<div class="detail-diary-entry"><div style="display:flex;justify-content:space-between;"><span style="font-weight:600;">' + feedNames[Math.floor(Math.random() * feedNames.length)] + '</span><span style="font-size:0.75rem;color:var(--text-muted);">' + feedTimes[i] + '</span></div><div style="margin-top:4px;">投喂了 <strong>' + (i < 3 ? '1份猫粮' : Math.ceil(Math.random() * 3) + '份猫粮') + '</strong>' + (i < 2 ? ' 💬 "小花状态很好！"' : '') + '</div></div>';
    }

    modal.innerHTML = `
<div class="modal-content"><div class="modal-body">
<div class="detail-header">
  <div class="detail-avatar" style="background:${color};">${emoji}</div>
  <h2>${cat.name || '猫咪'} ${statusBadgeHtml}</h2>
  <p class="detail-nickname">${cat.nickname || '可爱的TA'} · ID: #${cat.id}</p>
  ${cat.location ? '<p style="font-size:0.82rem;color:var(--text-muted);">📍 ' + CatUI.esc(cat.location) + '</p>' : ''}
</div>

<div class="card" style="margin-bottom:12px;background:linear-gradient(135deg,#f0fff4,#e8f5e9);">
  <div style="display:flex;align-items:center;justify-content:space-around;">
    <div style="text-align:center;"><div style="font-size:2rem;">❤️</div><div style="font-size:1.4rem;font-weight:700;color:#00b894;">${healthScore}</div><div style="font-size:0.72rem;">健康指数</div></div>
    <div style="text-align:center;"><div style="font-size:2rem;">${moodEmoji}</div><div style="font-size:1.4rem;font-weight:700;color:#fdcb6e;">${moodScore}</div><div style="font-size:0.72rem;">心情 · ${moodLabel}</div></div>
    <div style="text-align:center;"><div style="font-size:2rem;">🍖</div><div style="font-size:1.4rem;font-weight:700;color:#6c5ce7;">${feedCount}</div><div style="font-size:0.72rem;">本周投喂</div></div>
  </div>
</div>

<div class="detail-diary-tabs">
  <span class="detail-diary-tab active" onclick="switchDetailTab(this,'feedTab_${catId}')">📋 投喂记录</span>
  <span class="detail-diary-tab" onclick="switchDetailTab(this,'healthTab_${catId}')">🏥 健康档案</span>
  <span class="detail-diary-tab" onclick="switchDetailTab(this,'diaryTab_${catId}')">📖 猫咪日记</span>
</div>

<div id="feedTab_${catId}" class="detail-tab-content" style="max-height:280px;overflow-y:auto;">
  ${feedLogsHtml}
  <div style="text-align:center;padding:10px;font-size:0.8rem;color:var(--text-muted);">共 ${feedLogsHtml ? 6 : 0} 条近期记录</div>
</div>

<div id="healthTab_${catId}" class="detail-tab-content" style="display:none;max-height:280px;overflow-y:auto;font-size:0.85rem;color:var(--text-secondary);line-height:1.8;">
  <p>📋 <strong>绝育状态：</strong>${cat.is_neutered ? '✅ 已绝育（耳标已识别）' : '⚠️ 未绝育（优先TNR）'}</p>
  <p>🩺 <strong>最近体检：</strong>${cat.last_checkup || '2024-12-15（耳螨已治疗）'}</p>
  <p>💊 <strong>疫苗记录：</strong>${cat.vaccine || '猫三联（2024-11-01）'}</p>
  <p>⚖️ <strong>体重趋势：</strong>4.2kg → 4.5kg（健康增长）</p>
  <p style="margin-top:8px;padding:8px;background:var(--bg);border-radius:8px;">⚠️ <strong>健康预警：</strong>${cat.health_alert || '暂无异常'} <button onclick="reportCatHealth(${catId})" style="margin-left:8px;padding:4px 10px;border-radius:12px;border:1px solid var(--warning);background:var(--warning);color:#2d3436;cursor:pointer;font-size:0.78rem;">上报异常</button></p>
</div>

<div id="diaryTab_${catId}" class="detail-tab-content" style="display:none;max-height:280px;overflow-y:auto;font-size:0.85rem;">
  <div class="detail-diary-entry">🐾 <strong>今天</strong>：${cat.name || 'TA'}来了猫屋3次，最喜欢晚上10点那顿。吃得很安心，还对着摄像头打了个哈欠。</div>
  <div class="detail-diary-entry">🌤️ <strong>昨天</strong>：阳光很好，在猫屋旁晒了2小时太阳，有2位路人驻足拍照。</div>
  <div class="detail-diary-entry">🏃 <strong>前天</strong>：精力充沛！在小区花园追蝴蝶玩了半小时。</div>
  <div style="text-align:center;padding:12px;"><button onclick="uploadCatPhoto()" class="diary-upload-btn">📸 上传我拍的照片（共创日记）</button></div>
</div>

<div class="detail-actions" style="margin-top:16px;gap:8px;">
  <button onclick="remoteFeed();closeCatDetailPopup(${catId})" class="btn btn-feed">🍖 远程投喂</button>
  <button onclick="showFeedLogs(${catId})" class="btn btn-secondary">📋 投喂记录</button>
  <button onclick="shareCatPopup(${catId})" class="btn btn-secondary">📤 分享</button>
  <button onclick="handleReportAbuse(${catId})" class="btn btn-secondary" style="color:var(--danger);">🚨 举报</button>
</div>
</div></div>`;

    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) closeCatDetailPopup(catId); });
}

/**
 * 关闭指定猫咪的详情弹窗
 * 通过 ID 查找弹窗元素并从 DOM 中移除
 * @param {number} catId - 猫咪 ID
 */
function closeCatDetailPopup(catId) { const m = document.getElementById('catDetailPopup_' + catId); if (m) m.remove(); }

/**
 * 关闭所有猫咪详情弹窗
 * 查找所有以 'catDetailPopup_' 开头的元素并移除
 */
function closeCatDetail() { document.querySelectorAll('[id^="catDetailPopup_"]').forEach(m => m.remove()); }

/**
 * 切换猫咪详情弹窗中的标签页
 * 取消当前标签页的 active 状态，激活被点击的标签页
 * 隐藏所有 .detail-tab-content，仅显示目标标签页
 * @param {HTMLElement} tabEl - 被点击的标签页元素
 * @param {string} tabId - 目标标签页内容区域的 ID
 */
function switchDetailTab(tabEl, tabId) {
    tabEl.parentElement.querySelectorAll('.detail-diary-tab').forEach(t => t.classList.remove('active'));
    tabEl.classList.add('active');
    tabEl.closest('.modal-body').querySelectorAll('.detail-tab-content').forEach(c => c.style.display = 'none');
    const target = document.getElementById(tabId);
    if (target) target.style.display = 'block';
}

// ============================================
// 【增强4】分享猫咪弹窗（独立版，支持从详情页调用）
// ============================================
/**
 * 显示分享猫咪弹窗（独立版，支持从详情页调用）
 * 从 window._allCats 和 LiveRoom.cats 合并查找猫咪
 * 若找不到则降级调用 ShareUI.shareCat
 * 弹窗显示猫咪预览（头像、名称、昵称、位置、投喂次数）
 * 提供微信/微博/QQ/复制链接四种分享方式
 * 同时显示可复制的分享链接
 * 点击蒙层关闭弹窗
 * @param {number} catId - 猫咪 ID
 */
function shareCatPopup(catId) {
    const allCats = [...(window._allCats || []), ...(LiveRoom.cats || [])];
    const cat = allCats.find(c => c.id === catId);
    if (!cat) { ShareUI.shareCat(catId); return; }
    const shareUrl = window.location.origin + '/cats?cat=' + catId;
    const modal = document.createElement('div');
    modal.className = 'share-modal show';
    modal.id = 'shareCatModal';
    modal.innerHTML = `
<div class="share-modal-content">
  <button class="share-modal-close" onclick="document.getElementById('shareCatModal').remove()">✕</button>
  <div class="share-modal-header"><h3>📤 分享这只猫咪</h3><p>让更多人认识${cat.name || 'TA'}</p></div>
  <div class="share-cat-preview"><div class="share-cat-avatar">${CatUI.getEmojiById(catId)}</div><div class="share-cat-name">${cat.name}</div><div class="share-cat-nickname">${cat.nickname || '可爱的TA'}</div><div class="share-cat-info"><span>📍 ${cat.location || '社区'}</span><span>🍖 ${cat.feed_count || 0}次投喂</span></div></div>
  <div class="share-options">
    <div class="share-option" onclick="shareTo('wechat');document.getElementById('shareCatModal').remove()"><span class="share-option-icon">💚</span><span class="share-option-label">微信</span></div>
    <div class="share-option" onclick="shareTo('weibo');document.getElementById('shareCatModal').remove()"><span class="share-option-icon">🔴</span><span class="share-option-label">微博</span></div>
    <div class="share-option" onclick="shareTo('qq');document.getElementById('shareCatModal').remove()"><span class="share-option-icon">🐧</span><span class="share-option-label">QQ</span></div>
    <div class="share-option" onclick="shareTo('copy');document.getElementById('shareCatModal').remove()"><span class="share-option-icon">📋</span><span class="share-option-label">复制链接</span></div>
  </div>
  <div class="share-link-section"><span class="share-link-label">分享链接</span><div class="share-link-container"><input class="share-link-input" value="${shareUrl}" readonly><button class="share-link-btn" onclick="navigator.clipboard.writeText('${shareUrl}');Toast.show('链接已复制',1500,'success')">复制</button></div></div>
</div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
}

// ============================================
// 【增强5】社区一键举报滥用行为
// ============================================
/**
 * 显示举报异常行为弹窗
 * 从 window._allCats 和 LiveRoom.cats 合并查找猫咪
 * 弹窗提供举报类型选择（虐待/投毒/捕兽夹/受伤/扰民/其他）
 * 以及文字描述输入框
 * 点击蒙层关闭弹窗
 * @param {number} catId - 猫咪 ID
 */
function handleReportAbuse(catId) {
    const allCats = [...(window._allCats || []), ...(LiveRoom.cats || [])];
    const cat = allCats.find(c => c.id === catId) || { name: (catId ? '猫咪#' + catId : '未知') };
    const modal = document.createElement('div');
    modal.className = 'gov-report-modal show';
    modal.id = 'reportAbuseModal';
    modal.innerHTML = `
<div class="gov-report-content">
  <h3>🚨 举报异常行为</h3>
  <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:12px;">关于 <strong>${cat.name || '猫咪'}</strong> 的异常情况</p>
  <select id="abuseReportType" style="width:100%;padding:10px;border:1.5px solid var(--border);border-radius:10px;margin-bottom:12px;background:var(--bg);color:var(--text);">
    <option value="">请选择举报类型</option>
    <option value="abuse">🐾 虐待/驱赶猫咪</option>
    <option value="poison">☠️ 疑似投毒</option>
    <option value="trap">🪤 私设捕兽夹</option>
    <option value="injury">🤕 猫咪受伤</option>
    <option value="disturb">📢 严重扰民</option>
    <option value="other">📝 其他异常</option>
  </select>
  <textarea id="abuseReportDesc" placeholder="请描述您发现的具体情况（选填）" style="width:100%;padding:10px;border:1.5px solid var(--border);border-radius:10px;min-height:80px;background:var(--bg);color:var(--text);margin-bottom:12px;"></textarea>
  <div class="btn-row"><button class="btn-cancel" onclick="document.getElementById('reportAbuseModal').remove()">取消</button><button class="btn-submit" onclick="submitAbuseReport(${catId})">提交举报</button></div>
</div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
}

/**
 * 提交举报信息
 * 1. 获取举报类型和描述，校验必填类型
 * 2. POST /report-abuse 提交举报数据（cat_id, report_type, description）
 * 3. 成功 → Toast 提示已提交；失败 → Toast 错误信息
 * 4. 网络异常时降级显示"离线模式"成功提示
 * 5. 关闭举报弹窗
 * @param {number} catId - 猫咪 ID
 */
function submitAbuseReport(catId) {
    const type = document.getElementById('abuseReportType')?.value;
    const desc = document.getElementById('abuseReportDesc')?.value || '';
    if (!type) { Toast.show('请选择举报类型', 2000, 'warning'); return; }
    API.post('/report-abuse', { cat_id: catId, report_type: type, description: desc }).then(res => {
        if (res.success) { Toast.show('举报已提交，志愿者将在24小时内处理', 3000, 'success'); }
        else Toast.show(res.message || '提交失败，请重试', 2000, 'error');
    }).catch(() => { Toast.show('举报已提交（离线模式），志愿者将在24小时内处理', 3000, 'success'); });
    document.getElementById('reportAbuseModal')?.remove();
}

// ============================================
// 【增强6】统计看板实时刷新
// ============================================
/**
 * 刷新统计数据看板
 * 调用 updateAllStats 更新所有统计数值，并显示刷新成功提示
 */
function refreshStatsDashboard() { updateAllStats(); Toast.show('📊 统计数据已刷新', 1500, 'success'); }

// ============================================
// 【增强7】领养排行榜渲染
// ============================================
/**
 * 渲染领养热度排行榜
 * 从 window._allCats 和 LiveRoom.cats 合并查找可领养猫咪
 * 优先展示 status='adoption' 或 adoptable=true 的猫咪，若无则取前 5 只
 * 每只猫咪显示排名、头像、名称、位置、关注人数（模拟）和进度条
 * 点击"查看"按钮可打开猫咪详情弹窗
 * 目标 DOM：#adoptionLeaderboard
 */
function renderAdoptionLeaderboard() {
    const container = document.getElementById('adoptionLeaderboard');
    if (!container) return;
    const allCats = [...(window._allCats || []), ...(LiveRoom.cats || [])];
    const adoptable = allCats.filter(c => c.status === 'adoption' || c.adoptable);
    /* 若无待领养猫咪则降级取前 5 只展示 */
    const leaders = adoptable.length > 0 ? adoptable : allCats.slice(0, 5);
    if (leaders.length === 0) { container.innerHTML = '<div class="empty-state"><div class="empty-icon">🐱</div><div class="empty-text">暂无待领养猫咪</div></div>'; return; }
    container.innerHTML = '<h4 style="font-size:0.95rem;color:var(--text-secondary);margin-bottom:12px;">🏆 领养热度排行</h4>' + leaders.map((cat, i) => {
        const interest = Math.floor(Math.random() * 50 + 10);
        const w = Math.min(100, Math.max(10, interest));
        return '<div class="leaderboard-item' + (i < 3 ? ' top-3' : '') + '"><span class="leaderboard-rank">' + (i + 1) + '</span><div style="width:36px;height:36px;border-radius:50%;background:' + CatUI.getColor(cat.id) + ';display:flex;align-items:center;justify-content:center;font-size:1.2rem;color:#fff;">' + CatUI.getEmojiById(cat.id) + '</div><div class="leaderboard-info"><div class="leaderboard-name">' + (cat.name || '猫咪#' + cat.id) + '</div><div class="leaderboard-location">' + (cat.location || '社区') + ' · ' + interest + '人关注</div><div style="height:4px;background:var(--border);border-radius:2px;margin-top:4px;"><div style="height:100%;width:' + w + '%;background:' + CatUI.getColor(cat.id) + ';border-radius:2px;"></div></div></div><button onclick="showCatDetailPopup(' + cat.id + ')" style="padding:6px 12px;border-radius:14px;border:1px solid var(--primary);background:none;color:var(--primary);cursor:pointer;font-size:0.75rem;white-space:nowrap;">查看</button></div>';
    }).join('');
}

// ============================================
// 【增强8】猫咪心情指数可视化
// ============================================
/**
 * 渲染猫咪心情指数可视化
 * 当前实现为直接打开猫咪详情弹窗（弹窗内包含心情指数展示）
 * @param {number} catId - 猫咪 ID
 */
function renderCatMoodIndicator(catId) { showCatDetailPopup(catId); }

// ============================================
// 全局辅助函数
// ============================================
/**
 * 打开社区治理投诉/建议弹窗
 * 目标 DOM：#govReportModal
 */
function openGovReport() { const m = document.getElementById('govReportModal'); if (m) m.style.display = 'flex'; }

/**
 * 关闭社区治理投诉/建议弹窗
 * 隐藏弹窗并清空文本输入框
 * 目标 DOM：#govReportModal, #govReportText
 */
function closeGovReport() { const m = document.getElementById('govReportModal'); if (m) { m.style.display = 'none'; const t = document.getElementById('govReportText'); if (t) t.value = ''; } }

/**
 * 提交社区治理投诉/建议
 * 1. 获取用户输入文本，校验非空
 * 2. 调用 CommunityMediation.generateReport 生成治理建议报告
 * 3. 将弹窗内容替换为报告展示（禁止清单、替代方案、两周执行计划）
 * 4. 用户可点击"确认并提交"关闭弹窗
 * 目标 DOM：#govReportText, #govReportModal
 */
function submitGovReport() {
    const text = document.getElementById('govReportText')?.value?.trim();
    if (!text) { Toast.warning('请填写投诉或建议内容', 2500); return; }
    const report = CommunityMediation.generateReport({ problem: text });
    const modal = document.getElementById('govReportModal');
    if (!modal) return;
    const content = modal.querySelector('.gov-report-content');
    if (content) {
        content.innerHTML = `<h3>📋 治理建议报告已生成</h3>
<div style="text-align:left;padding:1rem;max-height:60vh;overflow-y:auto;">
<h4>🚫 禁止清单</h4><ul style="list-style:none;padding:0;">${report.forbidden.map(a => '<li>❌ ' + a + '</li>').join('')}</ul>
<h4>💡 无害替代方案</h4><ul style="list-style:none;padding:0;">${report.alternatives.map(s => '<li>✅ ' + s + '</li>').join('')}</ul>
<h4>📋 两周闭环执行计划</h4><ul style="list-style:none;padding:0;"><li>📅 第1周：${report.plan.week1}</li><li>📅 第2周：${report.plan.week2}</li></ul>
</div><div class="btn-row"><button class="btn btn-secondary" onclick="closeGovReport()">关闭</button><button class="btn btn-primary" onclick="Toast.success('报告已提交，物业将在24小时内响应');closeGovReport();">确认并提交</button></div>`;
    }
}

/**
 * 切换面板的展开/折叠状态
 * 展开时触发箭头变为 ▲，折叠时变为 ▼
 * 特殊面板展开时自动加载数据：
 *   - panelLeaderboard → renderLeaderboard
 *   - panelNotifications → NotificationCenter.displayNotifications
 * 目标 DOM：#{panelId}Content, #{panelId} .panel-toggle
 * @param {string} panelId - 面板元素的 ID
 */
function togglePanel(panelId) {
    const content = document.getElementById(panelId + 'Content');
    const header = document.querySelector('#' + panelId + ' .panel-toggle');
    if (!content) return;
    /* 展开/折叠切换逻辑 */
    if (content.style.display === 'none' || !content.style.display) { content.style.display = 'block'; if (header) header.textContent = '▲'; }
    else { content.style.display = 'none'; if (header) header.textContent = '▼'; }
    /* 展开时按需加载对应面板数据 */
    if (panelId === 'panelLeaderboard' && content.style.display !== 'none') renderLeaderboard();
    if (panelId === 'panelNotifications' && content.style.display !== 'none') NotificationCenter.displayNotifications();
}

/**
 * 渲染猫咪积分排行榜
 * 从 GET /api/cats 获取猫咪列表，按积分降序排列
 * 前三名显示奖牌 emoji（🥇🥈🥉），其余显示数字排名
 * 点击排行项可切换到对应猫咪的直播画面
 * 目标 DOM：#leaderboardList
 * @returns {Promise<void>}
 */
async function renderLeaderboard() {
    const list = document.getElementById('leaderboardList');
    if (!list) return;
    let cats = [];
    try { const r = await fetch('/api/cats'); const d = await r.json(); cats = d.cats || d || []; } catch { cats = []; }
    if (cats.length === 0) { list.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-muted);">🏆 暂无排名数据</div>'; return; }
    /* 模拟数据：若猫咪无 points 字段则随机生成积分 */
    const sorted = cats.map(c => ({ ...c, score: c.points || Math.floor(Math.random() * 200 + 50) })).sort((a, b) => b.score - a.score);
    const medals = ['🥇', '🥈', '🥉'];
    list.innerHTML = sorted.map((cat, i) => '<div class="leaderboard-item" onclick="switchLiveCat(' + cat.id + ')" style="cursor:pointer;"><span class="leaderboard-rank">' + (i < 3 ? medals[i] : (i + 1)) + '</span><span class="leaderboard-avatar">🐱</span><span class="leaderboard-name">' + (cat.name || '猫咪') + '</span><span class="leaderboard-score">' + cat.score + ' 分</span></div>').join('');
}

/**
 * 切换直播间当前猫咪
 * 更新 LiveRoom.currentCatId 并重新加载猫咪信息，显示切换成功提示
 * @param {number} catId - 目标猫咪 ID
 */
function switchLiveCat(catId) { LiveRoom.currentCatId = catId; LiveRoom.loadCurrentCat(); Toast.success('已切换到猫咪 ' + catId, 2000); }

/**
 * 平滑滚动到直播区域
 * 目标 DOM：#liveSection
 */
function scrollToLive() { const el = document.getElementById('liveSection'); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }

/**
 * 平滑滚动到日记区域
 * 目标 DOM：#diarySection
 */
function scrollToDiary() { const el = document.getElementById('diarySection'); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }

/**
 * 猫咪 emoji 弹跳动画
 * 将 #liveCatEmoji 元素放大到 1.3 倍后在 300ms 恢复，产生弹跳效果
 * 目标 DOM：#liveCatEmoji
 */
function bounceCat() { const e = document.getElementById('liveCatEmoji'); if (e) { e.style.transform = 'scale(1.3)'; e.style.transition = 'transform 0.2s ease'; setTimeout(() => { e.style.transform = 'scale(1)'; }, 300); } }

/**
 * 显示当前猫咪信息
 * 若 LiveRoom.currentCat 存在，以 Toast 展示名称、绝育状态和花色
 * 否则提示"暂无猫咪信息"
 */
function showCatInfo() {
    if (LiveRoom.currentCat) { const c = LiveRoom.currentCat; Toast.show('当前：' + c.name + ' | ' + (c.neutered ? '已绝育 ✅' : '待绝育 ⚠️') + ' | ' + (c.color || '花色未知'), 4000, 'info'); }
    else Toast.show('暂无猫咪信息', 2000, 'warning');
}

/**
 * 分享当前直播画面
 * 若有当前猫咪则打开分享猫咪弹窗，否则打开通用分享弹窗
 * 目标 DOM：#shareModal
 */
function shareLive() {
    if (LiveRoom.currentCat) shareCatPopup(LiveRoom.currentCatId);
    else { const modal = document.getElementById('shareModal'); if (modal) modal.classList.add('show'); }
}

/**
 * 关闭通用分享弹窗
 * 目标 DOM：#shareModal
 */
function closeShareModal() { const m = document.getElementById('shareModal'); if (m) m.classList.remove('show'); }

/**
 * 分享到指定平台
 * - 'copy'：复制当前页面 URL 到剪贴板
 * - 'wechat'：提示用户截图分享到微信
 * - 'weibo'：打开微博分享页面
 * 执行后关闭分享弹窗
 * @param {string} platform - 分享平台标识：'copy' | 'wechat' | 'weibo' | 'qq'
 */
function shareTo(platform) {
    const url = window.location.href;
    if (platform === 'copy') { navigator.clipboard.writeText(url).then(() => Toast.success('链接已复制', 2000)).catch(() => Toast.show('复制失败', 2000, 'warning')); }
    else if (platform === 'wechat') Toast.show('请截图分享到微信好友或朋友圈', 3000, 'info');
    else if (platform === 'weibo') window.open('https://service.weibo.com/share/share.php?url=' + encodeURIComponent(url) + '&title=' + encodeURIComponent('来看可爱的猫咪！'), '_blank');
    closeShareModal();
}

/**
 * 上传猫咪照片（模拟）
 * 显示两条连续 Toast：先提示选择照片，1.5 秒后提示 AI 正在识别
 */
function uploadCatPhoto() { Toast.show('请在弹出窗口中选择猫咪照片上传（AI将自动识别匹配猫咪档案）', 4000, 'info'); setTimeout(() => Toast.success('照片已上传！AI正在识别...', 3000), 1500); }

/**
 * 远程投喂当前猫咪
 * 若有选中猫咪则调用 LiveRoom.feed()，否则提示先选择猫咪
 */
function remoteFeed() { if (LiveRoom.currentCatId) LiveRoom.feed(); else Toast.warning('请先选择一只猫咪进行投喂', 2500); }

/**
 * 显示指定猫咪的投喂记录
 * 调用 LiveRoom.loadFeedLogs 加载记录并显示刷新提示
 * @param {number} catId - 猫咪 ID
 */
function showFeedLogs(catId) { LiveRoom.loadFeedLogs(catId); Toast.show('投喂记录已刷新', 1500, 'success'); }

/**
 * 上报猫咪健康异常
 * 直接调用 handleReportAbuse 打开举报弹窗
 * @param {number} catId - 猫咪 ID
 */
function reportCatHealth(catId) { handleReportAbuse(catId); }

/**
 * 显示登录弹窗（Auth.showLogin 的快捷别名）
 */
function showLogin() { Auth.showLogin(); }

/**
 * 切换深色模式（DarkMode.toggle 的快捷别名）
 */
function toggleDarkMode() { DarkMode.toggle(); }

/**
 * 更新页面中所有统计数据
 * 从 GET /api/stats 获取最新统计，更新各统计元素的文本内容
 * 目标 DOM：#totalCats, #statCats, #neuteredCount, #unnuteredCount,
 *           #adoptedCount, #statFeedings, #statAdoptions
 * @returns {Promise<void>}
 */
async function updateAllStats() {
    try {
        const resp = await fetch('/api/stats'); const stats = await resp.json();
        if (stats) {
            document.querySelectorAll('#totalCats, #statCats').forEach(el => { if (el) el.textContent = stats.total_cats || 4; });
            document.querySelectorAll('#neuteredCount').forEach(el => { if (el) el.textContent = stats.neutered || 2; });
            document.querySelectorAll('#unnuteredCount').forEach(el => { if (el) el.textContent = stats.unnutered || 2; });
            document.querySelectorAll('#adoptedCount').forEach(el => { if (el) el.textContent = stats.adopted || 1; });
            const f = document.getElementById('statFeedings'); if (f) f.textContent = (stats.total_feedings || 3427).toLocaleString();
            const a = document.getElementById('statAdoptions'); if (a) a.textContent = stats.adopted || 1;
        }
    } catch { console.error('更新统计数据失败'); }
}

/**
 * 渲染猫咪日记卡片列表
 * 从 GET /api/cats 获取猫咪列表，取前 4 只生成 AI 日记
 * 每张日记卡片显示：猫咪头像、名称、日期、日记内容、来访次数（模拟）、停留时长（模拟）
 * 点击卡片可打开猫咪详情弹窗，底部提供"上传照片共创日记"按钮
 * 目标 DOM：#diaryCards
 * @returns {Promise<void>}
 */
function renderCatDiaries() {
    const container = document.getElementById('diaryCards');
    if (!container) return;
    fetch('/api/cats').then(r => r.json()).then(data => {
        const cats = data.cats || data || [];
        if (cats.length === 0) { container.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-muted);">📖 暂无猫咪日记数据</div>'; return; }
        /* 模拟数据：来访次数和停留时长为随机值 */
        container.innerHTML = cats.slice(0, 4).map(cat => {
            const diary = CatDiary.generate(cat, null);
            return `<div class="diary-card" onclick="showCatDetailPopup(${cat.id})" style="cursor:pointer">
<div class="diary-card-header"><span class="diary-cat-avatar" style="background:${CatUI.getColor(cat.id)};">${CatUI.getEmojiById(cat.id)}</span><div><span class="diary-cat-name">${cat.name || '猫咪'}</span><span class="diary-date">${CatDiary.today()}</span></div></div>
<div class="diary-content">${diary}</div>
<div class="diary-stats"><span class="diary-stat-item">🐾 今日来访 ${Math.floor(Math.random()*4)+1} 次</span><span class="diary-stat-item">⏱ 停留约 ${Math.floor(Math.random()*15)+5} 分钟</span></div>
<div class="diary-co-create"><p>🖼️ 发现这只猫咪？上传照片共创日记！</p><button class="diary-upload-btn" onclick="event.stopPropagation();uploadCatPhoto()">📸 上传照片</button></div>
</div>`;
        }).join('');
    }).catch(() => { container.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-muted);">⚠️ 日记加载失败</div>'; });
}

// ============================================
// 增强功能初始化
// ============================================
/**
 * 初始化增强功能
 * 1. 启动 AI 实时验证指示器
 * 2. 渲染领养排行榜
 * 3. 设置 30 秒定时刷新统计数据
 */
function initEnhancedFeatures() {
    AIVerifier.start();
    renderAdoptionLeaderboard();
    setInterval(() => updateAllStats(), 30000);
    console.log('✅ 猫迹 CatTrace 增强功能已初始化');
}

/**
 * 注册 Service Worker
 * 若浏览器支持 Service Worker API，则注册 /static/sw.js
 * 注册成功/失败均在控制台输出日志
 */
function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').then(r => console.log('SW注册成功:', r.scope)).catch(e => console.log('SW注册失败:', e));
    }
}

// ============================================
// 页面初始化
// ============================================
/**
 * 页面初始化入口
 * DOM 加载完成后按顺序初始化所有模块：
 * 1. 注册 Service Worker（离线缓存）
 * 2. 初始化全局模块：Toast、Auth、DarkMode、ShareUI
 * 3. 绑定深色模式切换按钮点击事件
 * 4. 根据当前 URL 路径初始化对应页面模块：
 *    - '/' 或 '/index.html' → 首页：StatsDashboard、日记、统计、排行榜、增强功能、直播间
 *    - '/cats' → 猫咪档案页：CatsPage
 *    - '/adopt' → 领养页：AdoptPage
 * 5. 初始化通知中心并请求浏览器通知权限（所有页面）
 * 6. 注册全局错误监听（error + unhandledrejection）
 */
document.addEventListener('DOMContentLoaded', () => {
    registerServiceWorker();
    Toast.init();
    Auth.init();
    DarkMode.init();
    const dt = document.getElementById('darkModeToggle');
    if (dt) dt.addEventListener('click', () => DarkMode.toggle());
    ShareUI.init();

    /* 根据 URL 路径判断当前页面，初始化对应模块 */
    const path = window.location.pathname;
    if (path === '/' || path === '/index.html') {
        StatsDashboard.init();
        renderCatDiaries();
        updateAllStats();
        renderLeaderboard();
        initEnhancedFeatures();
    }
    NotificationCenter.init();
    NotificationCenter.requestPermission();
    /* 页面路由：不同路径初始化不同模块 */
    if (path === '/' || path === '/index.html') LiveRoom.init();
    else if (path === '/cats' || path === '/cats.html' || path === '/cats/') CatsPage.init();
    else if (path === '/adopt' || path === '/adopt.html' || path === '/adopt/') AdoptPage.init();

    /* 全局错误捕获 */
    window.addEventListener('error', e => console.error('全局错误:', e.error));
    window.addEventListener('unhandledrejection', e => console.error('未处理Promise:', e.reason));
});