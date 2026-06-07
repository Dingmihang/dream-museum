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
# 尝试从 ~/.hermes/.env 加载（本地开发用）
_env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k not in os.environ:
                    os.environ[k] = v

WECHAT_APPID = os.getenv("WECHAT_APPID", "wx683a3933492a97b1")
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
REPLICATE_TOKEN = os.getenv("REPLICATE_TOKEN", "")
SILICONFLOW_KEY = os.getenv("SILICONFLOW_KEY", "sk-elm...zzma")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
DAILY_FREE = 3          # 每日免费次数
MAX_AD_PER_DAY = 20     # 每日广告上限
RATE_LIMIT_WINDOW = 10  # 频率限制窗口(秒)
MAX_REQUESTS_PER_WINDOW = 5

# ---- AI Clients ----
_deepseek = None
def get_deepseek():
    global _deepseek
    if _deepseek is None:
        _deepseek = OpenAI(api_key=DEEPSEEK_KEY or "sk-placeholder", base_url="https://api.deepseek.com/v1")
    return _deepseek

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
                free_count INTEGER DEFAULT 3,
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

# 迁移旧数据：所有用户免费次数改为3
with db() as c:
    c.execute("UPDATE user SET free_count = 3 WHERE free_count < 3")

# 启动时自动填充模拟梦境（防止Render部署清空数据）
_seed_data = [
    ("晚风轻拂", "樱花岛上的透明鹿", "治愈梦境", "一只有透明翅膀的鹿在漂浮的樱花岛上轻轻起舞，每一步都落下星光。这是你心底对纯粹美好的渴望，像风一样自由而轻盈。", '["轻盈","自由","美好","樱花"]'),
    ("月亮邮递员", "城市上空的水母", "怪核", "巨大的发光水母在城市上空缓慢游动，街道空无一人。潜意识里对未知的敬畏与好奇交织，仿佛世界被重新定义。", '["神秘","超现实","孤独","探索"]'),
    ("星河旅人", "向日葵田的回忆", "童年梦境", "外婆家的后院变成了无边无际的向日葵田，金色的光芒洒满童年。那是你记忆深处最温暖的避风港。", '["童年","温暖","回忆","金色"]'),
    ("旧梦拾荒者", "月光莲花海", "梦核", "月光下的海面开满了发光的莲花，每朵莲花里都藏着一个被遗忘的梦。你正在拾回那些散落的自己。", '["月光","莲花","遗忘","拾回"]'),
    ("风居住的街道", "废弃钟楼的金树", "怪核", "无人知晓的钟楼上长出了一棵金色的树，树叶是时间的碎片。有些东西被遗忘，却在寂静中重生。", '["时间","重生","寂静","金色"]'),
    ("贩卖日落", "白鸟飞过彩虹桥", "治愈梦境", "你骑着巨大的白鸟飞越彩虹桥，云端有温柔的光。内心渴望突破现实边界，飞向更广阔的天空。", '["自由","飞翔","彩虹","治愈"]'),
    ("深海里的星星", "雪地上的月光脚印", "梦核", "白色的雪地上留下一串发光的脚印，一直延伸到月亮。你在追寻某个重要的人，还是追寻另一个自己？", '["追寻","月光","雪地","自己"]'),
    ("雾中行舟", "发光纸船的愿望", "治愈梦境", "小溪里游着发光的纸船，每只都装着一个未说出口的愿望。它们正缓缓驶向心愿实现的彼岸。", '["愿望","纸船","小溪","希望"]'),
    ("云朵收藏家", "面包店的小精灵", "童年梦境", "深夜的面包店里，小精灵们在偷偷烤明天的面包。每个面包里都藏着一个甜甜的梦。", '["精灵","面包","童年","甜蜜"]'),
    ("夏日终曲", "楼顶连成的草原", "梦核", "城市所有楼顶连成一片无尽的草原，风吹过像海浪。你在钢筋森林里找到了属于自己的旷野。", '["草原","城市","旷野","自由"]'),
    ("雨夜的猫", "烟斗里的银河", "怪核", "老爷爷的烟斗里飘出整个银河，星星点点洒满房间。有些梦想像烟一样轻，却比银河还浩瀚。", '["银河","梦想","轻盈","浩瀚"]'),
    ("海底两万里", "落叶变成的金鱼", "童年梦境", "秋天的落叶没有飘落，而是变成金色的鱼群游向天空。童年相信一切皆有可能。", '["秋天","金鱼","落叶","童年"]'),
    ("森之精灵", "石板路的星河", "梦核", "老街的石板路在月光下变成了一条星河，你踩过的每一步都溅起星光。平凡的日常也能变成魔法。", '["老街","月光","星河","魔法"]'),
    ("火车慢驶", "云层上的旋转木马", "治愈梦境", "旋转木马转到了云层之上，上面坐着各种可爱的动物。成年后的你，依然需要片刻的旋转与欢笑。", '["旋转木马","云端","欢乐","童真"]'),
    ("南方有乔木", "会说话的猫咪", "童年梦境", "猫咪悄悄告诉你，它去过最远的地方是月亮。有些陪伴看似微不足道，却是通往宇宙的入口。", '["猫咪","月亮","陪伴","秘密"]'),
    ("半杯奶茶", "糖果雨的梦境", "童年梦境", "天空下起了糖果雨，每颗糖果里都藏着一个未完成的梦。童年的快乐像糖一样甜，融化在舌尖上。", '["糖果","童年","甜蜜","梦想"]'),
    ("流浪的鲸鱼", "玻璃宫殿的云", "怪核", "沙漠里有一个玻璃做的宫殿，里面养着柔软的云朵。也许你内心渴望一个与世隔绝的宁静空间。", '["沙漠","玻璃","云朵","宁静"]'),
    ("失眠的长颈鹿", "发光纸船", "治愈梦境", "小溪里游着发光的纸船，每只都装着一个愿望。你的愿望正在缓缓驶向梦想的彼岸，不要着急。", '["纸船","愿望","小溪","耐心"]'),
    ("行走的云", "教室窗外的海底", "童年梦境", "教室窗外突然变成了深邃的海底世界，五颜六色的鱼群从窗前游过。好奇心是童年最珍贵的礼物。", '["教室","海底","鱼群","好奇"]'),
    ("发呆专业户", "旋转木马的秘密", "怪核", "废弃游乐园里的旋转木马在午夜自己转动起来。有些快乐即使被遗忘，也从未真正停止。", '["游乐园","旋转木马","午夜","遗忘"]'),
    ("一只废柴", "森林里的光", "治愈梦境", "森林里的蘑菇发出柔和的光，小小的精灵在跳舞。即使在最黑暗的森林里，也有光在守护你。", '["森林","蘑菇","精灵","微光"]'),
    ("熬夜冠军", "城堡旋转楼梯", "治愈梦境", "城堡里的旋转楼梯通向云端，每一层都是一个不同的季节。你在攀登人生的阶梯，沿途都是风景。", '["城堡","楼梯","云端","季节"]'),
    ("人间清醒", "贝壳路通向月亮", "童年梦境", "海水退去后露出一条贝壳铺成的路，一直延伸到月亮岛。有些奇迹只出现在潮水退去的时候。", '["海洋","贝壳","月亮","奇迹"]'),
    ("社恐星人", "霓虹雨中的城市", "赛博梦境", "赛博城市下雨了，霓虹灯光映在水面上像一幅流动的画。未来与诗意原来可以如此和谐共存。", '["赛博","霓虹","雨","诗意"]'),
    ("奶茶重度患者", "萤火虫星座", "治愈梦境", "湖面上的萤火虫组成了十二星座的形状，它们是你心中未被说出的星图。微光虽小，聚在一起就是银河。", '["萤火虫","星座","湖面","微光"]'),
    ("袜子少一只", "手心的小彩虹", "童年梦境", "我的手心可以长出小小的彩虹。原来魔法一直都在，只是需要你用童心去发现。", '["彩虹","手心","魔法","童心"]'),
    ("拖延症晚期", "冰面上的花", "梦核", "冰面上开出了温暖的花，踩上去不会碎。矛盾的事物在梦里找到了和解的方式。", '["冰面","花朵","矛盾","和解"]'),
    ("野生哲学家", "迷宫尽头的热巧克力", "治愈梦境", "迷宫尽头不是出口，而是一杯永远喝不完的热巧克力。有时候旅行的意义不在于走出去，而在于找到属于自己的温暖。", '["迷宫","热巧克力","温暖","旅程"]'),
    ("深夜食堂", "雪人织的围巾", "治愈梦境", "公园长椅上坐着一个雪人，他正在织一条特别长的围巾。原来等待一个人，也可以是一件温暖的事。", '["雪人","围巾","等待","温暖"]'),
    ("便利店小陈", "热气球与蒲公英", "治愈梦境", "热气球带我飞到了蒲公英组成的云层，每一朵蒲公英都载着一个未完成的梦。放手，是为了更好的相遇。", '["热气球","蒲公英","云层","放手"]'),
    ("没头脑不高兴", "画本里的小人", "童年梦境", "我的画本里走出了一群会发光的小人，他们在我的书桌上开派对。想象力是童年送给成年自己最好的礼物。", '["画本","小人","发光","想象力"]'),
    ("今天也可爱", "倒挂月亮的街灯", "怪核", "街道的路灯全是倒挂的月亮，温柔的光洒在空无一人的街道上。最美的风景往往在最不经意的时刻出现。", '["路灯","月亮","街道","温柔"]'),
    ("今天不想上班", "海螺里的歌声", "治愈梦境", "海螺里能听到另一个世界的歌声。把耳朵贴近它，你会听到宇宙在对你说：慢一点，没关系。", '["海螺","歌声","宇宙","慢生活"]'),
    ("地球观察员", "银杏叶的蝴蝶", "童年梦境", "秋天的银杏叶没有落下，而是变成金色的蝴蝶飞向天空。每一次告别，都可能是另一种形式的相遇。", '["银杏","蝴蝶","秋天","告别"]'),
    ("平行世界的我", "阁楼的异世界门", "怪核", "我家阁楼里有一扇门通向一片无垠的草原。也许我们都是生活在两个世界之间的旅人。", '["阁楼","门","草原","平行世界"]'),
    ("摸鱼达人", "水彩画里的雨天", "治愈梦境", "下雨天整个世界变成了一幅水彩画，颜色在雨中慢慢地晕开。美好的事物未必是清晰的，朦胧也是一种美。", '["雨","水彩画","朦胧","美"]'),
    ("快乐肥宅", "稻草人的音乐会", "童年梦境", "稻草人穿上西装在麦田里开了场音乐会，听众是满天的星星。孤独的人心中往往有一座最热闹的舞台。", '["稻草人","音乐会","麦田","星星"]'),
    ("便利店长", "逆行钟表店", "怪核", "废弃的钟表店里所有钟表都在逆行。有些时光你永远不想向前走，只想一遍遍地重温那些美好。", '["钟表","逆行","时光","重温"]'),
    ("北欧的极光", "镜中的月亮", "梦核", "镜子里不只有我，还有一个笑着的月亮。原来你一直寻找的光，就在你自己的眼睛里。", '["镜子","月亮","自己","光芒"]'),
    ("撒哈拉的星", "棉花糖楼梯", "童年梦境", "梦里的楼梯是棉花糖做的，踩上去软软的。成年的世界太硬了，偶尔需要回到童年的柔软里休息一下。", '["棉花糖","楼梯","柔软","休息"]'),
    ("冰岛没有冰", "星星变成的小猫", "治愈梦境", "星星落下来变成小猫咪在我怀里睡着了。宇宙用最温柔的方式告诉你：你从来都不是一个人。", '["星星","猫咪","拥抱","陪伴"]'),
    ("西西里的传说", "捕梦网与晚霞", "梦核", "用捕梦网捞起一片晚霞，染红了整个房间。你想留住的不只是颜色，更是那个稍纵即逝的瞬间。", '["捕梦网","晚霞","瞬间","珍藏"]'),
    ("大草原的狼", "长颈鹿吃星星", "童年梦境", "长颈鹿的脖子绕过了云层，在安静地吃着星星。原来再高的地方也有它的快乐，再远的目标也值得伸长脖子去够。", '["长颈鹿","星星","云层","目标"]'),
    ("吃瓜群众", "发光的文字溪流", "梦核", "水面上漂着会发光的文字，每个字都是一个小小的记忆。那些你以为遗忘了的故事，其实都在潜意识里闪闪发光。", '["文字","溪流","记忆","发光"]'),
    ("程序员小林", "地铁里的鲸鱼", "治愈梦境", "地铁站变成了水族馆，列车是一条条慢慢游过的鲸鱼。匆忙的通勤路上，也许你也需要偶尔停下来，看鲸鱼游过。", '["地铁","鲸鱼","水族馆","暂停"]'),
    ("地铁五号线", "泡泡屋顶小镇", "治愈梦境", "小镇的屋顶上都覆盖着透明的泡泡，在阳光下反射出彩虹。幸福有时很简单，只需要一个小镇的屋顶和满天的泡泡。", '["小镇","泡泡","屋顶","彩虹"]'),
    ("焦虑的考拉", "雾中灯塔的光", "梦核", "雾中的灯塔发出的光，让人能看见最想念的人。在迷茫的时刻，总有一盏灯为你亮着，指引你回家的方向。", '["灯塔","雾","光","思念"]'),
    ("今天也要努力", "山谷里的樱花雪", "治愈梦境", "山谷里有一棵会下雪的樱花树，花瓣和雪花在半空中相遇。这个世界上总有一些地方，春天和冬天在一起。", '["山谷","樱花","雪","共存"]'),
    ("明天再说吧", "烟斗里的宇宙", "怪核", "老爷子的烟斗里飘出了整个宇宙，星星和星云在房间里缓缓旋转。你永远不知道一个人的内心世界可以有多浩瀚。", '["烟斗","宇宙","浩瀚","内心"]'),
]

with db() as c:
    # 清理旧的种子数据（标签格式可能错误）
    c.execute("DELETE FROM dream WHERE user_id IN (SELECT id FROM user WHERE openid LIKE 'seed_%')")
    c.execute("DELETE FROM user WHERE openid LIKE 'seed_%'")
    count = c.execute("SELECT COUNT(*) FROM dream WHERE is_public=1").fetchone()[0]
    if count < len(_seed_data):
        for nick, title, style, analysis, tags_str in _seed_data:
            # 创建用户
            import hashlib
            openid = f"seed_{hashlib.md5(nick.encode()).hexdigest()[:8]}"
            c.execute("INSERT OR IGNORE INTO user (openid, nickname, free_count) VALUES (?,?,3)", (openid, nick))
            user = c.execute("SELECT id FROM user WHERE openid=?", (openid,)).fetchone()
            if user:
                uid = user["id"]
                c.execute("""INSERT INTO dream (user_id, prompt, style, dream_title, dream_analysis, dream_tags, image_url, is_public)
                             VALUES (?,?,?,?,?,?,?,?)""",
                          (uid, title, style, title, analysis, tags_str, "", 1))
        # 种子梦境 image_url 留空，图片代理自动返回占位 PNG

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
        if len(parts) != 3:
            raise ValueError
        uid, ts, sig = int(parts[0]), int(parts[1]), parts[2]
        expected = hashlib.sha256(f"{uid}:{ts}:{JWT_SECRET}".encode()).hexdigest()[:16]
        if sig != expected:
            raise ValueError
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
        resp = get_deepseek().chat.completions.create(
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
        cur = c.execute("""INSERT INTO dream (user_id, prompt, style, dream_title, dream_analysis, dream_tags, image_url, is_public)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (uid, req.prompt, req.style,
                   text_result["dream_title"],
                   text_result["dream_analysis"],
                   json.dumps(text_result["dream_tags"], ensure_ascii=False),
                   image_url, 1 if req.is_public else 0))
        dream_id = cur.lastrowid
        cur.execute("INSERT INTO generate_log (user_id, consume_type) VALUES (?,?)", (uid, consume_type))

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

# 图片生成 - 硅基流动 (SiliconFlow)
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "Tongyi-MAI/Z-Image-Turbo")

async def generate_image(prompt: str, negative: str) -> str:
    """生成梦境图片，返回图片 URL 或空字符串"""
    import aiohttp
    url = "https://api.siliconflow.cn/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "negative_prompt": negative,
        "image_size": "1024x576",
        "num_images": 1,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers, timeout=60) as resp:
                data = await resp.json()
        images = data.get("images", [])
        if images:
            return images[0].get("url", "")
        import sys
        print(f"[generate_image] no images in response: {json.dumps(data)[:200]}", file=sys.stderr)
        return ""
    except Exception as e:
        import sys
        print(f"[generate_image] error: {e}", file=sys.stderr)
        return ""

# ---- 异步 sleep helper ----
import asyncio
async def asyncio_sleep(s):
    await asyncio.sleep(s)

# ---- 梦境大厅 ----
@app.get("/api/dream/list")
async def dream_list(page: int = 1, size: int = 20, keyword: str = ""):
    with db() as c:
        where = "WHERE d.is_public=1"
        params = []
        if keyword:
            where += " AND (d.dream_tags LIKE ? OR d.dream_title LIKE ? OR d.prompt LIKE ?)"
            kw = f"%{keyword}%"
            params = [kw, kw, kw]
        base_from = "FROM dream d"
        total = c.execute(f"SELECT COUNT(*) {base_from} {where}", params).fetchone()[0]
        rows = c.execute(f"SELECT d.*, u.nickname, u.avatar {base_from} "
                         f"JOIN user u ON d.user_id=u.id {where} "
                         f"ORDER BY d.id DESC LIMIT ? OFFSET ?",
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

# ---- 更新个人资料 ----
class UpdateProfileReq(BaseModel):
    nickname: str = ""
    avatar: str = ""

@app.post("/api/user/update")
async def user_update(req: UpdateProfileReq, request: Request):
    uid, _ = get_user(request)
    with db() as c:
        if req.nickname and len(req.nickname.strip()) <= 20:
            c.execute("UPDATE user SET nickname=? WHERE id=?", (req.nickname.strip(), uid))
        if req.avatar and len(req.avatar) <= 500:
            c.execute("UPDATE user SET avatar=? WHERE id=?", (req.avatar, uid))
        u = dict(c.execute("SELECT * FROM user WHERE id=?", (uid,)).fetchone())
    return {
        "code": 200,
        "user": {
            "nickname": u["nickname"],
            "avatar": u["avatar"],
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

# ---- 图片代理（解决小程序域名白名单问题） ----
@app.get("/api/image/{dream_id}")
async def image_proxy(dream_id: int):
    import aiohttp
    from fastapi.responses import Response
    
    with db() as c:
        d = c.execute("SELECT image_url, style FROM dream WHERE id=?", (dream_id,)).fetchone()
    
    if d and d["image_url"]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(d["image_url"], timeout=15) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        return Response(content=content, media_type="image/png")
        except:
            pass
    
    # 占位图：返回柔和小方块 PNG
    style_colors = {
        "梦核": "#D4C5E2", "怪核": "#C5D5E2", "童年梦境": "#FAE8C8",
        "治愈梦境": "#C8E8D4", "赛博梦境": "#C8D8F0",
    }
    bg = style_colors.get(d["style"] if d else "梦核", "#EDE8E0")
    import struct, zlib
    r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
    width, height = 300, 170
    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter none
        for x in range(width):
            raw += bytes([r, g, b, 255])
    
    def chunk(ct, data):
        c = ct + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw))
    png += chunk(b'IEND', b'')
    
    return Response(content=png, media_type="image/png")

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
