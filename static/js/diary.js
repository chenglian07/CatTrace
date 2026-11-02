/**
 * DiaryPage - 猫咪日记独立页面模块
 * 
 * 负责日记页面的完整交互逻辑，包括：
 * - 猫咪筛选（按猫咪 ID 过滤日记）
 * - 分页加载日记列表（调用 /api/diaries 接口）
 * - 排序（按日期升/降序、按点赞数）
 * - 日记详情弹窗（含评论功能）
 * - 点赞功能（本地 localStorage 记录 + 后端接口）
 * 
 * 所有方法挂载在 DiaryPage 对象上，通过 onclick 等内联事件和 bindEvents 绑定触发
 */
const DiaryPage = {
    /** @type {Array} cats - 猫咪列表数据，从 /api/cats 加载 */
    cats: [],
    /** @type {string} currentCatFilter - 当前猫咪筛选条件，'all' 表示全部 */
    currentCatFilter: 'all',
    /** @type {number} currentPage - 当前分页页码 */
    currentPage: 1,
    /** @type {number} perPage - 每页显示条数 */
    perPage: 10,
    /** @type {number} totalPages - 总页数，由后端返回 */
    totalPages: 1,
    /** @type {string} currentSort - 排序方式：'date-desc' | 'date-asc' | 'likes' */
    currentSort: 'date-desc',
    /** @type {Object|null} currentDetailDiary - 当前详情弹窗中展示的日记对象 */
    currentDetailDiary: null,

    /**
     * 页面初始化入口
     * 按顺序执行：加载猫咪列表 → 渲染筛选按钮 → 加载日记 → 绑定事件
     * @returns {Promise<void>}
     */
    async init() {
        await this.loadCats();
        this.renderCatFilters();
        await this.loadDiaries();
        this.bindEvents();
    },

    /**
     * 从后端加载猫咪列表
     * 调用 /api/cats 接口，成功后存入 this.cats；失败时置为空数组
     * @returns {Promise<void>}
     */
    async loadCats() {
        try { const r = await fetch('/api/cats'); const d = await r.json(); this.cats = d.cats || d || []; } catch { this.cats = []; }
    },

    /**
     * 渲染猫咪筛选按钮组
     * 为每只猫咪生成一个筛选按钮，显示 emoji + 猫咪名称
     * 目标 DOM：#catFilterBtns
     */
    renderCatFilters() {
        const c = document.getElementById('catFilterBtns');
        if (!c) return;
        c.innerHTML = this.cats.map(cat => `<button class="diary-filter-btn" data-cat="${cat.id}">${this._getEmoji(cat.id)} ${cat.name || '猫咪'}</button>`).join('');
    },

    /**
     * 加载并渲染日记列表
     * 1. 显示加载动画
     * 2. 根据当前筛选条件和页码构造请求 URL（/api/diaries）
     * 3. 获取数据后按当前排序方式排序
     * 4. 按日期分组渲染，每组显示日期徽章和日记条目
     * 5. 更新分页控件状态
     * 失败时显示错误提示
     * @returns {Promise<void>}
     */
    async loadDiaries() {
        const tl = document.getElementById('diaryTimeline');
        if (!tl) return;
        tl.innerHTML = '<div class="diary-loading"><div class="diary-loading-spinner"></div><p>正在翻阅猫咪日记...</p></div>';
        try {
            let url = `/api/diaries?page=${this.currentPage}&per_page=${this.perPage}`;
            if (this.currentCatFilter !== 'all') url += `&cat_id=${this.currentCatFilter}`;
            const resp = await fetch(url);
            const data = await resp.json();
            if (!data.success) { tl.innerHTML = '<div class="diary-empty"><div class="diary-empty-icon">😿</div><p>加载失败</p></div>'; return; }
            this.totalPages = data.total_pages || 1;
            this._updatePagination();
            const diaries = data.diaries || [];
            if (diaries.length === 0) { tl.innerHTML = '<div class="diary-empty"><div class="diary-empty-icon">📖</div><p class="diary-empty-text">暂无日记记录</p></div>'; return; }
            const sorted = this._sortDiaries(diaries);
            const groups = {};
            sorted.forEach(d => { const date = d.date || '未知日期'; if (!groups[date]) groups[date] = []; groups[date].push(d); });
            let html = '';
            for (const [date, entries] of Object.entries(groups)) {
                const ds = date.slice(5).split('-')[1] || '?';
                html += `<div class="diary-date-group"><div class="diary-date-badge">${ds}</div><div class="diary-date-title">📅 ${this._formatDateLabel(date)}</div>${entries.map((d, i) => this._renderEntry(d, i)).join('')}</div>`;
            }
            tl.innerHTML = html;
        } catch (err) { console.error('加载日记失败:', err); tl.innerHTML = '<div class="diary-empty"><div class="diary-empty-icon">⚠️</div><p>加载失败，请刷新重试</p></div>'; }
    },

    /**
     * 渲染单条日记条目 HTML（私有方法）
     * 包含猫咪头像、名称、位置、心情 emoji、正文、来访统计、点赞/评论按钮
     * 点赞状态从 localStorage 读取（键名：diary_liked_{id}）
     * 点击条目触发 showDetail，点赞/评论按钮通过 onclick 内联绑定
     * @param {Object} d - 日记数据对象
     * @param {number} idx - 条目索引，用于设置动画延迟（animation-delay）
     * @returns {string} 日记条目 HTML 字符串
     */
    _renderEntry(d, idx) {
        const moods = { '开心': '😊', '慵懒': '😴', '警惕': '👀', '放松': '😌', '好奇': '🤔', '温柔': '🥰' };
        const moodE = moods[d.mood] || '🐱';
        const liked = localStorage.getItem(`diary_liked_${d.id}`) === '1';
        return `<div class="diary-entry" onclick="DiaryPage.showDetail(${d.id})" style="animation-delay:${idx*0.08}s">
            <div class="diary-entry-header">
                <div class="diary-entry-avatar">${this._getEmoji(d.cat_id)}</div>
                <div class="diary-entry-meta">
                    <span class="diary-entry-name">${this._esc(d.cat_name)}</span>
                    <span class="diary-entry-sub">
                        <span>${this._esc(d.cat_location || '')}</span>
                        <span class="diary-entry-mood">${moodE} ${d.mood || ''}</span>
                    </span>
                </div>
            </div>
            <div class="diary-entry-body">${this._esc(d.content || '')}</div>
            <div class="diary-entry-footer">
                <div class="diary-entry-stats">
                    <span class="diary-entry-stat">🐾 ${d.visits || 0} 次来访</span>
                    <span class="diary-entry-stat">⏱ ${d.duration || 0} 分钟</span>
                </div>
                <div class="diary-entry-actions">
                    <button class="diary-action-btn ${liked ? 'liked' : ''}" onclick="event.stopPropagation(); DiaryPage.toggleLike(${d.id}, this)">
                        ${liked ? '❤️' : '🤍'} <span class="like-count">${d.likes || 0}</span>
                    </button>
                    <button class="diary-action-btn" onclick="event.stopPropagation(); DiaryPage.showDetail(${d.id})">
                        💬 ${(d.comments || []).length}
                    </button>
                </div>
            </div>
        </div>`;
    },

    /**
     * 对日记列表按当前排序方式进行排序（私有方法）
     * 返回排序后的新数组，不修改原数组
     * @param {Array<Object>} diaries - 待排序的日记数组
     * @returns {Array<Object>} 排序后的日记数组
     */
    _sortDiaries(diaries) {
        const s = [...diaries];
        if (this.currentSort === 'date-desc') s.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
        else if (this.currentSort === 'date-asc') s.sort((a, b) => (a.date || '').localeCompare(b.date || ''));
        else if (this.currentSort === 'likes') s.sort((a, b) => (b.likes || 0) - (a.likes || 0));
        return s;
    },

    /**
     * 将日期字符串格式化为带中文标签的显示文本（私有方法）
     * 特殊处理：今天显示"（今天）"，昨天显示"（昨天）"，其他日期显示星期几
     * @param {string} dateStr - 日期字符串，格式如 "2024-01-15"
     * @returns {string} 格式化后的日期标签
     */
    _formatDateLabel(dateStr) {
        if (!dateStr) return '未知日期';
        const today = new Date().toISOString().slice(0, 10);
        const yd = new Date(); yd.setDate(yd.getDate() - 1);
        const ydStr = yd.toISOString().slice(0, 10);
        if (dateStr === today) return `${dateStr}（今天）`;
        if (dateStr === ydStr) return `${dateStr}（昨天）`;
        const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
        const d = new Date(dateStr + 'T00:00:00');
        return isNaN(d.getTime()) ? dateStr : `${dateStr}（${weekdays[d.getDay()]}）`;
    },

    /**
     * 切换日记点赞状态
     * - 已点赞：移除本地 localStorage 记录，更新按钮为未点赞样式（不请求后端）
     * - 未点赞：调用 /api/diaries/{id}/like 接口，成功后更新本地记录和按钮样式
     * 点赞时触发缩放动画效果（scale 1.2 → 1.0）
     * @param {number} diaryId - 日记 ID
     * @param {HTMLElement} btn - 点赞按钮 DOM 元素
     * @returns {Promise<void>}
     */
    async toggleLike(diaryId, btn) {
        const liked = localStorage.getItem(`diary_liked_${diaryId}`) === '1';
        if (liked) {
            localStorage.removeItem(`diary_liked_${diaryId}`);
            btn.classList.remove('liked');
            const c = btn.querySelector('.like-count');
            const n = Math.max(0, parseInt(c?.textContent || 0) - 1);
            btn.innerHTML = `🤍 <span class="like-count">${n}</span>`;
            return;
        }
        try {
            const resp = await fetch(`/api/diaries/${diaryId}/like`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
            const data = await resp.json();
            if (data.success) {
                localStorage.setItem(`diary_liked_${diaryId}`, '1');
                btn.classList.add('liked');
                btn.innerHTML = `❤️ <span class="like-count">${data.likes}</span>`;
                btn.style.transform = 'scale(1.2)';
                setTimeout(() => { btn.style.transform = ''; }, 200);
            }
        } catch { Toast.show('点赞失败', 2000, 'error'); }
    },

    /**
     * 打开日记详情弹窗
     * 1. 显示加载动画并弹出模态框
     * 2. 从 /api/diaries 获取日记详情数据
     * 3. 渲染猫咪信息、日记正文、统计数据、评论列表和评论表单
     * 4. 评论表单包含昵称输入框、文本框和发送按钮
     * 目标 DOM：#diaryDetailModal, #diaryDetailBody
     * @param {number} diaryId - 日记 ID
     * @returns {Promise<void>}
     */
    async showDetail(diaryId) {
        const modal = document.getElementById('diaryDetailModal');
        const body = document.getElementById('diaryDetailBody');
        if (!modal || !body) return;
        body.innerHTML = '<div class="diary-loading"><div class="diary-loading-spinner"></div></div>';
        modal.classList.add('show');
        try {
            const resp = await fetch(`/api/diaries?page=1&per_page=50${this.currentCatFilter !== 'all' ? '&cat_id=' + this.currentCatFilter : ''}`);
            const data = await resp.json();
            const diary = (data.diaries || []).find(d => d.id === diaryId);
            if (!diary) { body.innerHTML = '<div class="diary-empty"><p>日记不存在</p></div>'; return; }
            this.currentDetailDiary = diary;
            const moodEmojis = { '开心': '😊', '慵懒': '😴', '警惕': '👀', '放松': '😌', '好奇': '🤔', '温柔': '🥰' };
            const moodEmoji = moodEmojis[diary.mood] || '🐱';
            const comments = diary.comments || [];
            body.innerHTML = `
                <div class="detail-cat-header">
                    <div class="detail-cat-avatar">${this._getEmoji(diary.cat_id)}</div>
                    <div class="detail-cat-info"><h3>${this._esc(diary.cat_name)}</h3><p>${this._esc(diary.cat_nickname || '')} · ${this._esc(diary.cat_location || '')}</p></div>
                </div>
                <div class="detail-diary-date">📅 ${this._formatDateLabel(diary.date)} · ${moodEmoji} ${diary.mood || ''}</div>
                <div class="detail-diary-text">${this._esc(diary.content || '')}</div>
                <div class="detail-diary-stats">
                    <span>🐾 来访 ${diary.visits || 0} 次</span>
                    <span>⏱ 停留 ${diary.duration || 0} 分钟</span>
                    <span>🤍 ${diary.likes || 0} 次点赞</span>
                </div>
                <div class="detail-comments-title">💬 评论 (${comments.length})</div>
                <div class="detail-comment-list" id="commentList">
                    ${comments.length > 0 ? comments.map(c => `
                        <div class="detail-comment-item">
                            <span class="detail-comment-user">${this._esc(c.user)}</span>
                            <span class="detail-comment-text">${this._esc(c.text)}</span>
                            <div class="detail-comment-time">${this._formatTime(c.time)}</div>
                        </div>`).join('') : '<div class="detail-comment-empty">暂无评论，来留下第一条吧！</div>'}
                </div>
                <div class="detail-comment-form">
                    <div class="detail-comment-input-wrap">
                        <input type="text" id="commentUser" placeholder="你的昵称" maxlength="32">
                        <textarea id="commentText" placeholder="写下你的评论..." rows="2" maxlength="500"></textarea>
                    </div>
                    <button class="detail-comment-submit" onclick="DiaryPage.submitComment(${diary.id})">发送</button>
                </div>`;
        } catch { body.innerHTML = '<div class="diary-empty"><p>加载失败</p></div>'; }
    },

    /**
     * 提交评论
     * 校验昵称和内容非空后，调用 /api/diaries/{id}/comment 接口
     * 成功后将新评论追加到评论列表末尾，清空输入框，更新评论计数
     * 同时重新加载日记列表以刷新评论数显示
     * @param {number} diaryId - 日记 ID
     * @returns {Promise<void>}
     */
    async submitComment(diaryId) {
        const userEl = document.getElementById('commentUser');
        const textEl = document.getElementById('commentText');
        if (!userEl || !textEl) return;
        const user = userEl.value.trim();
        const text = textEl.value.trim();
        if (!user) { Toast.show('请填写昵称', 2000, 'warning'); return; }
        if (!text) { Toast.show('评论内容不能为空', 2000, 'warning'); return; }
        try {
            const resp = await fetch(`/api/diaries/${diaryId}/comment`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user, text })
            });
            const data = await resp.json();
            if (data.success) {
                Toast.show('评论成功！', 2000, 'success');
                const list = document.getElementById('commentList');
                if (list) {
                    const empty = list.querySelector('.detail-comment-empty');
                    if (empty) empty.remove();
                    list.insertAdjacentHTML('beforeend', `<div class="detail-comment-item" style="animation:diarySlideIn 0.3s ease"><span class="detail-comment-user">${this._esc(data.comment.user)}</span><span class="detail-comment-text">${this._esc(data.comment.text)}</span><div class="detail-comment-time">刚刚</div></div>`);
                }
                textEl.value = '';
                const title = document.querySelector('.detail-comments-title');
                if (title) title.innerHTML = `💬 评论 (${data.comment_count})`;
                this.loadDiaries();
            } else { Toast.show(data.message || '评论失败', 2000, 'error'); }
        } catch { Toast.show('网络异常', 2000, 'error'); }
    },

    /**
     * 关闭日记详情弹窗
     * 移除模态框的 'show' 类以隐藏弹窗
     * 目标 DOM：#diaryDetailModal
     */
    closeDetail() {
        const m = document.getElementById('diaryDetailModal');
        if (m) m.classList.remove('show');
    },

    /**
     * 翻到下一页
     * 条件：当前页码小于总页数时才执行
     * 操作：页码 +1 → 重新加载日记 → 平滑滚动到页面顶部
     */
    nextPage() {
        if (this.currentPage < this.totalPages) { this.currentPage++; this.loadDiaries(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
    },

    /**
     * 翻到上一页
     * 条件：当前页码大于 1 时才执行
     * 操作：页码 -1 → 重新加载日记 → 平滑滚动到页面顶部
     */
    prevPage() {
        if (this.currentPage > 1) { this.currentPage--; this.loadDiaries(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
    },

    /**
     * 更新分页控件的显示状态
     * - 总页数 > 1 时显示分页栏，否则隐藏
     * - 第 1 页时禁用"上一页"按钮
     * - 最后一页时禁用"下一页"按钮
     * - 更新页码文本为"第 X / Y 页"
     * 目标 DOM：#diaryPagination, #prevPageBtn, #nextPageBtn, #pageInfo
     */
    _updatePagination() {
        const p = document.getElementById('diaryPagination');
        if (!p) return;
        p.style.display = this.totalPages > 1 ? 'flex' : 'none';
        const prev = document.getElementById('prevPageBtn');
        const next = document.getElementById('nextPageBtn');
        const info = document.getElementById('pageInfo');
        if (prev) prev.disabled = this.currentPage <= 1;
        if (next) next.disabled = this.currentPage >= this.totalPages;
        if (info) info.textContent = `第 ${this.currentPage} / ${this.totalPages} 页`;
    },

    /**
     * 绑定页面事件监听器
     * 包含以下事件：
     * 1. 猫咪筛选按钮点击 → 切换 active 样式 → 更新筛选条件 → 重置页码 → 重新加载
     * 2. 排序下拉框变更 → 更新排序方式 → 重新加载日记
     * 3. 详情弹窗背景点击（点击蒙层本身）→ 关闭弹窗
     * 4. ESC 键按下 → 关闭详情弹窗
     */
    bindEvents() {
        /* 1. 为每个猫咪筛选按钮绑定点击事件 */
        document.querySelectorAll('.diary-filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                /* 移除所有按钮的 active 类，再为当前按钮添加 */
                document.querySelectorAll('.diary-filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentCatFilter = btn.dataset.cat;
                this.currentPage = 1;
                this.loadDiaries();
            });
        });
        /* 2. 排序下拉框变更事件 */
        const sortSelect = document.getElementById('diarySort');
        if (sortSelect) sortSelect.addEventListener('change', (e) => { this.currentSort = e.target.value; this.loadDiaries(); });
        /* 3. 点击弹窗蒙层关闭 */
        const modal = document.getElementById('diaryDetailModal');
        if (modal) modal.addEventListener('click', (e) => { if (e.target === modal) this.closeDetail(); });
        /* 4. ESC 键关闭弹窗 */
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape') this.closeDetail(); });
    },

    /**
     * 根据猫咪 ID 返回对应的 emoji 表情（私有方法）
     * 映射关系：1→🐱, 2→🐈‍⬛, 3→🐈, 4→😺，其余默认 🐱
     * @param {number|string} catId - 猫咪 ID
     * @returns {string} 对应的 emoji 字符
     */
    _getEmoji(catId) { return { 1: '🐱', 2: '🐈‍⬛', 3: '🐈', 4: '😺' }[catId] || '🐱'; },

    /**
     * HTML 特殊字符转义，防止 XSS 攻击（私有方法）
     * 利用浏览器 DOM 的 textContent → innerHTML 机制自动转义
     * @param {string} text - 待转义的文本
     * @returns {string} 转义后的安全 HTML 字符串，空值返回空字符串
     */
    _esc(text) { if (!text) return ''; const d = document.createElement('div'); d.textContent = text; return d.innerHTML; },

    /**
     * 将时间字符串格式化为相对时间显示（私有方法）
     * 规则：
     * - < 1 分钟 → "刚刚"
     * - < 60 分钟 → "X 分钟前"
     * - < 24 小时 → "X 小时前"
     * - < 7 天 → "X 天前"
     * - >= 7 天 → 显示中文日期（如 "2024/1/15"）
     * - 解析失败 → 原样返回
     * @param {string} timeStr - 时间字符串，可被 Date 构造函数解析
     * @returns {string} 格式化后的相对时间文本
     */
    _formatTime(timeStr) {
        if (!timeStr) return '';
        try {
            const d = new Date(timeStr); if (isNaN(d.getTime())) return timeStr;
            const diffMin = Math.floor((Date.now() - d) / 60000);
            if (diffMin < 1) return '刚刚';
            if (diffMin < 60) return `${diffMin} 分钟前`;
            const h = Math.floor(diffMin / 60);
            if (h < 24) return `${h} 小时前`;
            const day = Math.floor(h / 24);
            if (day < 7) return `${day} 天前`;
            return d.toLocaleDateString('zh-CN');
        } catch { return timeStr; }
    }
};

