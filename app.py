from flask import Flask, render_template, jsonify, request
import json
import os
import tempfile
import threading
import time
import uuid
import functools
from datetime import datetime, timedelta

# 导入自学习模块
from self_learning import SelfLearningEngine
from live_proxy import register as register_live_proxy

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.environ.get('PROJECTCAT_DATA_FILE', os.path.join(BASE_DIR, 'data.json'))
DATA_LOCK = threading.RLock()
MAX_FEED_LOGS = int(os.environ.get('PROJECTCAT_MAX_FEED_LOGS', '500'))
MAX_ADOPTION_APPS = int(os.environ.get('PROJECTCAT_MAX_ADOPTION_APPS', '500'))
MAX_REPORTS = int(os.environ.get('PROJECTCAT_MAX_REPORTS', '1000'))
MAX_USERS = int(os.environ.get('PROJECTCAT_MAX_USERS', '10000'))
MAX_GUEST_FEEDS = 1  # 游客最多投喂次数
ADMIN_TOKEN = os.environ.get('PROJECTCAT_ADMIN_TOKEN')
APP_CACHE_BUST = os.environ.get('PROJECTCAT_CACHE_BUST') or str(int(time.time()))

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# 初始化自学习引擎
learning_engine = SelfLearningEngine(DATA_FILE)

# ---------- 登录鉴权装饰器 ----------
def login_required(f):
    """要求请求携带有效的 Bearer Token（正式用户）"""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            return jsonify({'success': False, 'message': '请先登录', 'need_login': True}), 401
        user = _get_user_by_token(token)
        if not user:
            return jsonify({'success': False, 'message': '登录已过期，请重新登录', 'need_login': True}), 401
        request._current_user = user
        return f(*args, **kwargs)
    return wrapper

def optional_login(f):
    """可选登录：如果带 token 就注入用户，不带也行"""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        token = _extract_bearer_token()
        request._current_user = _get_user_by_token(token) if token else None
        return f(*args, **kwargs)
    return wrapper

def _extract_bearer_token():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:].strip()
    return None

def _get_user_by_token(token):
    if not token:
        return None
    data = load_data()
    for u in data.get('users', []):
        if u.get('token') == token:
            return u
    return None

@app.context_processor
def inject_cache_bust():
    return {'cache_bust': APP_CACHE_BUST}

@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# 初始化数据文件
def init_data():
    if not os.path.exists(DATA_FILE):
        default_data = {
            "cats": [
                {
                    "id": 1,
                    "name": "咪咪",
                    "nickname": "小区一霸",
                    "gender": "female",
                    "age": "2 岁",
                    "color": "橘白相间",
                    "location": "A 区 - 教学楼后",
                    "status": "free",
                    "description": "性格活泼，喜欢晒太阳，经常在教学楼后的小花园出现。",
                    "image": "cat1.jpg",
                    "feed_count": 156,
                    "views": 1234,
                    "health": "健康",
                    "neutered": True,
                    "adoption_ready": False
                },
                {
                    "id": 2,
                    "name": "小黑",
                    "nickname": "夜行侠",
                    "gender": "male",
                    "age": "1 岁半",
                    "color": "纯黑",
                    "location": "B 区 - 食堂门口",
                    "status": "free",
                    "description": "夜间活跃，白天喜欢躲在车底下，对人比较警惕。",
                    "image": "cat2.jpg",
                    "feed_count": 89,
                    "views": 876,
                    "health": "健康",
                    "neutered": False,
                    "adoption_ready": True
                },
                {
                    "id": 3,
                    "name": "雪球",
                    "nickname": "棉花糖",
                    "gender": "female",
                    "age": "3 岁",
                    "color": "纯白",
                    "location": "C 区 - 图书馆前",
                    "status": "free",
                    "description": "非常亲人，会主动蹭人，是图书馆的常驻猫咪。",
                    "image": "cat3.jpg",
                    "feed_count": 234,
                    "views": 2156,
                    "health": "健康",
                    "neutered": True,
                    "adoption_ready": True
                },
                {
                    "id": 4,
                    "name": "大橘",
                    "nickname": "十斤橘",
                    "gender": "male",
                    "age": "4 岁",
                    "color": "橘色",
                    "location": "D 区 - 操场角落",
                    "status": "free",
                    "description": "体重超标，需要控制饮食，但依然很贪吃。",
                    "image": "cat4.jpg",
                    "feed_count": 312,
                    "views": 1890,
                    "health": "需关注",
                    "neutered": True,
                    "adoption_ready": False
                }
            ],
            "feed_logs": [],
    "adoption_applications": [],
    "reports": [],
    "volunteers": [],
    "emergency_alerts": [],
    "users": [],
    "guest_feeds": {},
    "diaries": [
                {
                    "id": 1, "cat_id": 1, "date": "2026-09-28",
                    "content": "咪咪今天来了 3 次，最喜欢中午那顿。它吃得很安心，还对着摄像头打了个哈欠。阳光很好，它在猫屋旁边晒了一下午的太阳。",
                    "mood": "开心", "visits": 3, "duration": 45,
                    "likes": 12, "comments": [
                        {"user": "小花妈妈", "text": "咪咪太可爱了！", "time": "2026-09-28T14:30:00"}
                    ]
                },
                {
                    "id": 2, "cat_id": 2, "date": "2026-09-28",
                    "content": "小黑今天特别活跃，在猫屋周围跑了好几圈。来的时候夜幕降临，它警惕地蹭了蹭猫屋。深夜才开始放松下来，舔了舔爪子。",
                    "mood": "警惕", "visits": 2, "duration": 30,
                    "likes": 8, "comments": []
                },
                {
                    "id": 3, "cat_id": 3, "date": "2026-09-28",
                    "content": "清晨六点，雪球第一个来到猫屋。它轻轻叫了一声，开启了元气满满的一天。今天来了图书馆看书的同学们都忍不住去摸它。",
                    "mood": "温柔", "visits": 5, "duration": 60,
                    "likes": 23, "comments": [
                        {"user": "图书馆常客", "text": "雪球是图书馆的镇馆之宝！", "time": "2026-09-28T10:15:00"},
                        {"user": "考研人", "text": "每次复习累了看看雪球就很治愈", "time": "2026-09-28T16:42:00"}
                    ]
                },
                {
                    "id": 4, "cat_id": 4, "date": "2026-09-28",
                    "content": "大橘今天来了 4 次，每次停留约 20 分钟。它最喜欢的中午那顿似乎胃口很好，吃得干干净净。不过体重管理提醒已触发，需要关注。",
                    "mood": "慵懒", "visits": 4, "duration": 20,
                    "likes": 15, "comments": [
                        {"user": "操场跑步者", "text": "大橘又胖了一圈哈哈", "time": "2026-09-28T18:20:00"}
                    ]
                },
                {
                    "id": 5, "cat_id": 1, "date": "2026-09-27",
                    "content": "咪咪今天似乎有些慵懒，在猫屋待了 35 分钟。它伸了个懒腰，可能是在等它的猫朋友小黑。傍晚时分终于等到了一起玩耍。",
                    "mood": "慵懒", "visits": 2, "duration": 35,
                    "likes": 9, "comments": []
                },
                {
                    "id": 6, "cat_id": 3, "date": "2026-09-27",
                    "content": "雪球今天来了 4 次，每次停留约 15 分钟。微风习习的天气里，它在图书馆门前的大树下乘凉，还眯了眯眼睛享受午后时光。",
                    "mood": "放松", "visits": 4, "duration": 15,
                    "likes": 18, "comments": [
                        {"user": "大一新生", "text": "第一次见到这么亲人的猫！", "time": "2026-09-27T11:00:00"}
                    ]
                },
                {
                    "id": 7, "cat_id": 2, "date": "2026-09-27",
                    "content": "小黑今天似乎有些好奇，在猫屋待了 25 分钟。它甩了甩尾巴，可能是在研究新装的摄像头。深夜食堂门口只有它一个守夜人。",
                    "mood": "好奇", "visits": 1, "duration": 25,
                    "likes": 6, "comments": []
                },
                {
                    "id": 8, "cat_id": 4, "date": "2026-09-27",
                    "content": "大橘今天特别活跃，在操场角落的猫屋周围跑了好几圈。来的时候天气暖和，它开心地蹭了蹭猫屋。投喂了两次猫粮都吃光了。",
                    "mood": "开心", "visits": 3, "duration": 30,
                    "likes": 11, "comments": []
                },
                {
                    "id": 9, "cat_id": 1, "date": "2026-09-26",
                    "content": "刚下过雨的清晨，咪咪第一个来到教学楼后的猫屋。它舔了舔爪子，在湿润的草地上踩了几个小脚印。今天的它格外安静温柔。",
                    "mood": "温柔", "visits": 2, "duration": 40,
                    "likes": 14, "comments": [
                        {"user": "早起的同学", "text": "雨后的咪咪好治愈", "time": "2026-09-26T07:30:00"}
                    ]
                },
                {
                    "id": 10, "cat_id": 3, "date": "2026-09-26",
                    "content": "雪球今天来了 6 次！创下了本周最高记录。它最喜欢的下午时段来了好几波同学，每个人都忍不住给它加了餐。图书馆的人气王非它莫属。",
                    "mood": "开心", "visits": 6, "duration": 50,
                    "likes": 31, "comments": [
                        {"user": "图书馆管理员", "text": "雪球今天把好几本书都当枕头了", "time": "2026-09-26T15:00:00"},
                        {"user": "志愿者小王", "text": "给雪球拍了今天的写真！", "time": "2026-09-26T17:30:00"}
                    ]
                }
            ],
    "stats": {
                "total_cats": 4,
                "total_feeds": 791,
                "total_views": 6156,
                "active_users": 42
            }
        }
        os.makedirs(os.path.dirname(DATA_FILE) or '.', exist_ok=True)
        save_data(default_data)

def _next_id(items):
    max_id = 0
    for item in items:
        try:
            max_id = max(max_id, int(item.get('id', 0)))
        except Exception:
            continue
    return max_id + 1

def _to_int(value):
    try:
        return int(value)
    except Exception:
        return None

def _clean_str(value, max_len=64):
    if value is None:
        return ''
    s = str(value).strip()
    if len(s) > max_len:
        s = s[:max_len]
    return s

def _ensure_data_shape(data):
    changed = False
    if not isinstance(data, dict):
        data = {}
        changed = True

    cats = data.get('cats')
    if not isinstance(cats, list):
        cats = []
        changed = True

    feed_logs = data.get('feed_logs')
    if not isinstance(feed_logs, list):
        feed_logs = []
        changed = True

    adoption_applications = data.get('adoption_applications')
    if not isinstance(adoption_applications, list):
        adoption_applications = []
        changed = True

    reports = data.get('reports')
    if not isinstance(reports, list):
        reports = []
        changed = True

    volunteers = data.get('volunteers')
    if not isinstance(volunteers, list):
        volunteers = []
        changed = True

    emergency_alerts = data.get('emergency_alerts')
    if not isinstance(emergency_alerts, list):
        emergency_alerts = []
        changed = True

    diaries = data.get('diaries')
    if not isinstance(diaries, list):
        diaries = []
        changed = True

    stats = data.get('stats')
    if not isinstance(stats, dict):
        stats = {}
        changed = True

    for cat in cats:
        if not isinstance(cat, dict):
            continue
        if 'feed_count' not in cat or _to_int(cat.get('feed_count')) is None:
            cat['feed_count'] = 0
            changed = True
        else:
            v = int(cat['feed_count'])
            if cat['feed_count'] != v:
                cat['feed_count'] = v
                changed = True
        if 'views' not in cat or _to_int(cat.get('views')) is None:
            cat['views'] = 0
            changed = True
        else:
            v = int(cat['views'])
            if cat['views'] != v:
                cat['views'] = v
                changed = True
        if 'neutered' not in cat:
            cat['neutered'] = False
            changed = True
        if 'adoption_ready' not in cat:
            cat['adoption_ready'] = False
            changed = True
        if 'adoption_note' not in cat:
            cat['adoption_note'] = ''
            changed = True

    total_cats = len(cats)
    total_feeds = sum(int(c.get('feed_count', 0) or 0) for c in cats if isinstance(c, dict))
    total_views = sum(int(c.get('views', 0) or 0) for c in cats if isinstance(c, dict))
    if stats.get('total_cats') != total_cats:
        stats['total_cats'] = total_cats
        changed = True
    if stats.get('total_feeds') != total_feeds:
        stats['total_feeds'] = total_feeds
        changed = True
    if stats.get('total_views') != total_views:
        stats['total_views'] = total_views
        changed = True

    active_users = _to_int(stats.get('active_users'))
    if active_users is None:
        stats['active_users'] = 42
        changed = True
    elif stats.get('active_users') != active_users:
        stats['active_users'] = active_users
        changed = True

    data['cats'] = cats
    data['feed_logs'] = feed_logs
    data['adoption_applications'] = adoption_applications
    data['reports'] = reports
    data['volunteers'] = volunteers
    data['emergency_alerts'] = emergency_alerts
    data['diaries'] = diaries
    data['stats'] = stats
    return data, changed

def load_data():
    init_data()
    with DATA_LOCK:
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            broken_name = DATA_FILE + '.broken.' + datetime.now().strftime('%Y%m%d%H%M%S')
            try:
                os.replace(DATA_FILE, broken_name)
            except Exception:
                pass
            data = load_default_data()
            save_data(data)
            return data

    data, changed = _ensure_data_shape(data)
    if changed:
        save_data(data)
    return data

def load_default_data():
    return {
        "cats": [
            {
                "id": 1,
                "name": "咪咪",
                "nickname": "小区一霸",
                "gender": "female",
                "age": "2 岁",
                "color": "橘白相间",
                "location": "A 区 - 教学楼后",
                "status": "free",
                "description": "性格活泼，喜欢晒太阳，经常在教学楼后的小花园出现。",
                "image": "cat1.jpg",
                "feed_count": 156,
                "views": 1234,
                "health": "健康",
                "neutered": True,
                "adoption_ready": False
            },
            {
                "id": 2,
                "name": "小黑",
                "nickname": "夜行侠",
                "gender": "male",
                "age": "1 岁半",
                "color": "纯黑",
                "location": "B 区 - 食堂门口",
                "status": "free",
                "description": "夜间活跃，白天喜欢躲在车底下，对人比较警惕。",
                "image": "cat2.jpg",
                "feed_count": 89,
                "views": 876,
                "health": "健康",
                "neutered": False,
                "adoption_ready": True
            },
            {
                "id": 3,
                "name": "雪球",
                "nickname": "棉花糖",
                "gender": "female",
                "age": "3 岁",
                "color": "纯白",
                "location": "C 区 - 图书馆前",
                "status": "free",
                "description": "非常亲人，会主动蹭人，是图书馆的常驻猫咪。",
                "image": "cat3.jpg",
                "feed_count": 234,
                "views": 2156,
                "health": "健康",
                "neutered": True,
                "adoption_ready": True
            },
            {
                "id": 4,
                "name": "大橘",
                "nickname": "十斤橘",
                "gender": "male",
                "age": "4 岁",
                "color": "橘色",
                "location": "D 区 - 操场角落",
                "status": "free",
                "description": "体重超标，需要控制饮食，但依然很贪吃。",
                "image": "cat4.jpg",
                "feed_count": 312,
                "views": 1890,
                "health": "需关注",
                "neutered": True,
                "adoption_ready": False
            }
        ],
        "feed_logs": [],
        "adoption_applications": [],
        "stats": {
            "total_cats": 4,
            "total_feeds": 791,
            "total_views": 6156,
            "active_users": 42
        }
    }

def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE) or '.', exist_ok=True)
    with DATA_LOCK:
        fd, tmp_path = tempfile.mkstemp(prefix='data.', suffix='.json', dir=os.path.dirname(DATA_FILE) or None)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, DATA_FILE)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cats')
def cats():
    return render_template('cats.html')

@app.route('/adopt')
def adopt():
    return render_template('adopt.html')

@app.route('/diary')
def diary():
    return render_template('diary.html')

@app.route('/api/cats')
def get_cats():
    data = load_data()
    return jsonify(data['cats'])

@app.route('/api/cat/<int:cat_id>')
def get_cat(cat_id):
    data = load_data()
    for cat in data['cats']:
        if cat['id'] == cat_id:
            if request.args.get('count', '1') != '0':
                cat['views'] = int(cat.get('views', 0) or 0) + 1
                save_data(data)
            return jsonify(cat)
    return jsonify({'error': 'Cat not found'}), 404

@app.route('/api/stats')
def get_stats():
    data = load_data()
    return jsonify(data['stats'])

@app.route('/api/stats/feed-history')
def get_feed_history():
    """获取投喂历史记录"""
    data = load_data()
    logs = data.get('feed_logs', [])
    # 返回最近 30 条记录
    return jsonify(logs[-30:][::-1])

@app.route('/api/notifications')
def get_notifications():
    """获取通知列表"""
    data = load_data()
    # 从投喂日志和举报状态生成通知
    notifications = []
    
    # 最近的投喂记录作为通知
    feed_logs = data.get('feed_logs', [])[-10:]
    for log in feed_logs:
        cat_id = log.get('cat_id')
        cat_name = None
        for cat in data.get('cats', []):
            if cat.get('id') == cat_id:
                cat_name = cat.get('name')
                break
        notifications.append({
            'id': f"feed_{log.get('id')}",
            'type': 'feed',
            'title': f'投喂记录',
            'message': f'{log.get("user_name", "用户")} 投喂了 {cat_name or "猫咪"}',
            'time': log.get('time'),
            'read': False
        })
    
    # 紧急求助通知
    alerts = data.get('emergency_alerts', [])[-5:]
    for alert in alerts:
        if alert.get('status') == 'active':
            notifications.append({
                'id': f"alert_{alert.get('id')}",
                'type': 'emergency',
                'title': f'紧急求助',
                'message': f'{alert.get("cat_name")} 需要帮助！位置：{alert.get("location")}',
                'time': alert.get('time'),
                'read': False
            })
    
    return jsonify(notifications[::-1][:20])

@app.route('/api/notifications/unread-count')
def get_unread_notification_count():
    """获取未读通知数量"""
    # 目前返回 0，因为所有通知都是模拟的
    return jsonify({'count': 0})

@app.route('/api/feed', methods=['POST'])
def feed_cat():
    if not request.is_json:
        return jsonify({'success': False, 'message': '请求格式错误'}), 400

    req_data = request.get_json(silent=True) or {}
    cat_id = _to_int(req_data.get('cat_id'))
    if not cat_id:
        return jsonify({'success': False, 'message': 'cat_id 不合法'}), 400

    user_name = _clean_str(req_data.get('user_name'), 32) or '匿名用户'
    
    data = load_data()
    
    target_cat = None
    for cat in data['cats']:
        if cat.get('id') == cat_id:
            target_cat = cat
            break
    if not target_cat:
        return jsonify({'success': False, 'message': '猫咪不存在'}), 404

    target_cat['feed_count'] = int(target_cat.get('feed_count', 0) or 0) + 1
    
    # 记录投喂日志
    log = {
        'id': _next_id(data['feed_logs']),
        'cat_id': cat_id,
        'user_name': user_name,
        'time': datetime.now().isoformat(timespec='seconds')
    }
    data['feed_logs'].append(log)
    if len(data['feed_logs']) > MAX_FEED_LOGS:
        data['feed_logs'] = data['feed_logs'][-MAX_FEED_LOGS:]
    
    save_data(data)
    
    # ⭐ 触发自学习引擎
    try:
        user = getattr(request, '_current_user', None)
        user_id = user.get('id') if user else None
        learning_engine.on_feed(cat_id, user_id=user_id, user_name=user_name)
        # 同步学习数据到 data.json
        learning_engine._save_to_data(data)
        save_data(data)
    except Exception:
        pass  # 自学习失败不影响投喂主流程
    
    return jsonify({
        'success': True,
        'message': f'投喂成功！{user_name} 投喂了 {target_cat.get("name", "猫咪")}',
        'cat_id': cat_id,
        'feed_count': target_cat['feed_count']
    })

@app.route('/api/feed-logs')
def get_feed_logs():
    data = load_data()
    cat_id = _to_int(request.args.get('cat_id'))
    limit = _to_int(request.args.get('limit')) or 10
    limit = max(1, min(limit, 50))
    logs = data['feed_logs']
    if cat_id:
        logs = [log for log in logs if isinstance(log, dict) and log.get('cat_id') == cat_id]
    logs = logs[-limit:]
    return jsonify(logs[::-1])  # 倒序排列

@app.route('/api/adopt/apply', methods=['POST'])
def apply_adoption():
    if not request.is_json:
        return jsonify({'success': False, 'message': '请求格式错误'}), 400

    req_data = request.get_json(silent=True) or {}
    cat_id = _to_int(req_data.get('cat_id'))
    if not cat_id:
        return jsonify({'success': False, 'message': 'cat_id 不合法'}), 400

    applicant = req_data.get('applicant', {})
    if not isinstance(applicant, dict):
        return jsonify({'success': False, 'message': 'applicant 不合法'}), 400
    
    data = load_data()

    target_cat = None
    for cat in data['cats']:
        if cat.get('id') == cat_id:
            target_cat = cat
            break
    if not target_cat:
        return jsonify({'success': False, 'message': '猫咪不存在'}), 404
    if not target_cat.get('adoption_ready'):
        note = (target_cat.get('adoption_note') or '').strip()
        if note:
            return jsonify({'success': False, 'message': f'该猫咪暂不可领养：{note}'}), 400
        if target_cat.get('health') and target_cat.get('health') != '健康':
            return jsonify({'success': False, 'message': f'该猫咪暂不可领养：健康{target_cat.get("health")}' }), 400
        if target_cat.get('neutered') is False:
            return jsonify({'success': False, 'message': '该猫咪暂不可领养：未绝育'}), 400
        return jsonify({'success': False, 'message': '该猫咪暂不可领养：暂未开放领养'}), 400

    name = _clean_str(applicant.get('name'), 32)
    phone = _clean_str(applicant.get('phone'), 32)
    adoption_reason = _clean_str(applicant.get('adoptionReason'), 800)
    age = _to_int(applicant.get('age'))
    housing_type = _clean_str(applicant.get('housingType'), 16)
    housing_size = _clean_str(applicant.get('housingSize'), 16)
    family_agree = _clean_str(applicant.get('familyAgree'), 16)
    pet_experience = _clean_str(applicant.get('petExperience'), 16)

    if not name or not phone or not adoption_reason:
        return jsonify({'success': False, 'message': '请填写姓名、电话与领养动机'}), 400
    if age is None or age < 18 or age > 120:
        return jsonify({'success': False, 'message': '年龄需为 18-120 之间'}), 400
    if not housing_type or not housing_size or not family_agree or not pet_experience:
        return jsonify({'success': False, 'message': '请完整填写居住情况与养宠经验'}), 400
    
    # 创建申请记录
    application = {
        'id': _next_id(data['adoption_applications']),
        'cat_id': cat_id,
        'applicant': {
            'name': name,
            'age': age,
            'phone': phone,
            'email': _clean_str(applicant.get('email'), 128),
            'housingType': housing_type,
            'housingSize': housing_size,
            'familyAgree': family_agree,
            'petExperience': pet_experience,
            'previousPets': _clean_str(applicant.get('previousPets'), 128),
            'adoptionReason': adoption_reason
        },
        'time': datetime.now().isoformat(timespec='seconds'),
        'status': 'pending'
    }
    data['adoption_applications'].append(application)
    if len(data['adoption_applications']) > MAX_ADOPTION_APPS:
        data['adoption_applications'] = data['adoption_applications'][-MAX_ADOPTION_APPS:]
    save_data(data)
    
    return jsonify({'success': True, 'message': '领养申请已提交，我们会尽快审核！'})

@app.route('/api/cleanup-logs', methods=['POST'])
def cleanup_logs():
    """清理过期的投喂记录，保留最近 100 条"""
    data = load_data()
    max_logs = 100
    
    if len(data['feed_logs']) > max_logs:
        removed = len(data['feed_logs']) - max_logs
        data['feed_logs'] = data['feed_logs'][-max_logs:]
        save_data(data)
        return jsonify({'success': True, 'message': f'已清理 {removed} 条旧记录'})
    
    return jsonify({'success': True, 'message': '记录数量正常，无需清理'})

@app.route('/api/export')
def export_data():
    data = load_data()
    return jsonify(data)

@app.route('/api/admin/reset', methods=['POST'])
def admin_reset():
    if not ADMIN_TOKEN:
        return jsonify({'error': 'Not found'}), 404
    token = request.headers.get('X-Admin-Token') or ''
    if token != ADMIN_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401
    data = load_default_data()
    save_data(data)
    return jsonify({'success': True})

# ========== 网格化安全守护体系 API ==========

@app.route('/api/report', methods=['POST'])
def create_report():
    """创建举报记录"""
    if not request.is_json:
        return jsonify({'success': False, 'message': '请求格式错误'}), 400

    req_data = request.get_json(silent=True) or {}
    cat_id = _to_int(req_data.get('cat_id'))
    report_type = _clean_str(req_data.get('report_type'), 32)  # injury, abuse, neglect, other
    description = _clean_str(req_data.get('description'), 500)
    reporter_name = _clean_str(req_data.get('reporter_name'), 32) or '匿名用户'
    reporter_contact = _clean_str(req_data.get('reporter_contact'), 64)
    is_emergency = req_data.get('is_emergency', False)

    if not cat_id or not report_type or not description:
        return jsonify({'success': False, 'message': '请填写完整举报信息'}), 400

    data = load_data()

    # 验证猫咪存在
    target_cat = None
    for cat in data['cats']:
        if cat.get('id') == cat_id:
            target_cat = cat
            break
    if not target_cat:
        return jsonify({'success': False, 'message': '猫咪不存在'}), 404

    # 创建举报记录
    report = {
        'id': _next_id(data['reports']),
        'cat_id': cat_id,
        'cat_name': target_cat.get('name'),
        'report_type': report_type,
        'description': description,
        'reporter_name': reporter_name,
        'reporter_contact': reporter_contact,
        'is_emergency': bool(is_emergency),
        'status': 'pending',  # pending, reviewing, resolved, dismissed
        'time': datetime.now().isoformat(timespec='seconds'),
        'evidence': []  # 可上传图片/视频证据
    }
    data['reports'].append(report)
    if len(data['reports']) > MAX_REPORTS:
        data['reports'] = data['reports'][-MAX_REPORTS:]
    save_data(data)

    # 如果是紧急事件，自动创建求助警报
    if is_emergency:
        alert = {
            'id': _next_id(data['emergency_alerts']),
            'report_id': report['id'],
            'cat_id': cat_id,
            'cat_name': target_cat.get('name'),
            'location': target_cat.get('location'),
            'type': report_type,
            'description': description,
            'status': 'active',
            'time': datetime.now().isoformat(timespec='seconds')
        }
        data['emergency_alerts'].append(alert)
        save_data(data)

    return jsonify({
        'success': True,
        'message': '举报已提交，我们会尽快处理！' if not is_emergency else '紧急求助已发送，志愿者正在赶来的路上！',
        'report_id': report['id']
    })

@app.route('/api/reports')
def get_reports():
    """获取举报列表"""
    data = load_data()
    status = _clean_str(request.args.get('status'), 16)
    cat_id = _to_int(request.args.get('cat_id'))
    
    reports = data.get('reports', [])
    if status:
        reports = [r for r in reports if r.get('status') == status]
    if cat_id:
        reports = [r for r in reports if r.get('cat_id') == cat_id]
    
    return jsonify(reports[-50:][::-1])

@app.route('/api/volunteer/apply', methods=['POST'])
def apply_volunteer():
    """申请成为志愿者"""
    if not request.is_json:
        return jsonify({'success': False, 'message': '请求格式错误'}), 400

    req_data = request.get_json(silent=True) or {}
    name = _clean_str(req_data.get('name'), 32)
    phone = _clean_str(req_data.get('phone'), 32)
    id_card = _clean_str(req_data.get('id_card'), 32)
    experience = _clean_str(req_data.get('experience'), 500)
    area = _clean_str(req_data.get('area'), 64)
    available_time = _clean_str(req_data.get('available_time'), 100)

    if not name or not phone or not id_card:
        return jsonify({'success': False, 'message': '请填写姓名、电话和身份证号'}), 400

    data = load_data()

    # 检查是否已申请
    for vol in data.get('volunteers', []):
        if vol.get('id_card') == id_card:
            return jsonify({'success': False, 'message': '您已提交过志愿者申请'}), 400

    volunteer = {
        'id': _next_id(data['volunteers']),
        'name': name,
        'phone': phone,
        'id_card': id_card,
        'experience': experience,
        'area': area,
        'available_time': available_time,
        'status': 'pending',  # pending, approved, rejected
        'level': 'volunteer',  # volunteer, senior_volunteer, coordinator
        'verified': False,
        'apply_time': datetime.now().isoformat(timespec='seconds'),
        'feed_count': 0,
        'rescue_count': 0
    }
    data['volunteers'].append(volunteer)
    save_data(data)

    return jsonify({
        'success': True,
        'message': '志愿者申请已提交，审核通过后您将收到通知！'
    })

@app.route('/api/volunteers')
def get_volunteers():
    """获取志愿者列表（脱敏）"""
    data = load_data()
    status = _clean_str(request.args.get('status'), 16)
    
    volunteers = data.get('volunteers', [])
    if status:
        volunteers = [v for v in volunteers if v.get('status') == status]
    
    # 脱敏处理
    result = []
    for v in volunteers:
        result.append({
            'id': v.get('id'),
            'name': v.get('name'),
            'level': v.get('level'),
            'area': v.get('area'),
            'verified': v.get('verified'),
            'feed_count': v.get('feed_count', 0),
            'rescue_count': v.get('rescue_count', 0)
        })
    
    return jsonify(result[-100:][::-1])

@app.route('/api/emergency/alerts')
def get_emergency_alerts():
    """获取紧急求助列表"""
    data = load_data()
    status = _clean_str(request.args.get('status'), 16)
    
    alerts = data.get('emergency_alerts', [])
    if status:
        alerts = [a for a in alerts if a.get('status') == status]
    
    # 只返回脱敏的位置信息（区域级别）
    result = []
    for a in alerts:
        location = a.get('location', '')
        # 脱敏：只显示区域，不显示精确位置
        if ' - ' in location:
            location = location.split(' - ')[0] + '区'
        result.append({
            'id': a.get('id'),
            'report_id': a.get('report_id'),
            'cat_id': a.get('cat_id'),
            'cat_name': a.get('cat_name'),
            'location': location,
            'type': a.get('type'),
            'description': a.get('description'),
            'status': a.get('status'),
            'time': a.get('time')
        })
    
    return jsonify(result[-20:][::-1])

@app.route('/api/emergency/alert/<int:alert_id>/resolve', methods=['POST'])
def resolve_alert(alert_id):
    """解决紧急求助"""
    if not ADMIN_TOKEN:
        return jsonify({'error': 'Not found'}), 404
    token = request.headers.get('X-Admin-Token') or ''
    if token != ADMIN_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401

    data = load_data()
    for alert in data.get('emergency_alerts', []):
        if alert.get('id') == alert_id:
            alert['status'] = 'resolved'
            alert['resolve_time'] = datetime.now().isoformat(timespec='seconds')
            save_data(data)
            return jsonify({'success': True, 'message': '求助已标记为已解决'})
    
    return jsonify({'success': False, 'message': '求助不存在'}), 404

@app.route('/api/location/<int:cat_id>')
def get_cat_location(cat_id):
    """获取猫咪位置（根据权限返回不同精度）"""
    data = load_data()
    
    # 检查是否为认证志愿者
    is_volunteer = False
    volunteer_id = request.args.get('volunteer_id')
    if volunteer_id:
        for vol in data.get('volunteers', []):
            if str(vol.get('id')) == str(volunteer_id) and vol.get('verified'):
                is_volunteer = True
                break

    for cat in data['cats']:
        if cat['id'] == cat_id:
            location = cat.get('location', '')
            # 普通用户只显示区域
            if not is_volunteer and ' - ' in location:
                location = location.split(' - ')[0]
            return jsonify({
                'cat_id': cat_id,
                'cat_name': cat.get('name'),
                'location': location,
                'is_precise': is_volunteer
            })
    
    return jsonify({'error': 'Cat not found'}), 404

# ========== 认证系统 API ==========

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """手机号 + 验证码登录/注册"""
    if not request.is_json:
        return jsonify({'success': False, 'message': '请求格式错误'}), 400

    req_data = request.get_json(silent=True) or {}
    phone = _clean_str(req_data.get('phone'), 11)
    code = _clean_str(req_data.get('code'), 6)

    # 简单手机号校验
    if not phone or len(phone) < 11 or not phone.isdigit():
        return jsonify({'success': False, 'message': '请输入正确的手机号'}), 400

    # MVP 阶段：验证码固定为 8888
    if code != '8888':
        return jsonify({'success': False, 'message': '验证码错误，请重试（测试验证码：8888）'}), 400

    data = load_data()

    # 查找或创建用户
    user = None
    for u in data.get('users', []):
        if u.get('phone') == phone:
            user = u
            break

    if user is None:
        # 注册新用户
        if len(data.get('users', [])) >= MAX_USERS:
            return jsonify({'success': False, 'message': '系统用户数已达上限'}), 400
        user = {
            'id': _next_id(data.get('users', [])),
            'phone': phone,
            'nickname': f'爱猫人{phone[-4:]}',
            'avatar': '🐱',
            'role': 'user',
            'points': 5,
            'feed_count': 0,
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'token': str(uuid.uuid4())
        }
        data['users'].append(user)
    else:
        # 刷新 token
        user['token'] = str(uuid.uuid4())

    save_data(data)

    return jsonify({
        'success': True,
        'message': '登录成功',
        'token': user['token'],
        'user': {
            'id': user['id'],
            'phone': user['phone'],
            'nickname': user['nickname'],
            'avatar': user.get('avatar', '🐱'),
            'role': user.get('role', 'user'),
            'points': user.get('points', 0),
            'feed_count': user.get('feed_count', 0)
        }
    })

@app.route('/api/auth/me', methods=['GET'])
@login_required
def auth_me():
    """获取当前登录用户信息"""
    user = request._current_user
    return jsonify({
        'success': True,
        'user': {
            'id': user['id'],
            'phone': user['phone'],
            'nickname': user['nickname'],
            'avatar': user.get('avatar', '🐱'),
            'role': user.get('role', 'user'),
            'points': user.get('points', 0),
            'feed_count': user.get('feed_count', 0)
        }
    })

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """退出登录（清除 token）"""
    token = _extract_bearer_token()
    if token:
        data = load_data()
        for u in data.get('users', []):
            if u.get('token') == token:
                u['token'] = ''
                save_data(data)
                break
    return jsonify({'success': True, 'message': '已退出登录'})

# ========== 投喂 API（改造：区分登录用户与游客） ==========

@app.route('/api/feed', methods=['POST'])
@login_required
def feed_cat_login():
    """登录用户投喂（无限制，消耗积分）"""
    if not request.is_json:
        return jsonify({'success': False, 'message': '请求格式错误'}), 400

    req_data = request.get_json(silent=True) or {}
    cat_id = _to_int(req_data.get('cat_id'))
    if not cat_id:
        return jsonify({'success': False, 'message': 'cat_id 不合法'}), 400

    user = request._current_user
    user_name = user.get('nickname', '用户')

    data = load_data()

    target_cat = None
    for cat in data['cats']:
        if cat.get('id') == cat_id:
            target_cat = cat
            break
    if not target_cat:
        return jsonify({'success': False, 'message': '猫咪不存在'}), 404

    # 更新猫咪投喂数
    target_cat['feed_count'] = int(target_cat.get('feed_count', 0) or 0) + 1

    # 更新用户投喂数
    for u in data.get('users', []):
        if u.get('id') == user.get('id'):
            u['feed_count'] = u.get('feed_count', 0) + 1
            u['points'] = u.get('points', 0) + 1
            break

    # 记录投喂日志
    log = {
        'id': _next_id(data['feed_logs']),
        'cat_id': cat_id,
        'user_name': user_name,
        'user_id': user.get('id'),
        'time': datetime.now().isoformat(timespec='seconds'),
        'type': 'user'
    }
    data['feed_logs'].append(log)
    if len(data['feed_logs']) > MAX_FEED_LOGS:
        data['feed_logs'] = data['feed_logs'][-MAX_FEED_LOGS:]

    save_data(data)

    # ⭐ 触发自学习引擎
    try:
        learning_engine.on_feed(cat_id, user_id=user.get('id'), user_name=user_name)
        learning_engine._save_to_data(data)
        save_data(data)
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message': f'投喂成功！{user_name} 投喂了 {target_cat.get("name", "猫咪")}',
        'cat_id': cat_id,
        'feed_count': target_cat['feed_count'],
        'is_guest': False
    })

@app.route('/api/feed-as-guest', methods=['POST'])
def feed_as_guest():
    """游客投喂（每人仅限 1 次）"""
    if not request.is_json:
        return jsonify({'success': False, 'message': '请求格式错误'}), 400

    req_data = request.get_json(silent=True) or {}
    cat_id = _to_int(req_data.get('cat_id'))
    guest_id = _clean_str(req_data.get('guest_id'), 64)

    if not cat_id:
        return jsonify({'success': False, 'message': 'cat_id 不合法'}), 400
    if not guest_id:
        return jsonify({'success': False, 'message': 'missing guest_id'}), 400

    data = load_data()

    # 检查该游客是否已经投喂过
    guest_feeds = data.get('guest_feeds', {})
    guest_feed_count = guest_feeds.get(guest_id, {}).get('count', 0)

    if guest_feed_count >= MAX_GUEST_FEEDS:
        return jsonify({
            'success': False,
            'message': '游客投喂次数已用完，登录后无限畅喂！',
            'need_login': True
        }), 403

    target_cat = None
    for cat in data['cats']:
        if cat.get('id') == cat_id:
            target_cat = cat
            break
    if not target_cat:
        return jsonify({'success': False, 'message': '猫咪不存在'}), 404

    # 更新猫咪投喂数
    target_cat['feed_count'] = int(target_cat.get('feed_count', 0) or 0) + 1

    # 记录游客投喂
    guest_feeds[guest_id] = {
        'count': guest_feed_count + 1,
        'last_feed': datetime.now().isoformat(timespec='seconds')
    }
    data['guest_feeds'] = guest_feeds

    # 记录投喂日志
    log = {
        'id': _next_id(data['feed_logs']),
        'cat_id': cat_id,
        'user_name': '游客',
        'guest_id': guest_id,
        'time': datetime.now().isoformat(timespec='seconds'),
        'type': 'guest'
    }
    data['feed_logs'].append(log)
    if len(data['feed_logs']) > MAX_FEED_LOGS:
        data['feed_logs'] = data['feed_logs'][-MAX_FEED_LOGS:]

    save_data(data)

    remaining = MAX_GUEST_FEEDS - guest_feed_count - 1
    return jsonify({
        'success': True,
        'message': f'投喂成功！您还剩 {remaining} 次游客投喂机会，登录后无限畅喂！',
        'cat_id': cat_id,
        'feed_count': target_cat['feed_count'],
        'is_guest': True,
        'remaining': remaining
    })

# ========== 猫咪日记 API ==========

@app.route('/api/diaries')
def get_diaries():
    """获取日记列表，支持按猫筛选和分页"""
    data = load_data()
    diaries = data.get('diaries', [])
    cats = data.get('cats', [])

    # 构建猫咪 id -> name 映射
    cat_map = {c['id']: c for c in cats if isinstance(c, dict)}

    # 按 cat_id 筛选
    cat_id = _to_int(request.args.get('cat_id'))
    if cat_id:
        diaries = [d for d in diaries if d.get('cat_id') == cat_id]

    # 按日期倒序
    diaries_sorted = sorted(diaries, key=lambda d: d.get('date', ''), reverse=True)

    # 分页
    page = max(_to_int(request.args.get('page')) or 1, 1)
    per_page = min(_to_int(request.args.get('per_page')) or 10, 50)
    total = len(diaries_sorted)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = diaries_sorted[start:end]

    # 附加猫咪信息
    result = []
    for d in page_items:
        item = dict(d)
        cat = cat_map.get(d.get('cat_id'), {})
        item['cat_name'] = cat.get('name', '未知猫咪')
        item['cat_nickname'] = cat.get('nickname', '')
        item['cat_color'] = cat.get('color', '')
        item['cat_location'] = cat.get('location', '')
        result.append(item)

    return jsonify({
        'success': True,
        'diaries': result,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page if per_page else 1
    })

@app.route('/api/diaries/<int:cat_id>')
def get_cat_diaries(cat_id):
    """获取某只猫的全部日记"""
    data = load_data()
    diaries = data.get('diaries', [])
    cats = data.get('cats', [])

    cat = None
    for c in cats:
        if c.get('id') == cat_id:
            cat = c
            break
    if not cat:
        return jsonify({'success': False, 'message': '猫咪不存在'}), 404

    cat_diaries = [d for d in diaries if d.get('cat_id') == cat_id]
    cat_diaries_sorted = sorted(cat_diaries, key=lambda d: d.get('date', ''), reverse=True)

    return jsonify({
        'success': True,
        'cat': {
            'id': cat['id'],
            'name': cat.get('name', ''),
            'nickname': cat.get('nickname', ''),
            'color': cat.get('color', ''),
            'location': cat.get('location', ''),
            'health': cat.get('health', ''),
            'neutered': cat.get('neutered', False),
            'feed_count': cat.get('feed_count', 0),
            'views': cat.get('views', 0)
        },
        'diaries': cat_diaries_sorted
    })

@app.route('/api/diaries/<int:diary_id>/like', methods=['POST'])
def like_diary(diary_id):
    """点赞日记"""
    data = load_data()
    diaries = data.get('diaries', [])

    target = None
    for d in diaries:
        if d.get('id') == diary_id:
            target = d
            break
    if not target:
        return jsonify({'success': False, 'message': '日记不存在'}), 404

    target['likes'] = int(target.get('likes', 0)) + 1
    save_data(data)

    return jsonify({
        'success': True,
        'likes': target['likes']
    })

@app.route('/api/diaries/<int:diary_id>/comment', methods=['POST'])
def comment_diary(diary_id):
    """评论日记"""
    if not request.is_json:
        return jsonify({'success': False, 'message': '请求格式错误'}), 400

    req_data = request.get_json(silent=True) or {}
    user_name = _clean_str(req_data.get('user'), 32)
    text = _clean_str(req_data.get('text'), 500)

    if not user_name:
        return jsonify({'success': False, 'message': '请填写昵称'}), 400
    if not text:
        return jsonify({'success': False, 'message': '评论内容不能为空'}), 400

    data = load_data()
    diaries = data.get('diaries', [])

    target = None
    for d in diaries:
        if d.get('id') == diary_id:
            target = d
            break
    if not target:
        return jsonify({'success': False, 'message': '日记不存在'}), 404

    comments = target.get('comments', [])
    if not isinstance(comments, list):
        comments = []

    new_comment = {
        'user': user_name,
        'text': text,
        'time': datetime.now().isoformat(timespec='seconds')
    }
    comments.append(new_comment)
    target['comments'] = comments
    save_data(data)

    return jsonify({
        'success': True,
        'comment': new_comment,
        'comment_count': len(comments)
    })

# ========== 财务看板 ==========

@app.route('/dashboard')
def dashboard_page():
    """财务看板页面"""
    return render_template('dashboard.html')

@app.route('/api/finance/summary')
def get_finance_summary():
    """获取财务概览数据"""
    data = load_data()
    finance = data.get('finance', {})
    transactions = finance.get('transactions', [])
    
    # 计算统计数据
    total_income = sum(t['amount'] for t in transactions if t['type'] == 'income')
    total_expense = sum(t['amount'] for t in transactions if t['type'] == 'expense')
    balance = total_income - total_expense
    
    # 本月数据
    current_month = datetime.now().strftime('%Y-%m')
    month_income = sum(t['amount'] for t in transactions 
                       if t['type'] == 'income' and t['date'].startswith(current_month))
    month_expense = sum(t['amount'] for t in transactions 
                        if t['type'] == 'expense' and t['date'].startswith(current_month))
    
    # 按类别统计
    income_by_category = {}
    expense_by_category = {}
    for t in transactions:
        cat = t['category']
        if t['type'] == 'income':
            income_by_category[cat] = income_by_category.get(cat, 0) + t['amount']
        else:
            expense_by_category[cat] = expense_by_category.get(cat, 0) + t['amount']
    
    return jsonify({
        'success': True,
        'summary': {
            'total_income': round(total_income, 2),
            'total_expense': round(total_expense, 2),
            'balance': round(balance, 2),
            'month_income': round(month_income, 2),
            'month_expense': round(month_expense, 2),
            'transaction_count': len(transactions)
        },
        'income_by_category': income_by_category,
        'expense_by_category': expense_by_category,
        'categories': finance.get('categories', {})
    })

@app.route('/api/finance/transactions')
def get_finance_transactions():
    """获取交易记录列表"""
    data = load_data()
    finance = data.get('finance', {})
    transactions = finance.get('transactions', [])
    
    # 支持筛选
    trans_type = request.args.get('type')  # income/expense
    category = request.args.get('category')
    
    filtered = transactions
    if trans_type:
        filtered = [t for t in filtered if t['type'] == trans_type]
    if category:
        filtered = [t for t in filtered if t['category'] == category]
    
    # 按日期倒序
    filtered = sorted(filtered, key=lambda x: x['date'], reverse=True)
    
    # 分页
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    
    return jsonify({
        'success': True,
        'transactions': filtered[start:end],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'categories': finance.get('categories', {})
    })

@app.route('/api/finance/monthly')
def get_finance_monthly():
    """获取月度收支趋势"""
    data = load_data()
    finance = data.get('finance', {})
    transactions = finance.get('transactions', [])
    
    # 按月统计
    monthly = {}
    for t in transactions:
        month = t['date'][:7]  # YYYY-MM
        if month not in monthly:
            monthly[month] = {'income': 0, 'expense': 0}
        if t['type'] == 'income':
            monthly[month]['income'] += t['amount']
        else:
            monthly[month]['expense'] += t['amount']
    
    # 转换为列表并排序
    result = [{'month': k, 'income': round(v['income'], 2), 'expense': round(v['expense'], 2)} 
              for k, v in monthly.items()]
    result = sorted(result, key=lambda x: x['month'])
    
    return jsonify({
        'success': True,
        'monthly': result
    })

# ========== 自学习模块 API ==========

@app.route('/api/learning/cat-profile/<int:cat_id>')
def get_learning_cat_profile(cat_id):
    """获取猫咪学习画像"""
    return jsonify(learning_engine.get_cat_profile(cat_id))

@app.route('/api/learning/user-profile/<user_id>')
def get_learning_user_profile(user_id):
    """获取用户偏好画像"""
    return jsonify(learning_engine.get_user_profile(user_id))

@app.route('/api/learning/recommendations/<user_id>')
def get_learning_recommendations(user_id):
    """获取个性化推荐"""
    return jsonify({
        'success': True,
        'recommendations': learning_engine.get_recommendations(user_id)
    })

@app.route('/api/learning/anomalies')
def get_learning_anomalies():
    """获取异常预警列表"""
    anomalies = learning_engine.detect_anomalies()
    return jsonify({
        'success': True,
        'anomalies': anomalies,
        'count': len(anomalies)
    })

@app.route('/api/learning/insights')
def get_learning_insights():
    """获取全局模式洞察"""
    return jsonify(learning_engine.get_global_insights())

@app.route('/api/learning/health-report/<int:cat_id>')
def get_learning_health_report(cat_id):
    """获取猫咪健康报告"""
    return jsonify(learning_engine.compute_health_score(cat_id))

@app.route('/api/learning/feedback', methods=['POST'])
def post_learning_feedback():
    """提交识别纠错反馈"""
    if not request.is_json:
        return jsonify({'success': False, 'message': '请求格式错误'}), 400
    req_data = request.get_json(silent=True) or {}
    predicted = req_data.get('predicted_cat_id')
    actual = req_data.get('actual_cat_id')
    confidence = req_data.get('confidence', 0)
    image = req_data.get('image_path')
    if predicted is None or actual is None:
        return jsonify({'success': False, 'message': '缺少 predicted_cat_id 或 actual_cat_id'}), 400
    learning_engine.record_feedback(predicted, actual, confidence, image)
    return jsonify({'success': True, 'message': '反馈已记录'})

@app.route('/api/learning/train', methods=['POST'])
def post_learning_train():
    """触发模型重新训练"""
    result = learning_engine.retrain()
    # 同步学习数据到 data.json
    data = load_data()
    learning_engine._save_to_data(data)
    save_data(data)
    return jsonify(result)

# 实时直播：浏览器同源代理到树莓派 MJPEG（未配 CATTRACE_LIVE_URL 时自动关闭）
register_live_proxy(app)

if __name__ == '__main__':
    init_data()
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes', 'on')
    host = os.environ.get('PROJECTCAT_HOST', '127.0.0.1')
    port = int(os.environ.get('PROJECTCAT_PORT', '5000'))
    app.run(debug=debug, host=host, port=port)
