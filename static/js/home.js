/* 猫迹 CatTrace · 首页交互与 Flask API 接入 */
/**
 * 首页交互逻辑模块
 * 使用 IIFE（立即调用函数表达式）封装，避免全局变量污染
 * 包含猫咪数据管理、投喂功能、领养申请、社区反馈、实时直播等核心业务逻辑
 */
(function () {
    'use strict';

    /**
     * localStorage 存储键名常量
     * @constant {Object}
     * @property {string} token - 用户认证令牌键名
     * @property {string} user - 用户信息键名
     * @property {string} adoption - 领养申请记录键名
     */
    var STORAGE = {
        token: 'cattrace_token',
        user: 'cattrace_user',
        adoption: 'cattrace_adoption'
    };

    /**
     * 投喂档位配置（模拟数据）
     * 每个档位定义价格、标签名称和投喂份数
     * @constant {Array<Object>}
     */
    var FEED_PACKS = [
        { price: 1, label: '爱心单次', amount: 1 },
        { price: 5, label: '轻量守护', amount: 5 },
        { price: 18, label: '周末加餐', amount: 18 },
        { price: 68, label: '整月陪伴', amount: 68 }
    ];

    /**
     * 猫咪性格描述列表（模拟数据）
     * 用于在领养申请卡片中展示 AI 生成的性格标签
     * @constant {Array<string>}
     */
    var PERSONALITIES = [
        '粘人精，喜欢蹭蹭',
        '独立自主，有自己的小世界',
        '活泼好动，精力充沛',
        '温柔安静，适合陪伴',
        '吃货一枚，对食物充满热情',
        '社恐但会偷偷观察你'
    ];

    /**
     * 地图标记点位置坐标（模拟数据）
     * 用于在首页地图区域展示猫咪分布位置，使用 CSS 百分比定位
     * @constant {Array<Object>}
     */
    var MAP_POSITIONS = [
        { top: '26%', left: '18%' },
        { top: '52%', left: '72%' },
        { top: '66%', left: '42%' },
        { top: '18%', left: '63%' },
        { top: '40%', left: '48%' },
        { top: '72%', left: '24%' }
    ];

    /**
     * 领养流程阶段定义（模拟数据）
     * 描述从线上试养到终身关怀的完整领养流程
     * @constant {Array<Object>}
     */
    var ADOPT_STAGES = [
        { name: '线上试养', days: 'D1-D7', icon: '📱', hint: '每日上传进食、饮水、精神短视频，第 7 天志愿者上门初访。' },
        { name: '月度过渡', days: 'D8-D30', icon: '🏠', hint: '每周上传视频并填写行为问卷，第 30 天上门复检。' },
        { name: '稳定期', days: 'D31-D90', icon: '✅', hint: '每月简单反馈，第 90 天终审回访并签署《领养确认书》。' },
        { name: '终身关怀', days: '长期', icon: '💝', hint: '每年健康年报、疫苗与绝育提醒，系统自动推送。' }
    ];

    /**
     * 后备猫咪数据（模拟数据）
     * 当后端 API 不可用时，使用此数据作为降级展示
     * 包含 4 只猫咪的完整信息：基本信息、健康状态、投喂次数等
     * @constant {Array<Object>}
     */
    var FALLBACK_CATS = [
        {
            id: 1, name: '咪咪', nickname: '小区一霸', gender: 'female', age: '2 岁',
            color: '橘白相间', location: 'A 区 - 教学楼后', description: '性格活泼，喜欢晒太阳，经常在教学楼后的小花园出现。',
            feed_count: 160, views: 1235, health: '健康', neutered: true, adoption_ready: false
        },
        {
            id: 2, name: '小黑', nickname: '夜行侠', gender: 'male', age: '1 岁半',
            color: '纯黑', location: 'B 区 - 食堂门口', description: '夜间活跃，白天喜欢躲在车底下，对人比较警惕。',
            feed_count: 90, views: 876, health: '健康', neutered: false, adoption_ready: true
        },
        {
            id: 3, name: '雪球', nickname: '棉花糖', gender: 'female', age: '3 岁',
            color: '纯白', location: 'C 区 - 图书馆前', description: '非常亲人，会主动蹭人，是图书馆的常驻猫咪。',
            feed_count: 236, views: 2157, health: '健康', neutered: true, adoption_ready: true
        },
        {
            id: 4, name: '大橘', nickname: '十斤橘', gender: 'male', age: '4 岁',
            color: '橘色', location: 'D 区 - 操场角落', description: '体重超标，需要控制饮食，但依然很贪吃。',
            feed_count: 312, views: 1890, health: '需关注', neutered: true, adoption_ready: false
        }
    ];

    /**
     * 全局状态对象
     * 管理页面所有运行时数据，是整个首页的核心数据中心
     * @type {Object}
     * @property {Array} cats - 猫咪列表数据
     * @property {Object} stats - 统计数据（总数、投喂数等）
     * @property {Array} notifications - 通知消息列表
     * @property {Array} feedLogs - 投喂记录日志
     * @property {Array} localActivities - 本地活动动态（用户操作产生的记录）
     * @property {number|null} currentCatId - 当前选中猫咪的 ID
     * @property {Object} selectedPack - 当前选中的投喂档位
     * @property {string} filter - 猫咪筛选条件：'all' | 'adoption' | 'neutered'
     * @property {Object|null} user - 当前登录用户信息
     * @property {Object|null} diaryPhoto - 用户上传的猫咪日记照片
     * @property {boolean} usedFallback - 是否使用了后备模拟数据
     */
    var state = {
        cats: [],
        stats: {},
        notifications: [],
        feedLogs: [],
        localActivities: [],
        currentCatId: null,
        selectedPack: FEED_PACKS[0],
        filter: 'all',
        user: null,
        diaryPhoto: null,
        usedFallback: false
    };

    /* ---------- 工具函数 ---------- */

    /**
     * 通过 ID 获取 DOM 元素的快捷方法
     * @param {string} id - 元素的 id 属性值
     * @returns {HTMLElement|null} 对应的 DOM 元素，未找到时返回 null
     */
    function $(id) {
        return document.getElementById(id);
    }

    /**
     * HTML 特殊字符转义，防止 XSS 注入
     * 将 & < > " ' 五种字符替换为对应的 HTML 实体
     * @param {*} value - 需要转义的值，null/undefined 会被转为空字符串
     * @returns {string} 转义后的安全字符串
     */
    function esc(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
        });
    }

    /**
     * 数字格式化，使用中文千分位分隔
     * @param {number} num - 待格式化的数字
     * @returns {string} 格式化后的字符串，如 "1,234"
     */
    function fmt(num) {
        return Number(num || 0).toLocaleString('zh-CN');
    }

    /**
     * 数值限制函数，将数值约束在 [min, max] 范围内
     * @param {number} num - 输入数值
     * @param {number} min - 最小值
     * @param {number} max - 最大值
     * @returns {number} 约束后的数值
     */
    function clamp(num, min, max) {
        return Math.min(max, Math.max(min, num));
    }

    /**
     * 构造认证请求头
     * 从 localStorage 读取令牌，若存在则添加 Bearer 认证头
     * @returns {Object} 包含 Authorization 字段的请求头对象，无令牌时返回空对象
     */
    function authHeaders() {
        var token = localStorage.getItem(STORAGE.token);
        return token ? { Authorization: 'Bearer ' + token } : {};
    }

    /**
     * 封装 GET 请求
     * 自动附加认证头，禁用缓存以确保获取最新数据
     * @param {string} path - 请求路径
     * @returns {Promise<Object>} 解析后的 JSON 响应数据
     * @throws {Error} HTTP 状态码非 2xx 时抛出错误
     */
    async function apiGet(path) {
        var res = await fetch(path, { headers: authHeaders(), cache: 'no-store' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
    }

    /**
     * 封装 POST 请求
     * 自动设置 JSON 内容类型和认证头，请求体序列化为 JSON
     * @param {string} path - 请求路径
     * @param {Object} [payload] - 请求体数据，会被 JSON 序列化
     * @returns {Promise<Object>} 解析后的 JSON 响应数据
     * @throws {Error} HTTP 状态码非 2xx 且无 message 字段时抛出错误
     */
    async function apiPost(path, payload) {
        var headers = Object.assign({ 'Content-Type': 'application/json' }, authHeaders());
        var res = await fetch(path, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload || {})
        });
        var json = {};
        try {
            json = await res.json();
        } catch (err) {
            json = {};
        }
        if (!res.ok && json.message === undefined) {
            throw new Error('HTTP ' + res.status);
        }
        return json;
    }

    /**
     * 根据猫咪毛色返回对应的 emoji 表情
     * 用于在界面中直观地展示猫咪形象
     * @param {string} color - 猫咪毛色描述文本
     * @returns {string} 对应的猫咪 emoji：黑色/灰色/橘色返回 🐈，白色返回 🐱
     */
    function emojiFor(color) {
        var text = String(color || '');
        if (/黑/.test(text)) return '🐈';
        if (/灰|蓝/.test(text)) return '🐈';
        if (/白/.test(text)) return '🐱';
        if (/橘|橙|黄/.test(text)) return '🐈';
        return '🐱';
    }

    /**
     * 将后端原始猫咪数据标准化为前端统一格式
     * 补全默认值、转换字段命名风格（下划线 → 驼峰），并计算衍生属性
     * @param {Object} raw - 后端返回的原始猫咪数据
     * @returns {Object} 标准化后的猫咪对象，包含 id、name、emoji、personality 等字段
     */
    function normalizeCat(raw) {
        var id = Number(raw.id);
        return {
            id: id,
            name: raw.name || '未命名',
            nickname: raw.nickname || '社区新朋友',
            gender: raw.gender === 'female' ? '雌性' : raw.gender === 'male' ? '雄性' : '未知',
            age: raw.age || '未知',
            color: raw.color || '未知毛色',
            location: raw.location || '未知位置',
            desc: raw.description || '暂无简介',
            health: raw.health || '未知',
            neutered: Boolean(raw.neutered),
            adoptionReady: Boolean(raw.adoption_ready),
            adoptionNote: raw.adoption_note || '',
            feedCount: Number(raw.feed_count || 0),
            views: Number(raw.views || 0),
            missingDays: Number(raw.missing_status || 0),
            emoji: emojiFor(raw.color),
            visits: 1 + (id % 4),
            personality: PERSONALITIES[(id * 7) % PERSONALITIES.length]
        };
    }

    /**
     * 获取当前选中的猫咪对象
     * 优先返回 currentCatId 对应的猫咪，若未找到则返回列表中第一只
     * @returns {Object|null} 当前猫咪对象，列表为空时返回 null
     */
    function currentCat() {
        for (var i = 0; i < state.cats.length; i++) {
            if (state.cats[i].id === state.currentCatId) return state.cats[i];
        }
        return state.cats[0] || null;
    }

    /**
     * 根据 ID 查找指定猫咪
     * @param {number|string} id - 猫咪 ID
     * @returns {Object|null} 匹配的猫咪对象，未找到返回 null
     */
    function findCat(id) {
        for (var i = 0; i < state.cats.length; i++) {
            if (state.cats[i].id === Number(id)) return state.cats[i];
        }
        return null;
    }

    /**
     * 将健康状态文本转换为展示标签
     * @param {string} health - 原始健康状态文本
     * @returns {string} 展示用标签：'健康' → '优秀'，含'需'或'关注' → '关注中'
     */
    function healthLabel(health) {
        if (health === '健康') return '优秀';
        if (String(health).indexOf('需') >= 0 || String(health).indexOf('关注') >= 0) return '关注中';
        return health || '--';
    }

    /**
     * 将时间字符串转换为相对时间描述
     * 用于展示投喂记录、通知等的时间戳
     * @param {string} timeStr - ISO 格式时间字符串
     * @returns {string} 相对时间文本：'刚刚'、'X 分钟前'、'X 小时前'、'X 天前' 或具体日期
     */
    function formatRelative(timeStr) {
        var date = new Date(timeStr);
        if (isNaN(date.getTime())) return '--';
        var diff = Date.now() - date.getTime();
        if (diff < 60000) return '刚刚';
        if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前';
        if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前';
        if (diff < 86400000 * 7) return Math.floor(diff / 86400000) + ' 天前';
        return (date.getMonth() + 1) + ' 月 ' + date.getDate() + ' 日';
    }

    /**
     * 将 Date 对象格式化为中文日期文本
     * @param {Date} date - 日期对象
     * @returns {string} 格式如 "10 月 30 日"
     */
    function dateLabel(date) {
        return (date.getMonth() + 1) + ' 月 ' + date.getDate() + ' 日';
    }

    /**
     * 显示 Toast 轻提示
     * 通过操作 #toast 元素的 CSS 类实现淡入淡出效果
     * @param {string} message - 提示文本内容
     * @param {number} [duration=2400] - 显示持续时间（毫秒）
     */
    function showToast(message, duration) {
        var toast = $('toast');
        if (!toast) return;
        clearTimeout(showToast.timer);
        toast.textContent = message;
        toast.classList.add('show');
        showToast.timer = setTimeout(function () {
            toast.classList.remove('show');
        }, duration || 2400);
    }

    /**
     * 打开模态弹窗
     * 将指定 HTML 内容注入弹窗主体区域并显示
     * @param {string} html - 弹窗内 HTML 内容
     * @param {boolean} [wide=false] - 是否使用宽屏样式
     */
    function openModal(html, wide) {
        $('modalCard').classList.toggle('wide', Boolean(wide));
        $('modalBody').innerHTML = html;
        $('modal').classList.add('show');
    }

    /**
     * 关闭模态弹窗
     * 隐藏弹窗容器，清除宽屏样式并清空内容
     */
    function closeModal() {
        $('modal').classList.remove('show');
        $('modalCard').classList.remove('wide');
        $('modalBody').innerHTML = '';
    }

    /**
     * 复制文本到剪贴板
     * 优先使用现代 Clipboard API，降级使用 execCommand('copy')
     * @param {string} text - 需要复制的文本内容
     * @returns {Promise<void>}
     */
    async function copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
            showToast('链接已复制，去分享给朋友吧');
        } catch (err) {
            /* 降级方案：创建临时 textarea 元素，使用旧版 execCommand 复制 */
            var input = document.createElement('textarea');
            input.value = text;
            document.body.appendChild(input);
            input.select();
            try {
                document.execCommand('copy');
                showToast('链接已复制，去分享给朋友吧');
            } catch (e) {
                showToast('复制失败，请手动复制链接');
            }
            document.body.removeChild(input);
        }
    }

    /* ---------------- 渲染函数：负责将 state 数据映射到 DOM ---------------- */

    /**
     * 渲染顶部统计卡片
     * 展示猫咪总数、累计投喂、已绝育数、可领养数四个核心指标
     * 优先使用后端统计数据，降级使用本地猫咪列表计算
     */
    function renderStats() {
        var cats = state.cats;
        var totalCats = state.stats.total_cats != null ? Number(state.stats.total_cats) : cats.length;
        var totalFeeds = state.stats.total_feeds != null
            ? Number(state.stats.total_feeds)
            : cats.reduce(function (sum, cat) { return sum + cat.feedCount; }, 0);
        var neutered = cats.filter(function (cat) { return cat.neutered; }).length;
        var adoptable = cats.filter(function (cat) { return cat.adoptionReady; }).length;
        var neuterPct = cats.length ? Math.round(neutered / cats.length * 100) : 0;

        var cards = [
            { icon: '🐱', iconClass: 'pink', value: totalCats, label: '已建档猫咪', trend: '实时同步' },
            { icon: '🍽', iconClass: 'pink', value: totalFeeds, label: '累计投喂', trend: '实时同步' },
            { icon: '✅', iconClass: 'sage', value: neutered, label: '已绝育', trend: '占比 ' + neuterPct + '%' },
            { icon: '💗', iconClass: 'gold', value: adoptable, label: '可领养', trend: '等待新家' }
        ];

        $('statsRow').innerHTML = cards.map(function (item) {
            return '' +
                '<article class="panel stat-card">' +
                    '<div class="stat-icon ' + item.iconClass + '">' + item.icon + '</div>' +
                    '<div><h4>' + fmt(item.value) + '</h4><p>' + item.label + '</p></div>' +
                    '<div class="stat-trend"><div class="curve"></div><div style="margin-top:6px;">' + item.trend + '</div></div>' +
                '</article>';
        }).join('');
    }

    /**
     * 渲染投喂档位选择区域
     * 生成四个投喂按钮，当前选中档位高亮显示
     * 每次渲染后重新绑定点击事件，点击时切换选中档位并刷新
     * 目标 DOM：#feedPacks
     */
    function renderFeedPacks() {
        if (!$('feedPacks')) return;
        $('feedPacks').innerHTML = FEED_PACKS.map(function (pack) {
            return '' +
                '<button class="feed-pack ' + (pack.price === state.selectedPack.price ? 'active' : '') + '" type="button" data-price="' + pack.price + '">' +
                    '<strong>¥' + pack.price + '</strong>' +
                    '<span>' + pack.label + '</span>' +
                '</button>';
        }).join('');

        Array.prototype.forEach.call(document.querySelectorAll('.feed-pack'), function (btn) {
            btn.addEventListener('click', function () {
                var price = Number(btn.getAttribute('data-price'));
                state.selectedPack = FEED_PACKS.filter(function (pack) { return pack.price === price; })[0] || FEED_PACKS[0];
                renderFeedPacks();
            });
        });
    }

    /**
     * 渲染地图上的猫咪标记点
     * 根据猫咪列表在地图区域生成可点击的标记按钮
     * 已绝育猫咪显示 🏠 图标并使用绿色样式，未绝育显示 🐾
     * 标记位置从 MAP_POSITIONS 循环取值
     * 目标 DOM：#mapMarkers
     */
    function renderMapMarkers() {
        var html = state.cats.map(function (cat, index) {
            var pos = MAP_POSITIONS[index % MAP_POSITIONS.length];
            return '<button type="button" class="marker ' + (cat.neutered ? 'sage' : '') + '" ' +
                'style="top:' + pos.top + ';left:' + pos.left + ';" data-cat="' + cat.id + '" ' +
                'title="' + esc(cat.name) + ' · ' + esc(cat.location) + '">' +
                (cat.neutered ? '🏠' : '🐾') + '</button>';
        }).join('');
        $('mapMarkers').innerHTML = html;
    }

    /**
     * 渲染猫咪实时直播区域
     * 展示当前选中猫咪的直播画面信息，包括位置、浏览量、投喂次数、
     * 环境温湿度、健康状态、AI 识别状态等
     * 目标 DOM：#liveCatTitle, #liveCatLocation, #viewerCount, #liveFeedCount,
     *           #liveTemp, #liveHumidity, #liveHealth, #liveCatEmoji,
     *           #aiStatus, #mapSpotName, #mapSpotDesc
     */
    function renderLive() {
        var cat = currentCat();
        if (!cat) return;
        /* 以下元素在首页精简后已移除，仅存在于 /live 页面，需做 null 检查 */
        var el;
        if ((el = $('liveCatTitle'))) el.textContent = cat.name + '的实时画面';
        if ((el = $('liveCatLocation'))) el.textContent = cat.location + ' · ' + (cat.health === '健康' ? '猫咪状态良好' : '建议持续观察');
        if ((el = $('viewerCount'))) el.textContent = fmt(cat.views) + ' 人浏览';
        if ((el = $('liveFeedCount'))) el.textContent = fmt(cat.feedCount) + ' 次';
        if ((el = $('liveTemp'))) el.textContent = (21.8 + (cat.id % 5) * 0.6).toFixed(1) + '°C';
        if ((el = $('liveHumidity'))) el.textContent = (54 + (cat.id % 6) * 2) + '%';
        if ((el = $('liveHealth'))) el.textContent = healthLabel(cat.health);
        if ((el = $('liveCatEmoji'))) el.textContent = cat.emoji;
        if ((el = $('aiStatus'))) el.textContent = cat.name + ' · AI 已识别';
        if ((el = $('mapSpotName'))) el.textContent = cat.location;
        if ((el = $('mapSpotDesc'))) el.innerHTML = '猫咪数 ' + cat.visits + ' 只<br>累计投喂 ' + fmt(cat.feedCount) + ' 次';
    }

    /**
     * 渲染投喂记录列表
     * 展示最近 4 条投喂日志，包含投喂时间、用户名、猫咪名和份数
     * 无记录时显示空状态提示
     * 目标 DOM：#feedLogs
     */
    function renderFeedLogs() {
        var box = $('feedLogs');
        if (!box) return;
        if (!state.feedLogs.length) {
            box.innerHTML = '<div class="empty-state">暂无投喂记录，来成为第一个投喂的人吧。</div>';
            return;
        }
        box.innerHTML = state.feedLogs.slice(0, 4).map(function (log) {
            var cat = findCat(log.cat_id);
            var name = cat ? cat.name : '猫咪 #' + log.cat_id;
            var amount = Number(log.amount || 1);
            return '' +
                '<div class="log-row">' +
                    '<time>' + formatRelative(log.time) + '</time>' +
                    '<div><strong>' + esc(log.user_name || '爱心用户') + '</strong> 投喂了 ' +
                        '<span style="color:var(--pink-deep);font-weight:700;">' + esc(name) + '</span></div>' +
                    '<span class="muted">' + amount + ' 份猫粮</span>' +
                '</div>';
        }).join('');
    }

    /**
     * 为指定猫咪生成模拟日记条目（模拟数据）
     * 生成最近 3 天的日记数据，包含来访次数、时间段、心情、投喂数和停留时长
     * @param {Object} cat - 猫咪对象
     * @returns {Array<Object>} 日记条目数组，每条包含 label、date、visits、slot、mood、feed、stay
     */
    function diaryEntriesFor(cat) {
        var slots = ['清晨 6 点', '上午 10 点', '下午 3 点', '晚上 10 点'];
        var moods = ['很安心', '有点调皮', '懒洋洋的', '精神很好', '吃得很香'];
        var entries = [];
        for (var i = 0; i <= 2; i++) {
            var date = new Date();
            date.setDate(date.getDate() - i);
            var visits = 1 + ((cat.id + i) % 4);
            entries.push({
                label: i === 0 ? '今天' : i === 1 ? '昨天' : dateLabel(date),
                date: date,
                visits: visits,
                slot: slots[(cat.id + i) % slots.length],
                mood: moods[(cat.id * 2 + i) % moods.length],
                feed: visits * 2,
                stay: visits * 15
            });
        }
        return entries;
    }

    /**
     * 渲染猫咪日记区域
     * 展示当前猫咪的日记条目（今天/昨天/前天）和缩略图列表
     * 若用户上传了照片且匹配当前猫咪，则在缩略图列表最前方插入用户照片
     * 目标 DOM：#diaryCatName, #diaryTime, #diaryEntries, #diaryThumbs
     */
    function renderDiary() {
        var cat = currentCat();
        if (!cat) return;
        $('diaryCatName').textContent = cat.emoji + ' ' + cat.name;
        $('diaryTime').textContent = (8 + (cat.id % 3)) + ':' + (10 + (cat.id * 7) % 40) + ' 进入猫屋';

        var entries = diaryEntriesFor(cat);
        $('diaryEntries').innerHTML = entries.map(function (entry) {
            return '' +
                '<div class="diary-entry">' +
                    '<div class="diary-entry-head"><span>📅 ' + entry.label + '</span><span>' + entry.slot + '</span></div>' +
                    '<p>' + esc(cat.name) + ' 今天来了 ' + entry.visits + ' 次，最喜欢' + entry.slot + '那顿，' +
                        entry.mood + '地吃完，还对着摄像头打了个哈欠。</p>' +
                    '<div class="diary-stats">🍖 投喂 ' + entry.feed + ' 次 · ⏱ 停留 ' + entry.stay + ' 分钟</div>' +
                '</div>';
        }).join('');

        var clips = ['进食', '晒太阳', '巡视', '打盹'];
        var thumbs = clips.map(function (label) {
            return '<div class="thumb" title="' + label + '">' + cat.emoji + '</div>';
        });
        if (state.diaryPhoto && state.diaryPhoto.catId === cat.id) {
            thumbs.unshift('<div class="thumb diary-photo" title="用户共创照片"><img src="' + state.diaryPhoto.url + '" alt="用户上传的猫咪照片"></div>');
        }
        $('diaryThumbs').innerHTML = thumbs.join('');
    }

    /**
     * 生成猫咪标签 HTML 片段
     * 包含绝育状态标签（已绝育/待绝育）、健康状态标签、可领养标签
     * @param {Object} cat - 猫咪对象
     * @returns {string} 标签 HTML 字符串
     */
    function catTagsHtml(cat) {
        var html = '';
        html += '<span class="tag ' + (cat.neutered ? 'ok' : 'warn') + '">' + (cat.neutered ? '已绝育' : '待绝育') + '</span>';
        html += '<span class="tag ' + (cat.health === '健康' ? 'ok' : 'warn') + '">' + esc(cat.health) + '</span>';
        if (cat.adoptionReady) html += '<span class="tag pink">可领养</span>';
        return html;
    }

    /**
     * 生成猫咪卡片完整 HTML
     * 包含猫咪头像、基本信息、标签、投喂次数，可选显示性格描述和领养申请按钮
     * @param {Object} cat - 猫咪对象
     * @param {boolean} withApply - 是否显示"申请领养"按钮和性格描述
     * @returns {string} 卡片 HTML 字符串
     */
    function catCardHtml(cat, withApply) {
        return '' +
            '<article class="cat-card" data-cat="' + cat.id + '">' +
                '<div class="cat-visual">' + cat.emoji + '</div>' +
                '<div class="cat-info">' +
                    '<h4>' + esc(cat.name) + ' <span class="muted" style="font-weight:400;">“' + esc(cat.nickname) + '”</span></h4>' +
                    '<p>' + cat.gender + ' · ' + esc(cat.age) + ' · ' + esc(cat.color) + '</p>' +
                    '<p>📍 ' + esc(cat.location) + '</p>' +
                    '<div class="tags">' + catTagsHtml(cat) + '</div>' +
                    '<div class="cat-points" style="margin-top:8px;">🍖 已投喂 ' + fmt(cat.feedCount) + ' 次</div>' +
                    (withApply ? '<div class="personality">🤖 ' + esc(cat.personality) + '</div>' : '') +
                    (withApply ? '<button class="apply-btn" type="button" data-apply="' + cat.id + '">📝 申请领养</button>' : '') +
                '</div>' +
            '</article>';
    }

    /**
     * 根据当前筛选条件过滤猫咪列表
     * @returns {Array<Object>} 过滤后的猫咪数组
     */
    function filteredCats() {
        if (state.filter === 'adoption') {
            return state.cats.filter(function (cat) { return cat.adoptionReady; });
        }
        if (state.filter === 'neutered') {
            return state.cats.filter(function (cat) { return cat.neutered; });
        }
        return state.cats;
    }

    /**
     * 渲染猫咪档案列表区域
     * 根据筛选条件展示猫咪卡片，并更新计数文本
     * 目标 DOM：#catsCount, #catsGrid
     */
    function renderCats() {
        var list = filteredCats();
        $('catsCount').textContent = '显示 ' + list.length + ' / ' + state.cats.length + ' 只';
        if (!list.length) {
            $('catsGrid').innerHTML = '<div class="empty-state">没有符合筛选条件的猫咪，换个条件试试吧。</div>';
            return;
        }
        $('catsGrid').innerHTML = list.map(function (cat) {
            return catCardHtml(cat, false);
        }).join('');
    }

    /**
     * 渲染可领养猫咪区域
     * 仅展示 adoptionReady 为 true 的猫咪，卡片包含"申请领养"按钮
     * 目标 DOM：#adoptCount, #adoptCats
     */
    function renderAdoptable() {
        var list = state.cats.filter(function (cat) { return cat.adoptionReady; });
        $('adoptCount').textContent = list.length ? list.length + ' 只猫咪等待新家' : '暂无可领养猫咪';
        if (!list.length) {
            $('adoptCats').innerHTML = '<div class="empty-state">暂无可领养的猫咪，请关注后续更新。</div>';
            return;
        }
        $('adoptCats').innerHTML = list.map(function (cat) {
            return catCardHtml(cat, true);
        }).join('');
    }

    /**
     * 渲染投喂排行榜
     * 按投喂次数降序排列，取前 5 名展示，前三名显示奖牌 emoji
     * 目标 DOM：#leaderboardList
     */
    function renderLeaderboard() {
        var list = state.cats.slice().sort(function (a, b) { return b.feedCount - a.feedCount; }).slice(0, 5);
        if (!list.length) {
            $('leaderboardList').innerHTML = '<div class="empty-state">暂无排行数据</div>';
            return;
        }
        var medals = ['🥇', '🥈', '🥉'];
        $('leaderboardList').innerHTML = list.map(function (cat, index) {
            return '' +
                '<div class="leader-row" data-cat="' + cat.id + '">' +
                    '<div class="leader-rank">' + (medals[index] || '#' + (index + 1)) + '</div>' +
                    '<div><span class="leader-name">' + esc(cat.name) + '</span><span class="leader-loc">📍 ' + esc(cat.location) + '</span></div>' +
                    '<div class="leader-score">' + fmt(cat.feedCount) + ' 次</div>' +
                '</div>';
        }).join('');
    }

    /**
     * 合并本地活动动态和 API 通知，生成统一的活动列表
     * 本地活动（用户操作产生）排在前面，API 通知在后，最多返回 5 条
     * @returns {Array<Object>} 活动条目数组，每条含 icon、text、tag、time
     */
    function activityItems() {
        var apiItems = state.notifications.map(function (item) {
            var icon = item.type === 'feed' ? '🍖' : item.type === 'emergency' ? '🚨' : '🔔';
            var tag = item.type === 'feed' ? '投喂' : item.type === 'emergency' ? '紧急' : '系统';
            return {
                icon: icon,
                text: item.message || item.title || '',
                tag: tag,
                time: formatRelative(item.time)
            };
        });
        return state.localActivities.concat(apiItems).slice(0, 8);
    }

    /**
     * 渲染社区动态列表
     * 展示投喂、反馈、通知等活动的混合列表
     * 目标 DOM：#activityList
     */
    function renderActivities() {
        var items = activityItems();
        if (!items.length) {
            $('activityList').innerHTML = '<div class="empty-state">暂无动态，投喂一次就会出现在这里。</div>';
            return;
        }
        $('activityList').innerHTML = items.map(function (item) {
            return '' +
                '<div class="activity-row">' +
                    '<div class="activity-avatar">' + item.icon + '</div>' +
                    '<div style="min-width:0;">' +
                        '<p title="' + esc(item.text) + '">' + esc(item.text) + '</p>' +
                        '<div class="activity-meta">' +
                            '<span class="activity-tag">' + item.tag + '</span>' +
                            '<span class="muted">' + item.time + '</span>' +
                        '</div>' +
                    '</div>' +
                '</div>';
        }).join('');
    }

    /**
     * 渲染通知红点状态
     * 存在未读通知时显示红点，否则隐藏
     * 目标 DOM：#notifyDot
     */
    function renderNotifications() {
        var dot = $('notifyDot');
        if (dot) dot.hidden = !state.notifications.some(function (item) { return !item.read; });
    }

    /**
     * 渲染资源分配流向图
     * 展示已绝育/未绝育猫咪的比例条，用于可视化资源分配策略
     * 目标 DOM：#flowUnneutered, #flowNeutered, #flowRatio
     */
    function renderResourceFlow() {
        var total = state.cats.length;
        var unneutered = state.cats.filter(function (cat) { return !cat.neutered; }).length;
        var unPct = total ? Math.round(unneutered / total * 100) : 0;
        var okPct = total ? 100 - unPct : 0;

        var unEl = $('flowUnneutered');
        var okEl = $('flowNeutered');
        unEl.style.width = unPct + '%';
        okEl.style.width = okPct + '%';
        unEl.textContent = '未绝育 ' + unPct + '%';
        okEl.textContent = '已绝育 ' + okPct + '%';
        $('flowRatio').textContent = '未绝育优先 · ' + unneutered + ' / ' + total + ' 只';
    }

    /**
     * 渲染 AI × IoT 管理概览区域
     * 展示设备同步状态、AI 投喂分析、政府治理反馈三项洞察信息
     * 目标 DOM：#insightDevice, #insightAI, #insightGov
     */
    function renderInsight() {
        var totalFeeds = state.stats.total_feeds != null
            ? Number(state.stats.total_feeds)
            : state.cats.reduce(function (sum, cat) { return sum + cat.feedCount; }, 0);
        var healthAlerts = state.cats.filter(function (cat) { return cat.health !== '健康'; });
        var emergency = state.notifications.filter(function (item) { return item.type === 'emergency'; }).length;

        $('insightDevice').textContent = state.cats.length + ' 个猫咪点位已建档，摄像头、投喂器与环境传感器数据持续同步。';
        $('insightAI').textContent = '累计完成 ' + fmt(totalFeeds) + ' 次投喂记录，' + healthAlerts.length + ' 只猫咪需要持续观察。';
        $('insightGov').textContent = '已收到 ' + emergency + ' 条紧急提醒，社区反馈与治理建议正在跟进。';
    }

    /**
     * 渲染侧边栏摘要信息
     * 展示 AI 识别摘要、设备同步状态和健康提醒
     * 健康提醒分两级：有异常猫咪时显示"轻度健康提醒"（橙色），否则显示"健康状态良好"
     * 目标 DOM：#summaryAI, #summaryDevice, #summaryHealthDot, #summaryHealthTitle, #summaryHealthText
     */
    function renderSidebar() {
        var totalFeeds = state.stats.total_feeds != null
            ? Number(state.stats.total_feeds)
            : state.cats.reduce(function (sum, cat) { return sum + cat.feedCount; }, 0);
        var healthAlerts = state.cats.filter(function (cat) { return cat.health !== '健康'; });

        $('summaryAI').textContent = '已识别 ' + state.cats.length + ' 只猫咪，累计 ' + fmt(totalFeeds) + ' 次投喂记录。';
        $('summaryDevice').textContent = state.cats.length + ' 个点位数据在线，环境传感器持续同步。';

        var dot = $('summaryHealthDot');
        var title = $('summaryHealthTitle');
        var text = $('summaryHealthText');
        if (healthAlerts.length) {
            dot.className = 'dot-status alert';
            title.textContent = '轻度健康提醒';
            text.textContent = healthAlerts.map(function (cat) { return '“' + cat.name + '”' + cat.health; }).join('、') + '，建议继续观察。';
        } else {
            dot.className = 'dot-status';
            title.textContent = '健康状态良好';
            text.textContent = '当前所有猫咪健康记录正常，未发现异常。';
        }
    }

    /**
     * 渲染失踪猫咪横幅警告
     * 当有猫咪连续 7 天以上未出现时显示警告横幅，提示用户上报位置
     * 用户可关闭横幅（通过 state.missingDismissed 标记）
     * 目标 DOM：#missingBanner, #missingBannerText
     */
    function renderMissingBanner() {
        var banner = $('missingBanner');
        var missing = state.cats.filter(function (cat) { return cat.missingDays >= 7; });
        if (!missing.length || state.missingDismissed) {
            banner.hidden = true;
            return;
        }
        var maxDays = Math.max.apply(null, missing.map(function (cat) { return cat.missingDays; }));
        $('missingBannerText').textContent = '“' + missing.map(function (cat) { return cat.name; }).join('、') +
            '” 已 ' + maxDays + ' 天未出现。如果看到它们，请及时上报位置。';
        banner.hidden = false;
    }

    /**
     * 全量渲染所有界面区域
     * 按顺序调用所有 render* 函数，用于初始化和数据刷新后的一次性更新
     */
    function renderAll() {
        renderStats();
        renderFeedPacks();
        renderMapMarkers();
        renderLive();
        renderFeedLogs();
        renderDiary();
        renderCats();
        renderAdoptable();
        renderLeaderboard();
        renderActivities();
        renderNotifications();
        renderResourceFlow();
        renderInsight();
        renderSidebar();
        renderMissingBanner();
        renderAdoptionProgress();
        renderUser();
    }

    /**
     * 渲染用户信息区域
     * 显示用户头像（取昵称首字）和欢迎语，未登录时显示默认文案
     * 目标 DOM：#userAvatar, #userName
     */
    function renderUser() {
        var user = state.user;
        $('userAvatar').textContent = user ? String(user.nickname || '爱').slice(0, 1) : '爱';
        $('userName').textContent = user ? user.nickname : '你好，爱心用户';
    }

    /**
     * 渲染领养进度追踪区域
     * 从 localStorage 读取领养申请记录，展示四阶段进度条（线上试养→月度过渡→稳定期→终身关怀）
     * 无申请记录时显示空状态提示
     * 目标 DOM：#adoptTrackEmpty, #adoptTrackProgress
     */
    function renderAdoptionProgress() {
        var empty = $('adoptTrackEmpty');
        var progress = $('adoptTrackProgress');
        var app = null;
        try {
            app = JSON.parse(localStorage.getItem(STORAGE.adoption) || 'null');
        } catch (err) {
            app = null;
        }
        if (!app) {
            empty.hidden = false;
            progress.hidden = true;
            progress.innerHTML = '';
            return;
        }
        empty.hidden = true;
        progress.hidden = false;
        progress.innerHTML = '' +
            '<p class="muted" style="font-size:0.8rem;line-height:1.6;margin-bottom:8px;">' +
                '已提交 <strong>' + esc(app.catName) + '</strong> 的领养申请，当前处于线上试养审核阶段。' +
            '</p>' +
            '<div class="track-steps">' +
                ADOPT_STAGES.map(function (stage, index) {
                    var cls = index === 0 ? 'active' : '';
                    return '<div class="track-step ' + cls + '">' +
                        '<div class="track-dot">' + stage.icon + '</div>' +
                        '<div class="track-name">' + stage.name + '</div>' +
                        '<div class="track-day">' + stage.days + '</div>' +
                    '</div>';
                }).join('') +
            '</div>' +
            '<p class="track-hint">第 7 天志愿者将上门初访，请保持电话畅通。</p>';
    }

    /* ---------------- 猫咪详情弹窗 / 领养申请 ---------------- */

    /**
     * 生成猫咪失踪响应 SOP（标准操作流程）HTML
     * 根据失踪天数判定响应级别：正常 / 预警(5天) / 正式响应(7天) / 升级响应(14天)
     * 包含判定标准说明、寻猫文案示例和志愿者操作指南
     * @param {Object} cat - 猫咪对象
     * @returns {string} SOP 详情 HTML 字符串
     */
    function missingSopHtml(cat) {
        var days = cat.missingDays;
        var level = days >= 14 ? '升级响应' : days >= 7 ? '正式响应' : days >= 5 ? '预警' : '正常';
        var action = days >= 14
            ? '已结案，标记“失踪 / 离区”'
            : days >= 7
                ? '社区推送寻猫消息 + 志愿者轻量介入'
                : days >= 5
                    ? '内部标记，不推送用户'
                    : '猫咪近期活跃，无需担忧';

        return '' +
            '<table class="sop-table">' +
                '<tr><th>当前状态</th><td>' + (days > 0 ? days + ' 天未出现' : '活跃中') + '</td></tr>' +
                '<tr><th>响应级别</th><td><span class="sop-level ' + (level === '正常' ? '' : 'alert') + '">' + level + '</span></td></tr>' +
                '<tr><th>采取行动</th><td>' + action + '</td></tr>' +
            '</table>' +
            '<div class="sop-note">' +
                '<h4>📋 判定标准</h4>' +
                '<ul>' +
                    '<li><strong>预警：</strong>连续 5 天未出现 → 内部标记</li>' +
                    '<li><strong>正式响应：</strong>连续 7 天未出现 → 社区寻猫推送</li>' +
                    '<li><strong>升级响应：</strong>连续 14 天未出现 → 标记失踪 / 离区</li>' +
                '</ul>' +
                '<h4>🐾 寻猫文案示例</h4>' +
                '<p>🐾 【猫咪失踪提醒】您身边的“' + esc(cat.name) + '”' +
                    (days > 0 ? '已 ' + days + ' 天未出现。' : '近期活跃，状态正常。') +
                    '如果您在小区看到它，请点击上报位置或照片。无需主动搜索，路过时留意即可。</p>' +
                '<h4>🧑‍⚕️ 志愿者操作（轻量）</h4>' +
                '<ul>' +
                    '<li>核实后台目击上报</li>' +
                    '<li>在社区微信群发一次寻猫信息（不刷屏）</li>' +
                    '<li>禁止地毯式搜索</li>' +
                    '<li>每日花 2 分钟查看新目击</li>' +
                '</ul>' +
            '</div>';
    }

    /**
     * 打开猫咪详情弹窗
     * 展示猫咪基本信息、日记、失踪响应三个标签页，底部提供切换直播/投喂/领养操作按钮
     * 弹窗内的标签页切换通过事件委托实现
     * @param {number} catId - 目标猫咪 ID
     */
    function showCatDetail(catId) {
        var cat = findCat(catId);
        if (!cat) return;

        var diaryHtml = diaryEntriesFor(cat).map(function (entry) {
            return '<div class="diary-entry">' +
                '<div class="diary-entry-head"><span>📅 ' + entry.label + '</span><span>' + entry.slot + '</span></div>' +
                '<p>' + esc(cat.name) + ' 今天来了 ' + entry.visits + ' 次，最喜欢' + entry.slot + '那顿，' + entry.mood + '地吃完。</p>' +
                '<div class="diary-stats">🍖 投喂 ' + entry.feed + ' 次 · ⏱ 停留 ' + entry.stay + ' 分钟</div>' +
            '</div>';
        }).join('');

        openModal(
            '<div class="detail-head">' +
                '<div class="detail-avatar">' + cat.emoji + '</div>' +
                '<div>' +
                    '<h2>' + esc(cat.name) + '</h2>' +
                    '<p class="detail-nick">“' + esc(cat.nickname) + '” · ' + cat.gender + ' · ' + esc(cat.age) + '</p>' +
                    '<p class="detail-desc">' + esc(cat.desc) + '</p>' +
                    '<div class="detail-tags">' + catTagsHtml(cat) + '</div>' +
                '</div>' +
            '</div>' +
            '<div class="detail-tabs">' +
                '<button class="detail-tab active" type="button" data-tab="overview">📋 基本信息</button>' +
                '<button class="detail-tab" type="button" data-tab="diary">📖 猫咪日记</button>' +
                '<button class="detail-tab" type="button" data-tab="missing">🔔 失踪响应</button>' +
            '</div>' +
            '<div class="detail-pane" data-pane="overview">' +
                '<div class="insight-grid">' +
                    '<div class="mini-panel"><strong>位置</strong><p>' + esc(cat.location) + '</p></div>' +
                    '<div class="mini-panel"><strong>今日来访</strong><p>' + cat.visits + ' 次，AI 识别稳定。</p></div>' +
                    '<div class="mini-panel"><strong>累计投喂</strong><p>' + fmt(cat.feedCount) + ' 次 · 累计浏览 ' + fmt(cat.views) + ' 次</p></div>' +
                    '<div class="mini-panel"><strong>绝育与领养</strong><p>' + (cat.neutered ? '已绝育' : '待绝育') + ' · ' + (cat.adoptionReady ? '可申请领养' : '暂不可领养') + '</p></div>' +
                '</div>' +
            '</div>' +
            '<div class="detail-pane" data-pane="diary" hidden>' + diaryHtml + '</div>' +
            '<div class="detail-pane" data-pane="missing" hidden>' + missingSopHtml(cat) + '</div>' +
            '<div class="detail-actions">' +
                '<button class="btn btn-primary" type="button" data-act="switch">切换到它的直播</button>' +
                '<button class="btn btn-soft" type="button" data-act="feed">🍖 投喂它</button>' +
                (cat.adoptionReady ? '<button class="btn btn-soft" type="button" data-act="adopt">🏠 申请领养</button>' : '') +
            '</div>'
        );

        var tabs = document.querySelectorAll('.detail-tab');
        var panes = document.querySelectorAll('.detail-pane');
        Array.prototype.forEach.call(tabs, function (tab) {
            tab.addEventListener('click', function () {
                Array.prototype.forEach.call(tabs, function (item) { item.classList.remove('active'); });
                tab.classList.add('active');
                Array.prototype.forEach.call(panes, function (pane) {
                    pane.hidden = pane.getAttribute('data-pane') !== tab.getAttribute('data-tab');
                });
            });
        });

        var actions = $('modalBody').querySelectorAll('[data-act]');
        Array.prototype.forEach.call(actions, function (btn) {
            btn.addEventListener('click', function () {
                var act = btn.getAttribute('data-act');
                if (act === 'switch') {
                    switchCat(cat.id);
                    closeModal();
                    scrollToSection('liveSection');
                } else if (act === 'feed') {
                    switchCat(cat.id);
                    closeModal();
                    scrollToSection('liveSection');
                    feedCurrentCat();
                } else if (act === 'adopt') {
                    openAdoptForm(cat.id);
                }
            });
        });
    }

    /**
     * 计算领养人 AI 匹配评分（模拟算法）
     * 基础分 50，根据领养动机、住房类型、养宠经验累加分数
     * @param {string} reason - 领养动机文本
     * @param {string} housing - 住房类型：'own' | 'rent' | 'dorm' | 'family'
     * @param {string} experience - 养宠经验：'yes' | 'no'
     * @returns {number} 评分，范围 [20, 98]
     */
    function matchScoreFor(reason, housing, experience) {
        var score = 50;
        if (/陪伴|爱/.test(reason)) score += 15;
        if (/救助|流浪/.test(reason)) score += 10;
        if (/责任/.test(reason)) score += 5;
        if (housing === 'own') score += 10;
        if (housing === 'family') score += 5;
        if (experience === 'yes') score += 10;
        return clamp(score, 20, 98);
    }

    /**
     * 打开领养申请表单弹窗
     * 表单包含个人信息、居住情况、养宠经验、承诺确认四个板块
     * 内置 AI 匹配评分实时更新（监听输入变化自动计算）
     * 提交时进行前端校验，通过后调用 /api/adopt/apply 接口
     * 成功后将申请信息存入 localStorage 并刷新领养进度
     * @param {number} catId - 目标猫咪 ID
     */
    function openAdoptForm(catId) {
        var cat = findCat(catId);
        if (!cat) return;
        if (!cat.adoptionReady) {
            showToast(cat.adoptionNote || '该猫咪暂不可领养');
            return;
        }

        openModal(
            '<h2>🏠 领养申请表 · ' + esc(cat.name) + '</h2>' +
            '<p class="modal-sub">提交后进入 D1-D7 线上试养，志愿者将在第 7 天上门初访。</p>' +
            '<form class="adopt-form" id="adoptForm" novalidate>' +
                '<div class="modal-section-title">个人信息</div>' +
                '<div class="form-grid">' +
                    '<label class="field">姓名 *<input id="apName" type="text" maxlength="32" placeholder="请输入真实姓名"></label>' +
                    '<label class="field">年龄 *<input id="apAge" type="number" min="18" max="120" placeholder="需年满 18 周岁"></label>' +
                    '<label class="field">联系电话 *<input id="apPhone" type="tel" maxlength="32" placeholder="方便志愿者联系"></label>' +
                    '<label class="field">电子邮箱<input id="apEmail" type="email" maxlength="128" placeholder="选填"></label>' +
                '</div>' +
                '<div class="modal-section-title">居住情况</div>' +
                '<div class="form-grid">' +
                    '<label class="field">居住类型 *<select id="apHousing"><option value="">请选择</option><option value="own">自有住房</option><option value="rent">租房</option><option value="dorm">宿舍</option><option value="family">与家人同住</option></select></label>' +
                    '<label class="field">住房面积 *<select id="apSize"><option value="">请选择</option><option value="small">50 平米以下</option><option value="medium">50-100 平米</option><option value="large">100 平米以上</option></select></label>' +
                    '<label class="field full">家人是否同意养宠 *<select id="apFamily"><option value="">请选择</option><option value="yes">完全同意</option><option value="partial">部分同意</option><option value="no">不同意</option></select></label>' +
                '</div>' +
                '<div class="modal-section-title">养宠经验</div>' +
                '<div class="form-grid">' +
                    '<label class="field">是否有养宠经验 *<select id="apExp"><option value="">请选择</option><option value="yes">有</option><option value="no">无</option></select></label>' +
                    '<label class="field">之前养过什么宠物<input id="apPets" type="text" maxlength="128" placeholder="如：猫、狗等"></label>' +
                    '<label class="field full">养宠动机 *<textarea id="apReason" maxlength="800" rows="3" placeholder="请简述您想领养猫咪的原因…"></textarea></label>' +
                '</div>' +
                '<div class="match-box">' +
                    '<div class="match-head"><span>🤖 AI 匹配评分</span><strong id="matchScore">--</strong></div>' +
                    '<div class="match-bar"><div class="match-fill" id="matchFill"></div></div>' +
                    '<p class="match-text" id="matchText">填写居住情况、养宠经验与动机后自动计算。</p>' +
                '</div>' +
                '<div class="modal-section-title">承诺确认</div>' +
                '<div class="checkbox-group">' +
                    '<label class="checkbox-label"><input id="ckTerms" type="checkbox"> 我承诺以上信息真实有效，并遵守领养须知中的所有条款</label>' +
                    '<label class="checkbox-label"><input id="ckNeuter" type="checkbox"> 我同意为领养猫咪进行绝育手术（如尚未绝育）</label>' +
                    '<label class="checkbox-label"><input id="ckDeposit" type="checkbox"> 我知悉需支付 300 元可退还保障金，D+30 回访通过后退还</label>' +
                    '<label class="checkbox-label"><input id="ckChain" type="checkbox"> 我同意签署电子领养协议，数据通过区块链存证</label>' +
                '</div>' +
                '<div class="modal-actions">' +
                    '<button class="btn btn-soft" type="button" data-close>取消</button>' +
                    '<button class="btn btn-primary" type="submit">提交申请</button>' +
                '</div>' +
            '</form>',
            true
        );

        var form = $('adoptForm');
        var reason = $('apReason');
        var housing = $('apHousing');
        var experience = $('apExp');
        var scoreEl = $('matchScore');
        var fillEl = $('matchFill');
        var textEl = $('matchText');

        function updateMatch() {
            var hasInput = reason.value.trim() || housing.value || experience.value;
            if (!hasInput) {
                scoreEl.textContent = '--';
                fillEl.style.width = '0%';
                textEl.textContent = '填写居住情况、养宠经验与动机后自动计算。';
                return;
            }
            var score = matchScoreFor(reason.value, housing.value, experience.value);
            scoreEl.textContent = score + '/100';
            fillEl.style.width = score + '%';
            if (score >= 80) {
                textEl.textContent = '✨ 匹配度优秀，您很可能是理想的领养人。';
                fillEl.style.background = 'linear-gradient(90deg, var(--sage), #b5caaf)';
            } else if (score >= 60) {
                textEl.textContent = '👍 匹配度良好，建议完善养宠知识储备。';
                fillEl.style.background = 'linear-gradient(90deg, var(--gold), #f6dfbd)';
            } else {
                textEl.textContent = '📚 匹配度较低，建议先学习养宠知识或参与云养猫。';
                fillEl.style.background = 'linear-gradient(90deg, var(--pink), #e3a5b8)';
            }
        }

        [reason, housing, experience].forEach(function (el) {
            el.addEventListener('input', updateMatch);
            el.addEventListener('change', updateMatch);
        });
        updateMatch();

        form.addEventListener('submit', async function (event) {
            event.preventDefault();
            var name = $('apName').value.trim();
            var age = Number($('apAge').value);
            var phone = $('apPhone').value.trim();
            var adoptionReason = reason.value.trim();

            if (!name || !phone || !adoptionReason) {
                showToast('请填写姓名、电话与领养动机');
                return;
            }
            if (!age || age < 18 || age > 120) {
                showToast('年龄需为 18-120 之间');
                return;
            }
            if (!housing.value || !$('apSize').value || !$('apFamily').value || !experience.value) {
                showToast('请完整填写居住情况与养宠经验');
                return;
            }
            if (!$('ckTerms').checked || !$('ckNeuter').checked || !$('ckDeposit').checked || !$('ckChain').checked) {
                showToast('请勾选全部承诺条款');
                return;
            }

            var applicant = {
                name: name,
                age: age,
                phone: phone,
                email: $('apEmail').value.trim(),
                housingType: housing.value,
                housingSize: $('apSize').value,
                familyAgree: $('apFamily').value,
                petExperience: experience.value,
                previousPets: $('apPets').value.trim(),
                adoptionReason: adoptionReason
            };

            var submitBtn = form.querySelector('[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = '提交中…';
            var result;
            try {
                result = await apiPost('/api/adopt/apply', { cat_id: cat.id, applicant: applicant });
            } catch (err) {
                result = { success: false, message: '网络异常，请稍后重试' };
            }
            submitBtn.disabled = false;
            submitBtn.textContent = '提交申请';

            if (result.success) {
                localStorage.setItem(STORAGE.adoption, JSON.stringify({
                    catId: cat.id,
                    catName: cat.name,
                    applicant: name,
                    time: Date.now()
                }));
                showToast('✅ ' + (result.message || '领养申请已提交'));
                closeModal();
                renderAdoptionProgress();
            } else {
                showToast('❌ ' + (result.message || '提交失败，请稍后重试'));
            }
        });
    }

    /**
     * 打开领养须知弹窗
     * 展示领养条件、绝育要求、保障金、区块链存证等须知条款
     */
    function openAdoptNotice() {
        openModal(
            '<h2>⚠️ 领养须知</h2>' +
            '<p class="modal-sub">让救助、绝育、领养形成温柔闭环。</p>' +
            '<ul class="sop-note" style="padding-left:18px;display:grid;gap:8px;">' +
                '<li>领养人需年满 18 周岁，有稳定住所和收入。</li>' +
                '<li>需同意为猫咪绝育、定期体检、接种疫苗。</li>' +
                '<li>承诺科学喂养，不虐待、不弃养。</li>' +
                '<li>接受领养后的定期回访（D7 / D30 / D90）。</li>' +
                '<li>如无法继续饲养，需联系平台协助重新安置。</li>' +
                '<li>💰 <strong>可退还保障金：</strong>领养时支付 300 元，D+30 回访通过后全额退还。</li>' +
                '<li>🔗 <strong>区块链存证：</strong>签署电子领养协议（含绝育条款），数据上链不可篡改。</li>' +
            '</ul>' +
            '<div class="modal-actions"><button class="btn btn-primary" type="button" data-close>我知道了</button></div>'
        );
    }

    /* ---------------- 弹窗功能：分享 / 投诉 / 通知 / 登录 ---------------- */

    /**
     * 打开分享弹窗
     * 提供微信、微博、复制链接三种分享方式，展示当前直播间链接
     */
    function openShareModal() {
        var cat = currentCat();
        var link = window.location.href;
        openModal(
            '<h2>📤 分享直播间</h2>' +
            '<p class="modal-sub">把“' + esc(cat ? cat.name : '猫咪') + '”的实时画面分享给朋友。</p>' +
            '<div class="form-grid">' +
                '<button class="btn btn-soft" type="button" data-share="wechat">💬 微信</button>' +
                '<button class="btn btn-soft" type="button" data-share="weibo">📢 微博</button>' +
                '<button class="btn btn-soft" type="button" data-share="copy">🔗 复制链接</button>' +
                '<button class="btn btn-soft" type="button" data-close>关闭</button>' +
            '</div>' +
            '<label class="field full" style="margin-top:14px;">直播间链接' +
                '<input type="text" value="' + esc(link) + '" readonly>' +
            '</label>'
        );
    }

    /**
     * 打开社区投诉/建议弹窗
     * 表单包含关联猫咪、问题类型、问题描述、是否紧急等字段
     * 提交后调用 /api/report 接口，成功时将反馈加入本地活动列表并刷新
     */
    function openReportModal() {
        var options = state.cats.map(function (cat) {
            return '<option value="' + cat.id + '">' + esc(cat.name) + ' · ' + esc(cat.location) + '</option>';
        }).join('');

        openModal(
            '<h2>📝 提交社区投诉 / 建议</h2>' +
            '<p class="modal-sub">投诉提交后将自动生成治理建议，7 天反馈、14 天结案。</p>' +
            '<form id="reportForm">' +
                '<div class="form-grid">' +
                    '<label class="field">关联猫咪<select id="reportCat">' + options + '</select></label>' +
                    '<label class="field">问题类型<select id="reportType">' +
                        '<option value="other">其他</option>' +
                        '<option value="noise">夜间猫叫扰民</option>' +
                        '<option value="gathering">猫群聚集</option>' +
                        '<option value="hygiene">环境卫生</option>' +
                        '<option value="abuse">疑似伤害 / 虐待</option>' +
                    '</select></label>' +
                    '<label class="field full">问题描述<textarea id="reportText" maxlength="500" rows="4" placeholder="请描述您遇到的问题或建议，例如夜间猫叫扰民、猫群聚集等"></textarea></label>' +
                '</div>' +
                '<label class="checkbox-label" style="margin-top:10px;"><input id="reportEmergency" type="checkbox"> 标记为紧急事件，同步通知志愿者</label>' +
                '<div class="modal-actions">' +
                    '<button class="btn btn-soft" type="button" data-close>取消</button>' +
                    '<button class="btn btn-primary" type="submit">提交</button>' +
                '</div>' +
            '</form>'
        );

        $('reportForm').addEventListener('submit', async function (event) {
            event.preventDefault();
            var description = $('reportText').value.trim();
            if (!description) {
                showToast('请填写问题描述');
                return;
            }
            var payload = {
                cat_id: Number($('reportCat').value),
                report_type: $('reportType').value,
                description: description,
                reporter_name: state.user ? state.user.nickname : '社区居民',
                is_emergency: $('reportEmergency').checked
            };
            var submitBtn = event.target.querySelector('[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = '提交中…';
            var result;
            try {
                result = await apiPost('/api/report', payload);
            } catch (err) {
                result = { success: false, message: '网络异常，请稍后重试' };
            }
            submitBtn.disabled = false;
            submitBtn.textContent = '提交';
            if (result.success) {
                state.localActivities.unshift({
                    icon: payload.is_emergency ? '🚨' : '📝',
                    text: '你提交了社区' + (payload.is_emergency ? '紧急' : '') + '反馈：' + description,
                    tag: '社区',
                    time: '刚刚'
                });
                showToast(payload.is_emergency
                    ? '🚨 紧急反馈已提交，志愿者将尽快跟进'
                    : '✅ 反馈已提交，系统将生成治理建议');
                closeModal();
                renderActivities();
                loadNotifications();
            } else {
                showToast('❌ ' + (result.message || '提交失败'));
            }
        });
    }

    /**
     * 打开消息通知弹窗
     * 展示所有通知列表（投喂/紧急/系统），打开后自动将所有通知标记为已读
     */
    function openNotificationsModal() {
        var items = state.notifications;
        var html = items.map(function (item) {
            var icon = item.type === 'feed' ? '🍖' : item.type === 'emergency' ? '🚨' : '🔔';
            return '' +
                '<div class="notification-item ' + (item.read ? '' : 'unread') + '">' +
                    '<div class="notification-icon">' + icon + '</div>' +
                    '<div class="notification-copy"><strong>' + esc(item.title || '通知') + '</strong><p>' + esc(item.message || '') + '</p></div>' +
                    '<div class="notification-time">' + formatRelative(item.time) + '</div>' +
                '</div>';
        }).join('');

        openModal(
            '<h2>🔔 消息通知</h2>' +
            '<p class="modal-sub">投喂、求助与社区反馈会实时汇总到这里。</p>' +
            '<div class="notification-list">' + (html || '<div class="empty-state">暂无新消息</div>') + '</div>' +
            '<div class="modal-actions"><button class="btn btn-primary" type="button" data-close>知道了</button></div>'
        );

        state.notifications.forEach(function (item) { item.read = true; });
        renderNotifications();
    }

    /**
     * 打开登录/用户信息弹窗
     * 两种状态：
     * - 已登录：展示用户信息（手机号、积分、投喂次数），提供退出登录按钮
     * - 未登录：展示手机号+验证码登录表单，提交后调用 /api/auth/login 接口
     *   登录成功后将 token 和用户信息存入 localStorage 并刷新界面
     */
    function openLoginModal() {
        if (state.user) {
            openModal(
                '<h2>👤 我的账号</h2>' +
                '<p class="modal-sub">当前以“' + esc(state.user.nickname) + '”的身份参与守护。</p>' +
                '<div class="insight-grid">' +
                    '<div class="mini-panel"><strong>手机号</strong><p>' + esc(state.user.phone || '未绑定') + '</p></div>' +
                    '<div class="mini-panel"><strong>积分</strong><p>' + fmt(state.user.points || 0) + ' 分</p></div>' +
                    '<div class="mini-panel"><strong>投喂次数</strong><p>' + fmt(state.user.feed_count || 0) + ' 次</p></div>' +
                '</div>' +
                '<div class="modal-actions">' +
                    '<button class="btn btn-soft" type="button" data-logout>退出登录</button>' +
                    '<button class="btn btn-primary" type="button" data-close>继续守护</button>' +
                '</div>'
            );
            return;
        }

        openModal(
            '<h2>👤 登录 / 注册</h2>' +
            '<p class="modal-sub">手机号 + 验证码登录，测试验证码为 8888。</p>' +
            '<form id="loginForm">' +
                '<div class="form-grid">' +
                    '<label class="field full">手机号<input id="loginPhone" type="tel" inputmode="numeric" maxlength="11" placeholder="请输入 11 位手机号"></label>' +
                    '<label class="field full">验证码<input id="loginCode" type="text" inputmode="numeric" maxlength="6" placeholder="测试验证码 8888"></label>' +
                '</div>' +
                '<div class="modal-actions">' +
                    '<button class="btn btn-soft" type="button" data-close>取消</button>' +
                    '<button class="btn btn-primary" type="submit">登录</button>' +
                '</div>' +
            '</form>'
        );

        $('loginForm').addEventListener('submit', async function (event) {
            event.preventDefault();
            var phone = $('loginPhone').value.trim();
            var code = $('loginCode').value.trim();
            var submitBtn = event.target.querySelector('[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = '登录中…';
            var result;
            try {
                result = await apiPost('/api/auth/login', { phone: phone, code: code });
            } catch (err) {
                result = { success: false, message: '网络异常，请稍后重试' };
            }
            submitBtn.disabled = false;
            submitBtn.textContent = '登录';
            if (result.success && result.user) {
                state.user = result.user;
                localStorage.setItem(STORAGE.token, result.token || '');
                localStorage.setItem(STORAGE.user, JSON.stringify(result.user));
                renderUser();
                closeModal();
                showToast('👋 欢迎回来，' + result.user.nickname);
            } else {
                showToast('❌ ' + (result.message || '登录失败'));
            }
        });
    }

    /* ---------------- 用户行为与交互逻辑 ---------------- */

    /**
     * 平滑滚动到指定页面区域
     * @param {string} id - 目标区域的 DOM id
     */
    function scrollToSection(id) {
        var section = document.getElementById(id);
        if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    /**
     * 切换当前选中猫咪
     * 更新 currentCatId 并重新渲染直播区域和日记区域
     * @param {number} catId - 目标猫咪 ID
     */
    function switchCat(catId) {
        var cat = findCat(catId);
        if (!cat) return;
        state.currentCatId = cat.id;
        renderLive();
        renderDiary();
    }

    /**
     * 为直播区域的猫咪 emoji 添加弹跳动画
     * 通过添加/移除 CSS 类 'bounce' 实现 260ms 的缩放动效
     * 目标 DOM：#liveCatEmoji
     */
    function animateLiveCat() {
        var emoji = $('liveCatEmoji');
        emoji.classList.add('bounce');
        setTimeout(function () { emoji.classList.remove('bounce'); }, 260);
    }

    /**
     * 执行投喂操作
     * 1. 播放猫咪弹跳动画
     * 2. 调用 /api/feed 接口提交投喂请求
     * 3. 接口成功时更新猫咪投喂次数；失败时本地累加（离线容错）
     * 4. 将投喂记录加入本地活动列表
     * 5. 刷新所有受影响的界面区域
     * 6. 异步拉取最新统计、投喂记录和通知
     * @returns {Promise<void>}
     */
    async function feedCurrentCat() {
        var cat = currentCat();
        if (!cat) return;
        var pack = state.selectedPack;
        animateLiveCat();

        var result;
        try {
            result = await apiPost('/api/feed', {
                cat_id: cat.id,
                user_name: state.user ? state.user.nickname : '爱心用户',
                amount: pack.amount
            });
        } catch (err) {
            result = { success: false, message: '接口暂不可用' };
        }

        var amount = pack.amount;
        if (result.success) {
            cat.feedCount = Number(result.feed_count != null ? result.feed_count : cat.feedCount + amount);
            showToast('已为 ' + cat.name + ' 投喂 ' + amount + ' 份 · ' + pack.label);
        } else {
            cat.feedCount += amount;
            state.stats.total_feeds = Number(state.stats.total_feeds || 0) + amount;
            showToast((result.message || '接口暂不可用') + '，已本地记录这次投喂');
        }

        state.localActivities.unshift({
            icon: '🍖',
            text: '你为“' + cat.name + '”投喂了 ' + pack.label + '（' + amount + ' 份）',
            tag: '投喂',
            time: '刚刚'
        });
        if (state.localActivities.length > 8) state.localActivities.length = 8;

        renderLive();
        renderStats();
        renderCats();
        renderAdoptable();
        renderLeaderboard();
        renderActivities();
        renderSidebar();
        renderInsight();

        await Promise.allSettled([refreshStats(), loadFeedLogs(), loadNotifications()]);
    }

    /**
     * 从后端刷新统计数据
     * 调用 /api/stats 获取最新统计，成功后重新渲染统计、侧边栏和概览区域
     * 失败时保持现有数据不变
     * @returns {Promise<void>}
     */
    async function refreshStats() {
        try {
            var stats = await apiGet('/api/stats');
            if (stats && typeof stats === 'object') {
                state.stats = stats;
                renderStats();
                renderSidebar();
                renderInsight();
            }
        } catch (err) {
            /* 保持现有数据 */
        }
    }

    /**
     * 从后端加载投喂记录
     * 调用 /api/feed-logs 获取最近 6 条记录，失败时保持现有数据
     * @returns {Promise<void>}
     */
    async function loadFeedLogs() {
        try {
            var logs = await apiGet('/api/feed-logs?limit=6');
            state.feedLogs = Array.isArray(logs) ? logs : [];
        } catch (err) {
            if (!state.feedLogs.length) state.feedLogs = [];
        }
        renderFeedLogs();
    }

    /**
     * 从后端加载通知列表
     * 调用 /api/notifications 获取通知，成功后刷新红点、动态和概览区域
     * @returns {Promise<void>}
     */
    async function loadNotifications() {
        try {
            var list = await apiGet('/api/notifications');
            state.notifications = Array.isArray(list) ? list : [];
        } catch (err) {
            state.notifications = state.notifications || [];
        }
        renderNotifications();
        renderActivities();
        renderInsight();
    }

    /**
     * 从 localStorage 恢复用户登录状态
     * 解析存储的用户信息 JSON，若数据无效则设为 null
     */
    function restoreUser() {
        var user = null;
        try {
            user = JSON.parse(localStorage.getItem(STORAGE.user) || 'null');
        } catch (err) {
            user = null;
        }
        state.user = user && user.nickname ? user : null;
    }

    /**
     * 绑定所有静态事件监听器
     * 包括：投喂按钮、导航按钮、搜索框、筛选器、猫咪卡片点击、地图标记点击、
     * 排行榜点击、照片上传、弹窗关闭、键盘快捷键（ESC 关闭弹窗）、
     * 直播卡片跳转、分享/投诉/通知/登录按钮等
     */
    function bindStaticEvents() {
        if ($('feedBtn')) $('feedBtn').addEventListener('click', feedCurrentCat);

        $('heroFeedBtn').addEventListener('click', function () {
            scrollToSection('liveSection');
            showToast('已带你到云直播和投喂区域');
        });
        $('heroLearnBtn').addEventListener('click', function () {
            scrollToSection('insightSection');
            showToast('已跳转到 AI × IoT 管理概览');
        });
        $('viewCatBtn').addEventListener('click', function () {
            if (state.currentCatId) showCatDetail(state.currentCatId);
        });
        if ($('catInfoBtn')) $('catInfoBtn').addEventListener('click', function () {
            if (state.currentCatId) showCatDetail(state.currentCatId);
        });
        $('diaryRefreshBtn').addEventListener('click', function () {
            if (!state.cats.length) return;
            var index = state.cats.findIndex(function (cat) { return cat.id === state.currentCatId; });
            var next = state.cats[(index + 1) % state.cats.length];
            switchCat(next.id);
            showToast('已刷新猫咪动态');
        });
        $('notifyBtn').addEventListener('click', openNotificationsModal);
        $('loginBtn').addEventListener('click', openLoginModal);
        $('mapLiveBtn').addEventListener('click', function () {
            scrollToSection('liveSection');
            showToast('已定位到当前猫屋直播');
        });
        if ($('shareLiveBtn')) $('shareLiveBtn').addEventListener('click', openShareModal);
        $('openReportBtn').addEventListener('click', openReportModal);
        $('adoptNoticeBtn').addEventListener('click', openAdoptNotice);
        $('adoptNoticeBtn2').addEventListener('click', openAdoptNotice);
        $('missingBannerClose').addEventListener('click', function () {
            state.missingDismissed = true;
            $('missingBanner').hidden = true;
        });

        $('closeModalBtn').addEventListener('click', closeModal);
        $('modal').addEventListener('click', function (event) {
            if (event.target === $('modal')) closeModal();
        });
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') closeModal();
        });

        $('searchInput').addEventListener('keydown', function (event) {
            if (event.key !== 'Enter') return;
            var keyword = event.target.value.trim();
            if (!keyword) {
                showToast('请输入猫咪或猫屋关键词');
                return;
            }
            var hit = state.cats.filter(function (cat) {
                return cat.name.indexOf(keyword) >= 0 ||
                    cat.nickname.indexOf(keyword) >= 0 ||
                    cat.location.indexOf(keyword) >= 0;
            })[0];
            if (hit) {
                switchCat(hit.id);
                scrollToSection('liveSection');
                showToast('找到 ' + hit.name + '，已切换到对应信息');
            } else {
                showToast('没有找到“' + keyword + '”，可以试试“雪球”或“图书馆”');
            }
        });

        Array.prototype.forEach.call(document.querySelectorAll('#menu button'), function (btn) {
            btn.addEventListener('click', function () {
                Array.prototype.forEach.call(document.querySelectorAll('#menu button'), function (item) {
                    item.classList.remove('active');
                });
                btn.classList.add('active');
                scrollToSection(btn.getAttribute('data-target'));
            });
        });

        /* 直播卡片点击入口：跳转到 /live，排除内部按钮/链接点击 */
        Array.prototype.forEach.call(document.querySelectorAll('[data-live-entry]'), function (card) {
            card.addEventListener('click', function (e) {
                var tag = (e.target.tagName || '').toUpperCase();
                if (tag === 'BUTTON' || tag === 'A' || tag === 'INPUT' || e.target.closest('button') || e.target.closest('a')) return;
                window.location.href = '/live';
            });
        });

        $('catsFilter').addEventListener('click', function (event) {
            var chip = event.target.closest('.filter-chip');
            if (!chip) return;
            state.filter = chip.getAttribute('data-filter');
            Array.prototype.forEach.call(document.querySelectorAll('#catsFilter .filter-chip'), function (item) {
                item.classList.remove('active');
            });
            chip.classList.add('active');
            renderCats();
        });

        $('catsGrid').addEventListener('click', function (event) {
            var card = event.target.closest('.cat-card');
            if (card) showCatDetail(Number(card.getAttribute('data-cat')));
        });

        $('adoptCats').addEventListener('click', function (event) {
            var applyBtn = event.target.closest('[data-apply]');
            if (applyBtn) {
                event.stopPropagation();
                openAdoptForm(Number(applyBtn.getAttribute('data-apply')));
                return;
            }
            var card = event.target.closest('.cat-card');
            if (card) showCatDetail(Number(card.getAttribute('data-cat')));
        });

        $('mapMarkers').addEventListener('click', function (event) {
            var marker = event.target.closest('[data-cat]');
            if (!marker) return;
            switchCat(Number(marker.getAttribute('data-cat')));
            scrollToSection('liveSection');
        });

        $('leaderboardList').addEventListener('click', function (event) {
            var row = event.target.closest('[data-cat]');
            if (!row) return;
            switchCat(Number(row.getAttribute('data-cat')));
            scrollToSection('liveSection');
        });

        $('joinSection').addEventListener('click', function (event) {
            var item = event.target.closest('[data-action]');
            if (item) handleJoinAction(item.getAttribute('data-action'));
        });
        $('joinSection').addEventListener('keydown', function (event) {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            var item = event.target.closest('[data-action]');
            if (item) {
                event.preventDefault();
                handleJoinAction(item.getAttribute('data-action'));
            }
        });

        $('uploadPhotoBtn').addEventListener('click', function () {
            $('diaryUpload').click();
        });
        $('diaryUpload').addEventListener('change', function (event) {
            var file = event.target.files && event.target.files[0];
            if (!file) return;
            if (!/^image\//.test(file.type)) {
                showToast('请选择图片文件');
                return;
            }
            if (state.diaryPhoto && state.diaryPhoto.url) {
                URL.revokeObjectURL(state.diaryPhoto.url);
            }
            state.diaryPhoto = {
                catId: state.currentCatId,
                url: URL.createObjectURL(file)
            };
            renderDiary();
            var cat = currentCat();
            if (cat) {
                state.localActivities.unshift({
                    icon: '📷',
                    text: '你上传的照片经 AI 识别匹配到“' + cat.name + '”，已加入猫咪日记',
                    tag: '共创',
                    time: '刚刚'
                });
                renderActivities();
                showToast('AI 识别完成：照片已加入“' + cat.name + '”的日记');
            }
            event.target.value = '';
        });

        $('modalBody').addEventListener('click', function (event) {
            var close = event.target.closest('[data-close]');
            if (close) {
                closeModal();
                return;
            }
            var copy = event.target.closest('[data-copy]');
            if (copy) {
                copyText(window.location.href);
                return;
            }
            var share = event.target.closest('[data-share]');
            if (share) {
                var platform = share.getAttribute('data-share');
                if (platform === 'copy') {
                    copyText(window.location.href);
                } else {
                    showToast('请复制直播间链接后分享到' + (platform === 'wechat' ? '微信' : '微博'));
                }
                return;
            }
            var logout = event.target.closest('[data-logout]');
            if (logout) {
                localStorage.removeItem(STORAGE.token);
                localStorage.removeItem(STORAGE.user);
                state.user = null;
                renderUser();
                closeModal();
                showToast('已退出登录');
            }
        });
    }

    /**
     * 处理"参与守护"区域的操作按钮点击
     * @param {string} action - 操作类型：'feed'（投喂）| 'adopt'（领养）| 'volunteer'（志愿者）
     * - feed：滚动到直播投喂区域
     * - adopt：滚动到领养区域
     * - volunteer：弹出志愿者招募说明弹窗
     */
    function handleJoinAction(action) {
        if (action === 'feed') {
            scrollToSection('liveSection');
            showToast('选择投喂档位，就能远程送出猫粮');
        } else if (action === 'adopt') {
            scrollToSection('adoptSection');
            showToast('先看看待领养猫咪，再提交申请');
        } else if (action === 'volunteer') {
            openModal(
                '<h2>🤝 加入志愿者</h2>' +
                '<p class="modal-sub">志愿者参与夜间巡查、投喂记录核实与领养回访。</p>' +
                '<ul class="sop-note" style="padding-left:18px;display:grid;gap:8px;">' +
                    '<li>每周至少参与 1 次巡查或回访</li>' +
                    '<li>发现异常时通过社区共治中心提交反馈</li>' +
                    '<li>遵守“不捕捉、不驱赶、不遗弃”的原则</li>' +
                '</ul>' +
                '<div class="modal-actions"><button class="btn btn-primary" type="button" data-close>我知道了</button></div>'
            );
        }
    }

    /* ---------------- 初始化流程 ---------------- */

    /**
     * 并行加载所有初始数据
     * 同时请求猫咪列表、统计数据、通知列表、投喂记录四个接口
     * 任一接口失败不影响其他数据加载（使用 Promise.allSettled）
     * 猫咪列表失败时降级使用 FALLBACK_CATS 模拟数据
     * @returns {Promise<void>}
     */
    async function loadData() {
        var results = await Promise.allSettled([
            apiGet('/api/cats'),
            apiGet('/api/stats'),
            apiGet('/api/notifications'),
            apiGet('/api/feed-logs?limit=6')
        ]);

        var cats = results[0].status === 'fulfilled' ? results[0].value : null;
        var stats = results[1].status === 'fulfilled' ? results[1].value : null;
        var notifications = results[2].status === 'fulfilled' ? results[2].value : null;
        var logs = results[3].status === 'fulfilled' ? results[3].value : null;

        if (Array.isArray(cats) && cats.length) {
            state.cats = cats.map(normalizeCat);
        } else {
            state.cats = FALLBACK_CATS.map(normalizeCat);
            state.usedFallback = true;
        }

        if (stats && typeof stats === 'object' && stats.total_feeds != null) {
            state.stats = stats;
        } else {
            state.stats = {
                total_cats: state.cats.length,
                total_feeds: state.cats.reduce(function (sum, cat) { return sum + cat.feedCount; }, 0),
                total_views: state.cats.reduce(function (sum, cat) { return sum + cat.views; }, 0),
                active_users: 42
            };
        }

        state.notifications = Array.isArray(notifications) ? notifications : [];
        state.feedLogs = Array.isArray(logs) ? logs : [];
    }

    /**
     * 应用初始化入口
     * 执行顺序：
     * 1. 恢复用户登录状态（从 localStorage）
     * 2. 绑定所有事件监听器
     * 3. 加载后端数据（失败时降级为模拟数据）
     * 4. 默认选中第一只猫咪
     * 5. 全量渲染界面
     * 6. 若使用了模拟数据则弹出提示
     * @returns {Promise<void>}
     */
    async function init() {
        restoreUser();
        bindStaticEvents();
        try {
            await loadData();
        } catch (err) {
            state.cats = FALLBACK_CATS.map(normalizeCat);
            state.stats = {
                total_cats: state.cats.length,
                total_feeds: state.cats.reduce(function (sum, cat) { return sum + cat.feedCount; }, 0),
                total_views: 0,
                active_users: 0
            };
            state.usedFallback = true;
        }

        if (state.cats.length) {
            state.currentCatId = state.cats[0].id;
        }

        renderAll();

        if (state.usedFallback) {
            showToast('接口暂不可用，已切换为演示数据', 3600);
        }

        /* === 返回顶部按钮逻辑 === */
        /* 监听滚动事件，滚动超过 100px 时显示按钮 */
        /* 点击按钮后平滑滚动到页面顶部 */
        var backToTopBtn = document.getElementById('backToTop');
        if (backToTopBtn) {
            /* 滚动监听：判断是否显示返回顶部按钮 */
            window.addEventListener('scroll', function () {
                if (window.scrollY > 100) {
                    backToTopBtn.classList.add('show');
                } else {
                    backToTopBtn.classList.remove('show');
                }
            });

            /* 点击事件：平滑滚动到顶部 */
            backToTopBtn.addEventListener('click', function () {
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
            });
        }
    }

    /* 页面 DOM 加载完成后启动初始化 */
    document.addEventListener('DOMContentLoaded', init);
})();
