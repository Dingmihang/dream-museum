"""
梦境博物馆 - AI Dream Museum
FastAPI 后端
"""
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
import sqlite3, os, time, json, hashlib, secrets, re
from datetime import datetime, timedelta
from contextlib import contextmanager

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = f"{BASE}/dream_museum.db"

# ---- 配置 ----
WECHAT_APPID = os.getenv("WECHAT_APPID", "wx52c179fde7fe2e0a")
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
REPLICATE_TOKEN = os.getenv("REPLICATE_TOKEN", "")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
DAILY_FREE = 1          # 每日免费次数
MAX_AD_PER_DAY = 20     # 每日广告上限
RATE_LIMIT_WINDOW = 10  # 频率限制窗口(秒)
MAX_REQUESTS_PER_WINDOW = 5

# ---- AI Clients ----
deepseek = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com/v1")

# ---- DB ----
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                openid TEXT UNIQUE NOT NULL,
                nickname TEXT DEFAULT '梦行者',
                avatar TEXT DEFAULT '',
                free_count INTEGER DEFAULT 1,
                credit_count INTEGER DEFAULT 0,
                last_free_reset TEXT DEFAULT (datetime('now')),
                daily_ad_count INTEGER DEFAULT 0,
                last_ad_date TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS dream (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                style TEXT DEFAULT '梦核',
                dream_title TEXT,
                dream_analysis TEXT,
                dream_tags TEXT,
                image_url TEXT,
                is_public INTEGER DEFAULT 0,
                like_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
            CREATE TABLE IF NOT EXISTS generate_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                consume_type TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES user(id)
            );
            CREATE TABLE IF NOT EXISTS dream_like (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                dream_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, dream_id)
            );
            CREATE TABLE IF NOT EXISTS dream_fav (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                dream_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, dream_id)
            );
        """)

init_db()

# ---- Rate Limiter ----
_rate_map = {}
def check_rate(user_id: int):
    now = time.time()
    key = f"u{user_id}"
    if key not in _rate_map:
        _rate_map[key] = []
    _rate_map[key] = [t for t in _rate_map[key] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_map[key]) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(429, "请求过于频繁，请稍后")
    _rate_map[key].append(now)

# ---- Auth Helpers ----
def make_token(uid: int) -> str:
    payload = f"{uid}:{int(time.time())}"
    sig = hashlib.sha256(f"{payload}:{JWT_SECRET}".encode()).hexdigest()[:16]
    return f"{payload}:{sig}"

def verify_token(token: str) -> int:
    try:
        parts = token.split(":")
        if len(parts) != 4:
            raise ValueError
        uid, ts, sig = int(parts[0]), int(parts[1]), parts[2]+":"+parts[3]
        expected = hashlib.sha256(f"{uid}:{ts}:{JWT_SECRET}".encode()).hexdigest()[:16]
        if sig != expected:
            raise ValueError
        # 7天过期
        if time.time() - ts > 7 * 86400:
            raise ValueError
        return uid
    except:
        raise HTTPException(401, "登录已过期")

def get_user(request: Request) -> tuple:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "请先登录")
    uid = verify_token(token)
    with db() as c:
        u = c.execute("SELECT * FROM user WHERE id=?", (uid,)).fetchone()
        if not u:
            raise HTTPException(401, "用户不存在")
    return uid, dict(u)

# 每日重置
def reset_daily(u: dict):
    uid = u["id"]
    today = datetime.now().strftime("%Y-%m-%d")
    if u["last_free_reset"][:10] != today:
        with db() as c:
            c.execute("UPDATE user SET free_count=?, last_free_reset=?, daily_ad_count=0, last_ad_date=? WHERE id=?",
                      (DAILY_FREE, today, today, uid))

# ---- 内容安全 ----
BLOCK_WORDS = ["色情", "暴力", "杀人", "自杀", "毒品", "赌博", "裸体", "性爱", "血腥"]
def safety_check(text: str):
    for w in BLOCK_WORDS:
        if w in text:
            raise HTTPException(400, f"内容包含违规词汇，请修改后重试")
    if len(text) < 4:
        raise HTTPException(400, "梦境描述至少4个字")
    if len(text) > 200:
        raise HTTPException(400, "梦境描述最多200字")

# ---- Prompt Templates ----
STYLE_PROMPTS = {
    "梦核": "dreamcore aesthetic, soft focus, pastel tones, liminal space, nostalgic atmosphere, ethereal glow",
    "怪核": "weirdcore, uncanny valley, empty rooms, odd proportions, unsettling but beautiful, liminal horror",
    "童年梦境": "nostalgic childhood memory, warm golden tones, 1990s photography, soft sunlight, bittersweet atmosphere",
    "恐怖梦境": "dark ambient, deep shadows, creeping fog, abandoned places, subtle horror, cinematic darkness",
    "治愈梦境": "cozy dreamscape, warm gentle light, floating islands, soft clouds, peaceful surrealism, healing colors",
    "赛博梦境": "cyberpunk dream, neon haze, digital distortion, glitch art, rain-slicked streets, holographic light",
}

BASE_IMAGE_PROMPT = "masterpiece, best quality, dreamcore, low saturation, film grain, soft focus, surreal dreamscape, blurry edges, mysterious lighting, analog photography, hazy atmosphere, cinematic composition, 16:9"

NEGATIVE_PROMPT = "photorealistic, sharp focus, high contrast, bright daylight, realistic faces, text, watermark, ugly, distorted, bad anatomy, extra limbs"

# ============================================================
# FastAPI App
# ============================================================
app = FastAPI(title="梦境博物馆 API")

# ---- Models ----
class LoginReq(BaseModel):
    code: str

class CreateDreamReq(BaseModel):
    prompt: str
    style: str = "梦核"
    is_public: bool = False

class AdCallbackReq(BaseModel):
    openid: str
    ad_platform: str = "wechat"

# ---- Auth ----
@app.post("/api/auth/login")
async def login(req: LoginReq):
    # 微信登录
    if not req.code:
        raise HTTPException(400, "缺少登录 code")
    import urllib.request
    wx_url = f"https://api.weixin.qq.com/sns/jscode2session?appid={WECHAT_APPID}&secret={WECHAT_SECRET}&js_code={req.code}&grant_type=authorization_code"
    try:
        resp = json.loads(urllib.request.urlopen(wx_url, timeout=10).read())
        openid = resp.get("openid")
    except:
        openid = None
    
    if not openid:
        # 开发阶段：没有 AppSecret 时用 code 生成模拟 openid
        openid = f"dev_{hashlib.md5(req.code.encode()).hexdigest()[:12]}"

    with db() as c:
        user = c.execute("SELECT * FROM user WHERE openid=?", (openid,)).fetchone()
        if not user:
            c.execute("INSERT INTO user (openid) VALUES (?)", (openid,))
            user = c.execute("SELECT * FROM user WHERE openid=?", (openid,)).fetchone()

    uid = user["id"]
    token = make_token(uid)
    reset_daily(dict(user))
    return {"code": 200, "token": token, "user_id": uid, "nickname": user["nickname"]}

# ---- 生成梦境 ----
@app.post("/api/dream/create")
async def dream_create(req: CreateDreamReq, request: Request):
    uid, user = get_user(request)
    check_rate(uid)
    reset_daily(user)
    safety_check(req.prompt)

    # 判断额度
    with db() as c:
        u = c.execute("SELECT * FROM user WHERE id=?", (uid,)).fetchone()
        u = dict(u)
        reset_daily(u)

        consume_type = None
        if u["free_count"] > 0:
            consume_type = "free"
            c.execute("UPDATE user SET free_count = free_count - 1 WHERE id=?", (uid,))
        elif u["credit_count"] > 0:
            consume_type = "ad"
            c.execute("UPDATE user SET credit_count = credit_count - 1 WHERE id=?", (uid,))
        else:
            return JSONResponse({"code": 403, "message": "今日次数已用完，请观看广告获取生成机会"})

    # Step 1: DeepSeek 文字生成
    style_prompt = STYLE_PROMPTS.get(req.style, STYLE_PROMPTS["梦核"])
    text_prompt = f"""你是一个梦境分析师。用户描述了一段梦境："{req.prompt}"。风格：{req.style}。

请返回 JSON 格式（不要其他内容）：
{{
  "dream_title": "10字以内的梦境标题",
  "dream_analysis": "80-120字的诗意梦境解析，从潜意识、情绪、象征角度分析",
  "dream_tags": ["标签1","标签2","标签3","标签4"]
}}"""

    try:
        resp = deepseek.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": text_prompt}],
            temperature=0.9, max_tokens=500,
            response_format={"type": "json_object"}
        )
        text_result = json.loads(resp.choices[0].message.content)
    except:
        text_result = {
            "dream_title": req.prompt[:10] + "的梦",
            "dream_analysis": f"这是一个关于{req.prompt[:30]}的梦境，充满了潜意识的象征。",
            "dream_tags": ["梦境", req.style, "潜意识", "象征"]
        }

    # Step 2: Replicate 图片生成
    img_prompt = f"{BASE_IMAGE_PROMPT}, {style_prompt}, {text_result['dream_title']}, inspired by: {req.prompt[:80]}"
    image_url = await generate_image(img_prompt, NEGATIVE_PROMPT)

    # Step 3: 保存
    with db() as c:
        c.execute("""INSERT INTO dream (user_id, prompt, style, dream_title, dream_analysis, dream_tags, image_url, is_public)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (uid, req.prompt, req.style,
                   text_result["dream_title"],
                   text_result["dream_analysis"],
                   json.dumps(text_result["dream_tags"], ensure_ascii=False),
                   image_url, 1 if req.is_public else 0))
        dream_id = c.lastrowid
        c.execute("INSERT INTO generate_log (user_id, consume_type) VALUES (?,?)", (uid, consume_type))

    # 重新查用户余额
    with db() as c:
        u = dict(c.execute("SELECT * FROM user WHERE id=?", (uid,)).fetchone())

    return {
        "code": 200,
        "dream": {
            "id": dream_id,
            "dream_title": text_result["dream_title"],
            "dream_analysis": text_result["dream_analysis"],
            "dream_tags": text_result["dream_tags"],
            "image_url": image_url,
            "style": req.style,
            "consume_type": consume_type
        },
        "quota": {
            "free_count": u["free_count"],
            "credit_count": u["credit_count"]
        }
    }

async def generate_image(prompt: str, negative: str) -> str:
    import aiohttp
    url = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}", "Content-Type": "application/json"}
    body = {
        "input": {
            "prompt": prompt,
            "negative_prompt": negative,
            "num_outputs": 1,
            "aspect_ratio": "16:9",
            "output_format": "webp",
            "output_quality": 80
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers, timeout=60) as resp:
            data = await resp.json()
        pred_id = data.get("id")
        if not pred_id:
            return ""

        # 轮询等待
        get_url = f"https://api.replicate.com/v1/predictions/{pred_id}"
        for _ in range(30):
            await asyncio_sleep(2)
            async with session.get(get_url, headers=headers) as resp:
                data = await resp.json()
            if data.get("status") == "succeeded":
                output = data.get("output", [])
                if isinstance(output, list) and output:
                    return output[0]
                return str(output) if output else ""
            if data.get("status") == "failed":
                return ""
    return ""

# ---- 异步 sleep helper ----
import asyncio
async def asyncio_sleep(s):
    await asyncio.sleep(s)

# ---- 梦境大厅 ----
@app.get("/api/dream/list")
async def dream_list(page: int = 1, size: int = 20, keyword: str = ""):
    with db() as c:
        base = "FROM dream WHERE is_public=1"
        params = []
        if keyword:
            base += " AND (dream_tags LIKE ? OR dream_title LIKE ? OR prompt LIKE ?)"
            kw = f"%{keyword}%"
            params = [kw, kw, kw]
        total = c.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        rows = c.execute(f"SELECT d.*, u.nickname, u.avatar {base.replace('FROM','FROM')} "
                         f"JOIN user u ON d.user_id=u.id ORDER BY d.id DESC LIMIT ? OFFSET ?",
                         params + [size, (page-1)*size]).fetchall()
    return {
        "code": 200,
        "data": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "has_more": total > page * size
    }

@app.get("/api/dream/detail/{dream_id}")
async def dream_detail(dream_id: int, request: Request):
    with db() as c:
        d = c.execute("SELECT d.*, u.nickname, u.avatar FROM dream d JOIN user u ON d.user_id=u.id WHERE d.id=?", (dream_id,)).fetchone()
        if not d:
            return JSONResponse({"code": 404, "message": "梦境不存在"})
    result = dict(d)
    # 检查当前用户是否点赞/收藏
    try:
        uid, _ = get_user(request)
        with db() as c:
            liked = c.execute("SELECT 1 FROM dream_like WHERE user_id=? AND dream_id=?", (uid, dream_id)).fetchone()
            faved = c.execute("SELECT 1 FROM dream_fav WHERE user_id=? AND dream_id=?", (uid, dream_id)).fetchone()
        result["is_liked"] = bool(liked)
        result["is_faved"] = bool(faved)
    except:
        result["is_liked"] = False
        result["is_faved"] = False
    return {"code": 200, "data": result}

# ---- 点赞 / 收藏 ----
@app.post("/api/dream/like")
async def dream_like(request: Request):
    body = await request.json()
    dream_id = body.get("dream_id", 0)
    uid, _ = get_user(request)
    with db() as c:
        existing = c.execute("SELECT id FROM dream_like WHERE user_id=? AND dream_id=?", (uid, dream_id)).fetchone()
        if existing:
            c.execute("DELETE FROM dream_like WHERE user_id=? AND dream_id=?", (uid, dream_id))
            c.execute("UPDATE dream SET like_count = MAX(0, like_count - 1) WHERE id=?", (dream_id,))
            liked = False
        else:
            c.execute("INSERT INTO dream_like (user_id, dream_id) VALUES (?,?)", (uid, dream_id))
            c.execute("UPDATE dream SET like_count = like_count + 1 WHERE id=?", (dream_id,))
            liked = True
    with db() as c:
        count = c.execute("SELECT like_count FROM dream WHERE id=?", (dream_id,)).fetchone()[0]
    return {"code": 200, "liked": liked, "like_count": count}

@app.post("/api/dream/fav")
async def dream_fav(request: Request):
    body = await request.json()
    dream_id = body.get("dream_id", 0)
    uid, _ = get_user(request)
    with db() as c:
        existing = c.execute("SELECT id FROM dream_fav WHERE user_id=? AND dream_id=?", (uid, dream_id)).fetchone()
        if existing:
            c.execute("DELETE FROM dream_fav WHERE user_id=? AND dream_id=?", (uid, dream_id))
            faved = False
        else:
            c.execute("INSERT INTO dream_fav (user_id, dream_id) VALUES (?,?)", (uid, dream_id))
            faved = True
    return {"code": 200, "faved": faved}

# ---- 我的页面 ----
@app.get("/api/user/profile")
async def user_profile(request: Request):
    uid, user = get_user(request)
    reset_daily(user)
    with db() as c:
        u = dict(c.execute("SELECT * FROM user WHERE id=?", (uid,)).fetchone())
    return {
        "code": 200,
        "user": {
            "nickname": u["nickname"],
            "avatar": u["avatar"],
            "free_count": u["free_count"],
            "credit_count": u["credit_count"],
            "daily_free": DAILY_FREE,
            "daily_ad_max": MAX_AD_PER_DAY,
            "daily_ad_used": u["daily_ad_count"]
        }
    }

@app.get("/api/user/dreams")
async def user_dreams(request: Request, page: int = 1, size: int = 20):
    uid, _ = get_user(request)
    with db() as c:
        total = c.execute("SELECT COUNT(*) FROM dream WHERE user_id=?", (uid,)).fetchone()[0]
        rows = c.execute("SELECT * FROM dream WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                         (uid, size, (page-1)*size)).fetchall()
    return {"code": 200, "data": [dict(r) for r in rows], "total": total}

@app.get("/api/user/favorites")
async def user_favs(request: Request, page: int = 1, size: int = 20):
    uid, _ = get_user(request)
    with db() as c:
        total = c.execute("SELECT COUNT(*) FROM dream_fav WHERE user_id=?", (uid,)).fetchone()[0]
        rows = c.execute("""
            SELECT d.*, u.nickname, u.avatar FROM dream_fav df
            JOIN dream d ON df.dream_id=d.id
            JOIN user u ON d.user_id=u.id
            WHERE df.user_id=? ORDER BY df.id DESC LIMIT ? OFFSET ?
        """, (uid, size, (page-1)*size)).fetchall()
    return {"code": 200, "data": [dict(r) for r in rows], "total": total}

# ---- 设置公开 ----
@app.post("/api/dream/publish")
async def dream_publish(request: Request):
    body = await request.json()
    dream_id = body.get("dream_id", 0)
    uid, _ = get_user(request)
    with db() as c:
        d = c.execute("SELECT * FROM dream WHERE id=? AND user_id=?", (dream_id, uid)).fetchone()
        if not d:
            return JSONResponse({"code": 404, "message": "梦境不存在"})
        c.execute("UPDATE dream SET is_public=1 WHERE id=?", (dream_id,))
    return {"code": 200, "message": "发布成功"}

# ---- 广告回调 ----
@app.post("/api/ad/callback")
async def ad_callback(request: Request):
    body = await request.json()
    uid, _ = get_user(request)
    with db() as c:
        u = dict(c.execute("SELECT * FROM user WHERE id=?", (uid,)).fetchone())
        reset_daily(u)

        today = datetime.now().strftime("%Y-%m-%d")
        # 防刷：检查当日广告上限
        if u["daily_ad_count"] >= MAX_AD_PER_DAY:
            return JSONResponse({"code": 403, "message": "今日广告次数已用完"})

        # 防刷：30秒内不能重复
        c.execute("SELECT created_at FROM generate_log WHERE user_id=? AND consume_type='ad' ORDER BY id DESC LIMIT 1", (uid,))
        last = c.fetchone()
        if last:
            last_time = datetime.strptime(last["created_at"], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - last_time).seconds < 30:
                return JSONResponse({"code": 429, "message": "请稍后再试"})

        c.execute("UPDATE user SET credit_count = credit_count + 1, daily_ad_count = daily_ad_count + 1, last_ad_date=? WHERE id=?",
                  (today, uid))
        c.execute("INSERT INTO generate_log (user_id, consume_type) VALUES (?,?)", (uid, "ad"))

    with db() as c:
        u = dict(c.execute("SELECT * FROM user WHERE id=?", (uid,)).fetchone())
    return {"code": 200, "credit_count": u["credit_count"], "message": "获得1次梦境生成机会"}

# ---- 删除梦境 ----
@app.post("/api/dream/delete")
async def dream_delete(request: Request):
    body = await request.json()
    dream_id = body.get("dream_id", 0)
    uid, _ = get_user(request)
    with db() as c:
        c.execute("DELETE FROM dream WHERE id=? AND user_id=?", (dream_id, uid))
        c.execute("DELETE FROM dream_like WHERE dream_id=?", (dream_id,))
        c.execute("DELETE FROM dream_fav WHERE dream_id=?", (dream_id,))
    return {"code": 200, "message": "已删除"}

# ---- 健康检查 ----
@app.get("/health")
async def health():
    with db() as c:
        users = c.execute("SELECT COUNT(*) FROM user").fetchone()[0]
        dreams = c.execute("SELECT COUNT(*) FROM dream").fetchone()[0]
    return {"status": "ok", "users": users, "dreams": dreams}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090)
