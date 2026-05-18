import os
import re
import random
import asyncio
import sqlite3
import time
import json
import string
import math

os.makedirs("profiles", exist_ok=True)

from unidecode import unidecode
from PIL import Image, ImageDraw, ImageFont
from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import GetFullChannelRequest

def format_time(seconds):
    return f"{seconds}s"

def win_chance(amount):
    if amount < 10000:
        return 0.75
    elif amount < 30000:
        return 0.65
    elif amount < 50000:
        return 0.55
    else:
        return 0.50

# ========= CONFIG =========
API_ID = 39842340
API_HASH = "6d573118f5dda2cd1960677452c42c33"
BOT_TOKEN = "8712453329:AAE30HwBsfoGJGoytHTHxr-5P2ymj3Dd1Po"
BOT_USERNAME = "farm_tree_bot"

RAIN_INTERVAL = 3600   # 1h30 = 5400 sec
RAIN_DURATION = 1800 # durée collecte = 1h
GROUP_FILE = "group.json"

groups_db = set()
rains = {}
groups = set()
rbet_players = {}
nation_games = {}
fnation_fights = {}
ripple_games = {}
lotteries = {}  # {chat_id: {lot_id: data}}
lottery_counter = 0
sonar_games = {}  # {chat_id: game_data}
games_4p = {}  # chat_id: game

PROFILE_CACHE_FILE = "profile_cache.json"
profile_cache = {}

def load_profile_cache():
    global profile_cache
    try:
        with open(PROFILE_CACHE_FILE, "r", encoding="utf-8") as f:
            profile_cache = json.load(f)
    except:
        profile_cache = {}

def save_profile_cache():
    with open(PROFILE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile_cache, f, ensure_ascii=False)

client = TelegramClient('bots', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

load_profile_cache()
save_profile_cache()
# ========= DATABASE =========
conn = sqlite3.connect("game.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    cash INTEGER DEFAULT 10000,
    bank INTEGER DEFAULT 0,
    health INTEGER DEFAULT 1,
    reputation INTEGER DEFAULT 0,
    weapon TEXT DEFAULT 'punch',
    gem TEXT DEFAULT 'none',
    last_daily INTEGER DEFAULT 0,
    kills_today INTEGER DEFAULT 0,
    robs_today INTEGER DEFAULT 0,
    last_reset INTEGER DEFAULT 0,
    last_blood INTEGER DEFAULT 0,
    last_kill INTEGER DEFAULT 0,
    last_rob INTEGER DEFAULT 0,
    last_pay INTEGER DEFAULT 0
)
""")

cursor.execute("PRAGMA table_info(users)")
columns = [col[1] for col in cursor.fetchall()]

if "last_nation" not in columns:
    cursor.execute("ALTER TABLE users ADD COLUMN last_nation INTEGER DEFAULT 0")
    conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    rob_enabled INTEGER DEFAULT 1,
    kill_enabled INTEGER DEFAULT 1
)
""")

conn.commit()

def add_friend(user1, user2):

    # évite doublons
    cursor.execute(
        "SELECT 1 FROM friends WHERE user_id=? AND friend_id=?",
        (user1, user2)
    )

    if cursor.fetchone():
        return

    # relation double
    cursor.execute(
        "INSERT INTO friends(user_id, friend_id) VALUES (?, ?)",
        (user1, user2)
    )

    cursor.execute(
        "INSERT INTO friends(user_id, friend_id) VALUES (?, ?)",
        (user2, user1)
    )

    conn.commit()


def remove_friend(user1, user2):

    cursor.execute(
        "DELETE FROM friends WHERE user_id=? AND friend_id=?",
        (user1, user2)
    )

    cursor.execute(
        "DELETE FROM friends WHERE user_id=? AND friend_id=?",
        (user2, user1)
    )

    conn.commit()



cursor.execute("DELETE FROM profiles")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS friends (
    user_id INTEGER,
    friend_id INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    photo TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS ratings (
    from_user INTEGER,
    to_user INTEGER,    rating INTEGER
)
""")

conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS siblings (
    user1 INTEGER,
    user2 INTEGER
)
""")

conn.commit()
# ========= FAMILY TABLE =========
cursor.execute("""
CREATE TABLE IF NOT EXISTS family (
    user_id INTEGER PRIMARY KEY,
    parent_id INTEGER
)
""")

# ========= MARRIAGE TABLE =========
cursor.execute("""
CREATE TABLE IF NOT EXISTS marriages (
    user_id INTEGER PRIMARY KEY,
    partner_id INTEGER
)
""")

conn.commit()

# 🔥 ajoute colonne si elle n'existe pas
try:
    cursor.execute("ALTER TABLE profiles ADD COLUMN name TEXT")
    conn.commit()
except:
    pass
# ========= LOAD GIF =========
def load_kill_gifs():
    data = {}
    for f in os.listdir("killed"):
        key = ''.join([i for i in f.split(".")[0] if not i.isdigit()])
        data.setdefault(key, []).append(os.path.join("killed", f))
    return data

killed_gifs = load_kill_gifs()
rob_gifs = [os.path.join("robbery", f) for f in os.listdir("robbery")]
failed_gifs = [os.path.join("failed", f) for f in os.listdir("failed")]

# ========= TREE IMAGE =========
def draw_tree(user_id):

    size_x = 1400
    size_y = 1000

    img = Image.new(
        "RGB",
        (size_x, size_y),
        "#a8cad6"
    )

    draw = ImageDraw.Draw(img)

    center_x = size_x // 2
    center_y = size_y // 2

    # ========= FONT =========
    try:

        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/system/fonts/Roboto-Bold.ttf"
        ]

        font_path = None

        for p in font_paths:
            if os.path.exists(p):
                font_path = p
                break

        if font_path:
            font = ImageFont.truetype(font_path, 20)
        else:
            font = ImageFont.load_default()

    except:
        font = ImageFont.load_default()

    # ========= PHOTO DRAW =========
    def draw_person(uid, x, y):

        pic = get_profile_pic(uid)

        w = 140
        h = 90

        x1 = x - w // 2
        y1 = y - h // 2

        x2 = x + w // 2
        y2 = y + h // 2

        if pic and os.path.exists(pic):

            try:

                p = Image.open(pic).convert("RGB")
                p = p.resize((w, h))

                img.paste(
                    p,
                    (x1, y1)
                )

            except:

                draw.rounded_rectangle(
                    [x1, y1, x2, y2],
                    radius=10,
                    outline="#ff2b2b",
                    width=4,
                    fill="#243447"
                )

        else:

            draw.rounded_rectangle(
                [x1, y1, x2, y2],
                radius=10,
                outline="#ff2b2b",
                width=4,
                fill="#243447"
            )

        return (x1, y1, x2, y2)

    # ========= CENTER =========
    main_box = draw_person(
        user_id,
        center_x,
        center_y
    )

    # ========= GET FAMILY =========
    cursor.execute(
        "SELECT parent_id FROM family WHERE user_id=?",
        (user_id,)
    )

    parent_row = cursor.fetchone()

    parent_id = parent_row[0] if parent_row else None

    cursor.execute(
        "SELECT user_id FROM family WHERE parent_id=?",
        (user_id,)
    )

    children = [x[0] for x in cursor.fetchall()]

    cursor.execute(
        "SELECT partner_id FROM marriages WHERE user_id=?",
        (user_id,)
    )

    partner_row = cursor.fetchone()

    partner_id = partner_row[0] if partner_row else None

    siblings = []

    if parent_id:

        cursor.execute(
            """
            SELECT user_id
            FROM family
            WHERE parent_id=?
            AND user_id!=?
            """,
            (parent_id, user_id)
        )

        siblings = [x[0] for x in cursor.fetchall()]

    # ========= PARENT =========
    if parent_id:

        px = center_x
        py = center_y - 250

        parent_box = draw_person(
            parent_id,
            px,
            py
        )

        # ligne noire parent/enfant
        draw.line(
            (
                center_x,
                main_box[1],
                px,
                parent_box[3]
            ),
            fill="black",
            width=5
        )

    # ========= PARTNER =========
    if partner_id:

        mx = center_x + 260
        my = center_y

        partner_box = draw_person(
            partner_id,
            mx,
            my
        )

        # ligne rouge amour
        draw.line(
            (
                main_box[2],
                center_y,
                partner_box[0],
                my
            ),
            fill="red",
            width=5
        )

    # ========= SIBLINGS =========
    if siblings:

        spacing = 230

        start_x = center_x - (
            (len(siblings) - 1) * spacing
        ) // 2

        for i, sid in enumerate(siblings):

            sx = start_x + i * spacing
            sy = center_y

            sibling_box = draw_person(
                sid,
                sx,
                sy
            )

            # ligne fraternité noire
            draw.line(
                (
                    sibling_box[2],
                    sy,
                    main_box[0],
                    center_y
                ),
                fill="black",
                width=5
            )

    # ========= CHILDREN =========
    if children:

        spacing = 230

        start_x = center_x - (
            (len(children) - 1) * spacing
        ) // 2

        for i, cid in enumerate(children):

            cx = start_x + i * spacing
            cy = center_y + 250

            child_box = draw_person(
                cid,
                cx,
                cy
            )

            # ligne noire parent/enfant
            draw.line(
                (
                    center_x,
                    main_box[3],
                    cx,
                    child_box[1]
                ),
                fill="black",
                width=5
            )

    # ========= LEGEND =========
    draw.text(
        (40, 40),
        "Black = family links",
        fill="black",
        font=font
    )

    draw.text(
        (40, 75),
        "Red = heart links",
        fill="red",
        font=font
    )

    # ========= SAVE =========
    path = f"tree_{user_id}_{random.randint(1,999999)}.png"

    img.save(path)

    return path


# ========= FAMILY UTILS =========

def get_parent(user_id):

    cursor.execute(
        "SELECT parent_id FROM family WHERE user_id=?",
        (user_id,)
    )

    r = cursor.fetchone()

    return r[0] if r else None


def get_children(user_id):

    cursor.execute(
        "SELECT user_id FROM family WHERE parent_id=?",
        (user_id,)
    )

    return [x[0] for x in cursor.fetchall()]

# ========= GET USERNAME =========

async def get_username_text(user_id):

    try:

        user = await client.get_entity(user_id)

        if user.username:
            return f"@{user.username}"

    except:
        pass

    return "No username"

def is_family_link(user1, user2):

    # parent direct
    if get_parent(user1) == user2:
        return True

    if get_parent(user2) == user1:
        return True

    # frères/sœurs
    p1 = get_parent(user1)
    p2 = get_parent(user2)

    if p1 and p2 and p1 == p2:
        return True

    # grand parent
    gp1 = get_parent(p1) if p1 else None
    gp2 = get_parent(p2) if p2 else None

    if gp1 == user2 or gp2 == user1:
        return True

    return False



# ========= CLEAN NAME =========
def clean_name(name):
    if not name:
        return "user"

    name = unidecode(str(name))
    name = re.sub(r'[^a-zA-Z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()

    if not name:
        return "user"

    return name.lower()


def get_cached_name(user_id):
    data = profile_cache.get(str(user_id))
    if data and data.get("name"):
        return clean_name(data["name"])

    cursor.execute("SELECT name FROM profiles WHERE user_id=?", (user_id,))
    r = cursor.fetchone()

    if r and r[0]:
        return clean_name(r[0])

    return "user"


def get_profile_pic(user_id):
    data = profile_cache.get(str(user_id))
    if data and data.get("photo"):
        if os.path.exists(data["photo"]):
            return data["photo"]

    cursor.execute("SELECT photo FROM profiles WHERE user_id=?", (user_id,))
    r = cursor.fetchone()

    return r[0] if r else None

# ========= FRIENDS =========
def get_friends(user_id):

    cursor.execute(
        "SELECT friend_id FROM friends WHERE user_id=?",
        (user_id,)
    )

    return [x[0] for x in cursor.fetchall()]


# ========= LINES =========
def draw_line_edge(draw, x1, y1, x2, y2, start_offset, end_offset):

    dx = x2 - x1
    dy = y2 - y1
    dist = math.sqrt(dx * dx + dy * dy)

    if dist == 0:
        return

    sx = x1 + dx * (start_offset / dist)
    sy = y1 + dy * (start_offset / dist)

    ex = x2 - dx * (end_offset / dist)
    ey = y2 - dy * (end_offset / dist)

    draw.line(
        (sx, sy, ex, ey),
        fill="#ff2b2b",
        width=4
    )


# ========= DRAW =========
def draw_circle(user_id):

    size = 1100

    img = Image.new("RGB", (size, size), "#5fa8d3")
    draw = ImageDraw.Draw(img)

    center_x = size // 2
    center_y = size // 2

    friends = get_friends(user_id)
    total = len(friends)

    # ========= ADAPTATION =========
    if total <= 4:
        center_size = 170
        friend_size = 120
        radius = 360

    elif total <= 8:
        center_size = 150
        friend_size = 105
        radius = 390

    elif total <= 12:
        center_size = 135
        friend_size = 90
        radius = 410

    elif total <= 18:
        center_size = 120
        friend_size = 80
        radius = 430

    else:
        center_size = 105
        friend_size = 70
        radius = 450

    # ========= FONT =========
    try:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/system/fonts/Roboto-Bold.ttf"
        ]

        font_path = None

        for p in font_paths:
            if os.path.exists(p):
                font_path = p
                break

        if font_path:
            font_main = ImageFont.truetype(font_path, max(16, center_size // 6))
            font_friend = ImageFont.truetype(font_path, max(14, friend_size // 5))
        else:
            font_main = ImageFont.load_default()
            font_friend = ImageFont.load_default()

    except:
        font_main = ImageFont.load_default()
        font_friend = ImageFont.load_default()

    # ========= USER =========
    name = get_cached_name(user_id)
    pic = get_profile_pic(user_id)

    ux = center_x - center_size // 2
    uy = center_y - center_size // 2

    has_photo = pic and os.path.exists(pic)

    # ========= PHOTO =========
    if has_photo:
        try:
            p = Image.open(pic).convert("RGB")
            p = p.resize((center_size, center_size))
            img.paste(p, (ux, uy))
        except:
            has_photo = False

    # ========= USER NO PHOTO =========
    if not has_photo:

        bbox = draw.textbbox((0, 0), name, font=font_main)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        rw = max(170, tw + 40)
        rh = 55

        rx1 = center_x - rw // 2
        ry1 = center_y - rh // 2
        rx2 = center_x + rw // 2
        ry2 = center_y + rh // 2

        draw.rounded_rectangle(
            [rx1, ry1, rx2, ry2],
            radius=10,
            outline="#ff2b2b",
            width=5,
            fill="#243447"
        )

        draw.text(
            (center_x - tw // 2, center_y - th // 2),
            name,
            fill="white",
            font=font_main
        )

    else:

        bbox = draw.textbbox((0, 0), name, font=font_main)
        tw = bbox[2] - bbox[0]

        draw.text(
            (center_x - tw // 2, uy - 35),
            name,
            fill="white",
            font=font_main
        )

    # ========= FRIENDS =========
    for i, fid in enumerate(friends):

        angle = (2 * math.pi * i) / max(total, 1)

        fx = int(center_x + radius * math.cos(angle))
        fy = int(center_y + radius * math.sin(angle))

        fname = get_cached_name(fid) or "user"
        fpic = get_profile_pic(fid)

        f_has_photo = fpic and os.path.exists(fpic)

        # ========= LIGNE =========
        draw_line_edge(
            draw,
            center_x,
            center_y,
            fx,
            fy,
            center_size // 2 + 10,
            friend_size // 2 + 10
        )

        # ========= PHOTO =========
        if f_has_photo:
            try:
                p = Image.open(fpic).convert("RGB")
                p = p.resize((friend_size, friend_size))
                img.paste(p, (fx - friend_size // 2, fy - friend_size // 2))
            except:
                f_has_photo = False

        # ========= FRIEND NO PHOTO =========
        if not f_has_photo:

            bbox = draw.textbbox((0, 0), fname, font=font_friend)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            rw = max(140, tw + 30)
            rh = 45

            rx1 = fx - rw // 2
            ry1 = fy - rh // 2
            rx2 = fx + rw // 2
            ry2 = fy + rh // 2

            draw.rounded_rectangle(
                [rx1, ry1, rx2, ry2],
                radius=10,
                outline="#ff2b2b",
                width=4,
                fill="#26334a"
            )

            draw.text(
                (fx - tw // 2, fy - th // 2),
                fname,
                fill="white",
                font=font_friend
            )

        else:

            bbox = draw.textbbox((0, 0), fname, font=font_friend)
            tw = bbox[2] - bbox[0]

            draw.text(
                (fx - tw // 2, fy - friend_size // 2 - 28),
                fname,
                fill="white",
                font=font_friend
            )

    # ========= SAVE =========
    path = f"circle_{user_id}_{random.randint(1,999999)}.png"
    img.save(path)

    return path

def save_groups():
    with open(GROUP_FILE, "w") as f:
        json.dump(list(groups_db), f)

def load_groups():
    global groups_db
    try:
        with open(GROUP_FILE, "r") as f:
            groups_db = set(tuple(x) for x in json.load(f))
    except:
        groups_db = set()

def load_groups():
    global groups_db
    try:
        with open(GROUP_FILE, "r") as f:
            groups_db = set(tuple(x) for x in json.load(f))
    except:
        groups_db = set()

def add_group(chat_id, name, username, members):
    key = (chat_id, name, username, members)

    if key not in groups_db:
        groups_db.add(key)
        save_groups()

def safe_amount(text):
    if not text.isdigit():
        return None
    return int(text)

def get_user(uid):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users(user_id) VALUES(?)", (uid,))
        conn.commit()
        return get_user(uid)
    return user

def parse_amount(text):
    text = text.strip()

    # ❌ REFUSE négatif
    if text.startswith("-"):
        raise ValueError("Negative not allowed")

    # ✅ FORMAT 1+4 → 10000
    if "+" in text:
        parts = text.split("+")

        if len(parts) != 2:
            raise ValueError("Invalid format")

        base, zeros = parts

        if not base.isdigit() or not zeros.isdigit():
            raise ValueError("Invalid format")

        return int(base) * (10 ** int(zeros))

    # ✅ FORMAT NORMAL (juste nombre)
    if not text.isdigit():
        raise ValueError("Invalid amount")

    return int(text)

def reset_limits(user):
    now = int(time.time())
    if now - user[10] > 86400:
        cursor.execute("UPDATE users SET kills_today=0, robs_today=0, last_reset=? WHERE user_id=?", (now, user[0]))
        conn.commit()

async def is_real_user(user_id):
    try:
        user = await client.get_entity(user_id)
        return not user.bot
    except:
        return False

def create_grid():
    letters = list(string.ascii_lowercase[:10])
    return {f"{l}{n}": None for l in letters for n in range(1, 11)}

def random_treasures():
    letters = list(string.ascii_lowercase[:10])
    coords = [f"{l}{n}" for l in letters for n in range(1, 11)]
    return set(random.sample(coords, 5))

def distance(c1, c2):
    x1 = ord(c1[0]) - 97
    y1 = int(c1[1:]) - 1
    x2 = ord(c2[0]) - 97
    y2 = int(c2[1:]) - 1
    return max(abs(x1 - x2), abs(y1 - y2))


def update_distances(game):
    for coord, val in game["grid"].items():
        if isinstance(val, int):
            remaining = [t for t in game["treasures"] if t not in game["found"]]

            if remaining:
                dists = [distance(coord, t) for t in remaining]
                game["grid"][coord] = min(dists)
            else:
                game["grid"][coord] = val


def draw_grid(game):
    size = 700
    cell = size // 10

    img = Image.new("RGB", (size + 80, size + 80), "#5fa8d3")
    draw = ImageDraw.Draw(img)

    try:
        font_path = "/system/fonts/Roboto-Regular.ttf"
        font_big = ImageFont.truetype(font_path, 30)
        font_cell = ImageFont.truetype(font_path, 25)
    except:
        font_big = ImageFont.load_default()
        font_cell = ImageFont.load_default()

    # ========= LETTRES A-J =========
    for i in range(10):
        text = chr(65 + i)
        bbox = draw.textbbox((0, 0), text, font=font_big)
        w = bbox[2] - bbox[0]

        x = 80 + i * cell + (cell // 2) - (w // 2)
        draw.text((x, 30), text, fill="black", font=font_big)

    # ========= CHIFFRES 1-10 =========
    for j in range(10):
        text = str(j + 1)
        bbox = draw.textbbox((0, 0), text, font=font_big)
        h = bbox[3] - bbox[1]

        y = 80 + j * cell + (cell // 2) - (h // 2)
        draw.text((25, y), text, fill="black", font=font_big)

    # ========= GRILLE =========
    for i in range(10):
        for j in range(10):

            x1 = 80 + i * cell
            y1 = 80 + j * cell
            x2 = x1 + cell
            y2 = y1 + cell

            coord = f"{chr(97+i)}{j+1}"
            val = game["grid"][coord]

            draw.rectangle([x1, y1, x2, y2], outline="black")

            # ========= TEXTE =========
            text = None

            if val == "X":
                text = "X"
            elif val == "S":
                text = "S"
            elif isinstance(val, int):
                text = str(val)

            if text:
                bbox = draw.textbbox((0, 0), text, font=font_cell)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]

                x_center = x1 + (cell // 2) - (w // 2)
                y_center = y1 + (cell // 2) - (h // 2)

                color = "black"
                if text == "X":
                    color = "red"

                draw.text((x_center, y_center), text, fill=color, font=font_cell)

    # ========= SAVE IMAGE =========
    path = f"sonar_{random.randint(1,999999)}.png"
    img.save(path)
    return path

def get_random_4pic():
    folders = os.listdir("4pic")
    if not folders:
        return None

    folder = random.choice(folders)
    path = os.path.join("4pic", folder)

    data_path = os.path.join(path, "data.json")
    if not os.path.exists(data_path):
        return None

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data.get("answer"):
        return None

    return data
def add_money(user_id, amount):
    cursor.execute(
        "INSERT OR IGNORE INTO users(user_id, cash, reputation) VALUES (?, 0.0, 0.0)",
        (user_id,)
    )
    cursor.execute(
        "UPDATE users SET cash = cash + ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()


def add_rep(user_id, amount):
    cursor.execute(
        "INSERT OR IGNORE INTO users(user_id, cash, reputation) VALUES (?, 0.0, 0.0)",
        (user_id,)
    )
    cursor.execute(
        "UPDATE users SET reputation = ROUND(reputation + ?, 2) WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()
# ========= START =========
@client.on(events.NewMessage(pattern="/start"))
async def start(event):
    if event.is_private:
        await event.respond(
            "🔥 Welcome to Crime Game Bot!\nFight, steal, earn money and dominate 😈",
            buttons=[
                [Button.inline("Help", b"help")],
                [Button.url("Group Support", "https://t.me/Mangas_Animes_Quizz")],
                [Button.url("Add Me", f"https://t.me/{BOT_USERNAME}?startgroup=true")]
            ]
        )

@client.on(events.CallbackQuery)
async def cb(event):
    if event.data == b"help":
        await event.edit("""
Commands:
/acc /account
/kill
/rob
/daily
/pay
/deposit
/withdraw
/medical
/donatedblood/
/fuse
""")

# ========= LIST GROUPS =========
@client.on(events.NewMessage(pattern=r"^/groups$"))
async def list_groups(event):
    if not event.is_private:
        return

    if not groups_db:
        return await event.reply("No groups detected yet.")

    text = "📊 Bot Groups:\n\n"

    for i, (gid, name, username, members) in enumerate(groups_db, start=1):
        if username:
            text += f"{i}. {name}\n   @{username}\n   ID: {gid}\n   👥 {members} members\n\n"
        else:
            text += f"{i}. {name}\n   (no username)\n   ID: {gid}\n   👥 {members} members\n\n"

        if len(text) > 3500:
            await event.reply(text)
            text = ""

    if text:
        await event.reply(text)


# ========= TREE COMMAND =========
@client.on(events.NewMessage(pattern=r"^/tree$"))
async def tree_cmd(event):

    target_id = event.sender_id

    # si reply -> montre l'arbre de la personne
    if event.is_reply:

        msg = await event.get_reply_message()

        user = await msg.get_sender()

        if user:
            target_id = user.id

    try:

        img = draw_tree(target_id)

        await event.reply(
            file=img
        )

    except Exception as e:

        print(e)

        await event.reply(
            f"Error: {e}"
        )



# ========= ADOPT =========

@client.on(events.NewMessage(pattern=r"^/adopt$"))
async def adopt(event):

    if not event.is_reply:
        return await event.reply(
            "Reply to someone."
        )

    msg = await event.get_reply_message()

    target = await msg.get_sender()

    sender = await event.get_sender()

    if not target:
        return

    if getattr(target, "bot", False):
        return await event.reply(
            "Bots are not allowed."
        )

    if target.id == sender.id:
        return await event.reply(
            "You can't adopt yourself."
        )

    # max 7 enfants
    if len(get_children(sender.id)) >= 7:
        return await event.reply(
            "You already reached the max amount of children."
        )

    # déjà un parent
    if get_parent(target.id):
        return await event.reply(
            "This person already has a parent."
        )

    # bloque incest/family
    if is_family_link(sender.id, target.id):
        return await event.reply(
            "Family links like this are forbidden."
        )

    await event.reply(

        f"[{clean_name(target.first_name)}](tg://user?id={target.id}), "
        f"[{clean_name(sender.first_name)}](tg://user?id={sender.id}) "
        f"wants to make you their offspring.",

        buttons=[
            [
                Button.inline(
                    "Yes ✅",
                    f"adopt_yes_{sender.id}_{target.id}".encode()
                ),

                Button.inline(
                    "No ❌",
                    f"adopt_no_{sender.id}_{target.id}".encode()
                )
            ]
        ],

        link_preview=False
    )


# ========= ADOPT YES =========

@client.on(events.CallbackQuery(pattern=b"adopt_yes_(\\d+)_(\\d+)"))
async def adopt_yes(event):

    parent_id = int(event.pattern_match.group(1))
    child_id = int(event.pattern_match.group(2))

    if event.sender_id != child_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    # revérifie
    if get_parent(child_id):
        return await event.edit(
            "You already have a parent."
        )

    if len(get_children(parent_id)) >= 7:
        return await event.edit(
            "This person already has too many children."
        )

    if is_family_link(parent_id, child_id):
        return await event.edit(
            "Family links like this are forbidden."
        )

    cursor.execute(
        "INSERT OR REPLACE INTO family(user_id, parent_id) VALUES (?, ?)",
        (child_id, parent_id)
    )

    conn.commit()

    add_money(parent_id, 3000)
    add_money(child_id, 3000)

    await event.edit(
        "Adoption accepted! +3000$"
    )


# ========= ADOPT NO =========

@client.on(events.CallbackQuery(pattern=b"adopt_no_(\\d+)_(\\d+)"))
async def adopt_no(event):

    child_id = int(event.pattern_match.group(2))

    if event.sender_id != child_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    await event.edit(
        "Adoption declined."
    )


# ========= FAMILY =========

@client.on(events.NewMessage(pattern=r"^/family$"))
async def family_cmd(event):

    user_id = event.sender_id

    text = "👨‍👩‍👧 FAMILY\n\n"

    # ========= PARENT =========
    parent = get_parent(user_id)

    if parent:

        uname = await get_username_text(parent)

        text += (
            f"Parent      | "
            f"{get_cached_name(parent)} | "
            f"{uname}\n"
        )

    # ========= CHILDREN =========
    children = get_children(user_id)

    for child in children:

        uname = await get_username_text(child)

        text += (
            f"Child       | "
            f"{get_cached_name(child)} | "
            f"{uname}\n"
        )

    # ========= SIBLINGS =========
    parent_id = get_parent(user_id)

    if parent_id:

        cursor.execute(
            """
            SELECT user_id
            FROM family
            WHERE parent_id=?
            AND user_id!=?
            """,
            (parent_id, user_id)
        )

        siblings = [x[0] for x in cursor.fetchall()]

        for sib in siblings:

            uname = await get_username_text(sib)

            text += (
                f"Sibling    | "
                f"{get_cached_name(sib)} | "
                f"{uname}\n"
            )

    await event.reply(text)


# ========= DISOWN =========

@client.on(events.NewMessage(pattern=r"^/disown(?: @(\w+))?$"))
async def disown(event):

    parent_id = event.sender_id

    target = None

    # ========= REPLY =========
    if event.is_reply:

        msg = await event.get_reply_message()

        target = await msg.get_sender()

    # ========= USERNAME =========
    else:

        m = event.pattern_match.group(1)

        if m:

            try:
                target = await client.get_entity(m)
            except:
                return await event.reply(
                    "User not found."
                )

    if not target:
        return await event.reply(
            "Reply to your child or use @username."
        )

    # ========= CHECK CHILD =========
    if get_parent(target.id) != parent_id:
        return await event.reply(
            "This person is not your child."
        )

    user = get_user(parent_id)

    if user[1] < 3000:
        return await event.reply(
            "You need 3000$ cash."
        )

    await event.reply(

        f"Are you sure you want to disown "
        f"[{clean_name(target.first_name)}]"
        f"(tg://user?id={target.id})?\n\n"
        f"This will cost you 3000$.",

        buttons=[
            [
                Button.inline(
                    "Yes ✅",
                    f"disown_yes_{parent_id}_{target.id}".encode()
                ),

                Button.inline(
                    "No ❌",
                    f"disown_no_{parent_id}".encode()
                )
            ]
        ],

        link_preview=False
    )


# ========= DISOWN YES =========

@client.on(events.CallbackQuery(pattern=b"disown_yes_(\\d+)_(\\d+)"))
async def disown_yes(event):

    parent_id = int(event.pattern_match.group(1))
    child_id = int(event.pattern_match.group(2))

    if event.sender_id != parent_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    user = get_user(parent_id)

    if user[1] < 3000:
        return await event.edit(
            "You need 3000$ cash."
        )

    if get_parent(child_id) != parent_id:
        return await event.edit(
            "This person is no longer your child."
        )

    cursor.execute(
        "DELETE FROM family WHERE user_id=?",
        (child_id,)
    )

    cursor.execute(
        "UPDATE users SET cash=cash-3000 WHERE user_id=?",
        (parent_id,)
    )

    conn.commit()

    await event.edit(
        "Child removed from your family. -3000$"
    )


# ========= DISOWN NO =========

@client.on(events.CallbackQuery(pattern=b"disown_no_(\\d+)"))
async def disown_no(event):

    user_id = int(event.pattern_match.group(1))

    if event.sender_id != user_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    await event.edit(
        "Cancelled."
    )

# ========= RUNAWAY =========

@client.on(events.NewMessage(pattern=r"^/runaway$"))
async def runaway(event):

    user_id = event.sender_id

    parent = get_parent(user_id)

    if not parent:
        return await event.reply(
            "You don't have a parent."
        )

    user = get_user(user_id)

    if user[1] < 3000:
        return await event.reply(
            "You need 3000$ cash."
        )

    await event.reply(

        "Are you sure you want to run away from home?\n\n"
        "This will cost you 3000$.",

        buttons=[
            [
                Button.inline(
                    "Yes ✅",
                    f"runaway_yes_{user_id}".encode()
                ),

                Button.inline(
                    "No ❌",
                    f"runaway_no_{user_id}".encode()
                )
            ]
        ]
    )


# ========= RUNAWAY YES =========

@client.on(events.CallbackQuery(pattern=b"runaway_yes_(\\d+)"))
async def runaway_yes(event):

    user_id = int(event.pattern_match.group(1))

    if event.sender_id != user_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    parent = get_parent(user_id)

    if not parent:
        return await event.edit(
            "You already have no parent."
        )

    user = get_user(user_id)

    if user[1] < 3000:
        return await event.edit(
            "You need 3000$ cash."
        )

    cursor.execute(
        "DELETE FROM family WHERE user_id=?",
        (user_id,)
    )

    cursor.execute(
        "UPDATE users SET cash=cash-3000 WHERE user_id=?",
        (user_id,)
    )

    conn.commit()

    await event.edit(
        "You ran away from home. -3000$"
    )


# ========= RUNAWAY NO =========

@client.on(events.CallbackQuery(pattern=b"runaway_no_(\\d+)"))
async def runaway_no(event):

    user_id = int(event.pattern_match.group(1))

    if event.sender_id != user_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    await event.edit(
        "Cancelled."
    )

# ========= MAKE PARENT =========

@client.on(events.NewMessage(pattern=r"^/makeparent$"))
async def makeparent(event):

    if not event.is_reply:
        return await event.reply(
            "Reply to someone."
        )

    child_id = event.sender_id

    msg = await event.get_reply_message()
    parent = await msg.get_sender()

    if not parent:
        return

    if getattr(parent, "bot", False):
        return await event.reply(
            "Bots are not allowed."
        )

    if parent.id == child_id:
        return await event.reply(
            "You can't do this to yourself."
        )

    # déjà parent ?
    cursor.execute(
        "SELECT parent_id FROM family WHERE user_id=?",
        (child_id,)
    )

    existing = cursor.fetchone()

    if existing:
        return await event.reply(
            "You already have a parent."
        )

    # max 7 enfants
    cursor.execute(
        "SELECT COUNT(*) FROM family WHERE parent_id=?",
        (parent.id,)
    )

    child_count = cursor.fetchone()[0]

    if child_count >= 7:
        return await event.reply(
            "This person already has 7 children."
        )

    sender = await event.get_sender()

    sender_name = clean_name(
        sender.first_name or "user"
    )

    parent_name = clean_name(
        parent.first_name or "user"
    )

    await event.reply(

        f"[{parent_name}](tg://user?id={parent.id}), "
        f"[{sender_name}](tg://user?id={child_id}) "
        f"wants to become one of your children.",

        buttons=[
            [
                Button.inline(
                    "Yes ✅",
                    f"parent_yes_{child_id}_{parent.id}".encode()
                ),

                Button.inline(
                    "No ❌",
                    f"parent_no_{child_id}_{parent.id}".encode()
                )
            ]
        ],

        link_preview=False
    )


@client.on(events.CallbackQuery(pattern=b"parent_yes_(\\d+)_(\\d+)"))
async def parent_yes(event):

    child_id = int(event.pattern_match.group(1))
    parent_id = int(event.pattern_match.group(2))

    if event.sender_id != parent_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    # vérifie encore
    cursor.execute(
        "SELECT parent_id FROM family WHERE user_id=?",
        (child_id,)
    )

    if cursor.fetchone():
        return await event.edit(
            "This user already has a parent."
        )

    cursor.execute(
        "INSERT INTO family(user_id, parent_id) VALUES (?, ?)",
        (child_id, parent_id)
    )

    conn.commit()

    add_money(child_id, 3000)
    add_money(parent_id, 3000)

    await event.edit(
        "Family link created! +3000$"
    )


@client.on(events.CallbackQuery(pattern=b"parent_no_(\\d+)_(\\d+)"))
async def parent_no(event):

    parent_id = int(event.pattern_match.group(2))

    if event.sender_id != parent_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    await event.edit(
        "Request declined."
    )


# ========= SIBLING =========

@client.on(events.NewMessage(pattern=r"^/sibling$"))
async def sibling(event):

    if not event.is_reply:
        return await event.reply(
            "Reply to someone."
        )

    user1 = event.sender_id

    msg = await event.get_reply_message()
    target = await msg.get_sender()

    if not target:
        return

    if getattr(target, "bot", False):
        return await event.reply(
            "Bots are not allowed."
        )

    if target.id == user1:
        return await event.reply(
            "You can't do this to yourself."
        )

    # déjà siblings ?
    cursor.execute(
        """
        SELECT 1 FROM siblings
        WHERE
        (user1=? AND user2=?)
        OR
        (user1=? AND user2=?)
        """,
        (user1, target.id, target.id, user1)
    )

    if cursor.fetchone():
        return await event.reply(
            "You are already siblings."
        )

    sender = await event.get_sender()

    sender_name = clean_name(
        sender.first_name or "user"
    )

    target_name = clean_name(
        target.first_name or "user"
    )

    await event.reply(

        f"[{target_name}](tg://user?id={target.id}), "
        f"[{sender_name}](tg://user?id={user1}) "
        f"wants to be your sibling.",

        buttons=[
            [
                Button.inline(
                    "Yes ✅",
                    f"sibling_yes_{user1}_{target.id}".encode()
                ),

                Button.inline(
                    "No ❌",
                    f"sibling_no_{user1}_{target.id}".encode()
                )
            ]
        ],

        link_preview=False
    )


@client.on(events.CallbackQuery(pattern=b"sibling_yes_(\\d+)_(\\d+)"))
async def sibling_yes(event):

    user1 = int(event.pattern_match.group(1))
    user2 = int(event.pattern_match.group(2))

    if event.sender_id != user2:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    cursor.execute(
        """
        INSERT INTO siblings(user1, user2)
        VALUES (?, ?)
        """,
        (user1, user2)
    )

    conn.commit()

    add_money(user1, 3000)
    add_money(user2, 3000)

    await event.edit(
        "Sibling link created! +3000$"
    )


@client.on(events.CallbackQuery(pattern=b"sibling_no_(\\d+)_(\\d+)"))
async def sibling_no(event):

    user2 = int(event.pattern_match.group(2))

    if event.sender_id != user2:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    await event.edit(
        "Request declined."
    )


# ========= REMOVE SIBLING =========

@client.on(events.NewMessage(pattern=r"^/removesibling(?: (.+))?$"))
async def remove_sibling(event):

    user_id = event.sender_id
    target = None

    # reply
    if event.is_reply:

        msg = await event.get_reply_message()
        target = await msg.get_sender()

    # username
    elif event.pattern_match.group(1):

        username = event.pattern_match.group(1).replace("@", "")

        try:
            target = await client.get_entity(username)
        except:
            return await event.reply(
                "User not found."
            )

    else:
        return await event.reply(
            "Reply or use username."
        )

    if not target:
        return

    # vérifie sibling
    cursor.execute(
        """
        SELECT 1 FROM siblings
        WHERE
        (user1=? AND user2=?)
        OR
        (user1=? AND user2=?)
        """,
        (user_id, target.id, target.id, user_id)
    )

    if not cursor.fetchone():
        return await event.reply(
            "This person is not your sibling."
        )

    user = get_user(user_id)

    if user[1] < 3000:
        return await event.reply(
            "You need 3000$."
        )

    target_name = clean_name(
        target.first_name or "user"
    )

    await event.reply(

        f"Are you sure you want to remove "
        f"[{target_name}](tg://user?id={target.id}) "
        f"from your siblings?\n\n"
        f"Cost: 3000$",

        buttons=[
            [
                Button.inline(
                    "Yes ✅",
                    f"rs_yes_{user_id}_{target.id}".encode()
                ),

                Button.inline(
                    "No ❌",
                    f"rs_no_{user_id}".encode()
                )
            ]
        ],

        link_preview=False
    )


@client.on(events.CallbackQuery(pattern=b"rs_yes_(\\d+)_(\\d+)"))
async def rs_yes(event):

    user_id = int(event.pattern_match.group(1))
    target_id = int(event.pattern_match.group(2))

    if event.sender_id != user_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    user = get_user(user_id)

    if user[1] < 3000:
        return await event.edit(
            "You need 3000$."
        )

    cursor.execute(
        """
        DELETE FROM siblings
        WHERE
        (user1=? AND user2=?)
        OR
        (user1=? AND user2=?)
        """,
        (user_id, target_id, target_id, user_id)
    )

    cursor.execute(
        "UPDATE users SET cash=cash-3000 WHERE user_id=?",
        (user_id,)
    )

    conn.commit()

    await event.edit(
        "Sibling removed. -3000$"
    )


@client.on(events.CallbackQuery(pattern=b"rs_no_(\\d+)"))
async def rs_no(event):

    user_id = int(event.pattern_match.group(1))

    if event.sender_id != user_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    await event.edit(
        "Cancelled."
    )
# ========= TRACK GROUPS =========
@client.on(events.NewMessage)
async def track_groups(event):
    if not event.is_group:
        return

    chat = await event.get_chat()
    name = getattr(chat, "title", "Unknown")
    username = getattr(chat, "username", None)

    try:
        full = await client(GetFullChannelRequest(event.chat_id))
        members = full.full_chat.participants_count
    except:
        members = "unknown"

    groups_db.add((event.chat_id, name, username, members))
    save_groups()


#============ friend zone ======

@client.on(events.NewMessage)
async def track_users(event):

    if not event.sender:
        return

    sender = await event.get_sender()

    # ignore bots/channels
    if getattr(sender, "bot", False) or hasattr(sender, "title"):
        return

    user_id = sender.id

    # ========= NAME =========
    first = sender.first_name or ""
    last = sender.last_name or ""

    if first and last:
        name = f"{first} {last}"

    elif first:
        name = first

    elif sender.username:
        name = sender.username

    else:
        name = f"User{user_id}"

    # ========= PHOTO =========
    photo_path = None

    try:
        photo_path = await client.download_profile_photo(
            sender,
            file=f"profiles/{user_id}.jpg"
        )
    except:
        pass

    # ========= SQLITE SAVE =========
    cursor.execute("""

        INSERT INTO profiles(user_id, name, photo)
        VALUES (?, ?, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET

            name=excluded.name,

            photo=COALESCE(
                excluded.photo,
                profiles.photo
            )

    """, (

        user_id,
        name,
        photo_path

    ))

    conn.commit()

    # ========= JSON CACHE SAVE =========
    profile_cache[str(user_id)] = {
        "name": name,
        "photo": photo_path if photo_path else profile_cache.get(str(user_id), {}).get("photo")
    }

    save_profile_cache()
# ========= FRIENDS IMAGE =========
@client.on(events.NewMessage(pattern=r"^/friends$"))
async def friends_cmd(event):

    try:

        # ========= SI REPLY =========
        if event.is_reply:

            msg = await event.get_reply_message()

            target = await msg.get_sender()

            if not target:
                return await event.reply(
                    "User not found."
                )

            target_id = target.id

        else:

            # soi-même
            target_id = event.sender_id

        # ========= IMAGE =========
        img = draw_circle(target_id)

        await event.reply(file=img)

    except Exception as e:

        print(e)

        await event.reply(
            f"❌ Error : {e}"
        )

# ========= FRIEND =========
@client.on(events.NewMessage(pattern=r"^/friend$"))
async def friend(event):

    sender_id = event.sender_id

    if not event.is_reply:
        return await event.reply(
            "Reply to someone."
        )

    msg = await event.get_reply_message()

    target = await msg.get_sender()

    if not target:
        return

    if getattr(target, "bot", False):
        return await event.reply(
            "Bots not allowed"
        )

    if target.id == sender_id:
        return await event.reply(
            "You can't friend yourself."
        )

    if target.id in get_friends(sender_id):
        return await event.reply(
            "Already friends"
        )

    sender = await event.get_sender()

    sender_name = clean_name(
        sender.first_name or "user"
    )

    target_name = clean_name(
        target.first_name or "user"
    )

    await event.reply(

        f"Hey [{target_name}](tg://user?id={target.id}), "
        f"[{sender_name}](tg://user?id={sender_id}) "
        f"admires your qualities. Let's become friends!",

        buttons=[
            [
                Button.inline(
                    "Yes",
                    f"f_yes_{sender_id}_{target.id}".encode()
                ),

                Button.inline(
                    "No",
                    f"f_no_{sender_id}_{target.id}".encode()
                )
            ]
        ],

        link_preview=False
    )


# ========= ACCEPT =========
@client.on(events.CallbackQuery(pattern=b"f_yes_(\\d+)_(\\d+)"))
async def f_yes(event):

    s = int(
        event.pattern_match.group(1)
    )

    t = int(
        event.pattern_match.group(2)
    )

    if event.sender_id != t:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    if t in get_friends(s):
        return await event.edit(
            "Already friends."
        )

    add_friend(s, t)

    add_money(s, 3000)
    add_money(t, 3000)

    await event.edit(
        "Friend added! +3000$"
    )


# ========= DECLINE =========
@client.on(events.CallbackQuery(pattern=b"f_no_(\\d+)_(\\d+)"))
async def f_no(event):

    s = int(
        event.pattern_match.group(1)
    )

    t = int(
        event.pattern_match.group(2)
    )

    if event.sender_id != t:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    await event.edit(
        "Request declined."
    )


# ========= UNFRIEND =========

@client.on(events.NewMessage(pattern=r"^/unfriend$"))
async def unfriend(event):

    user_id = event.sender_id

    # ========= REPLY MODE =========
    if event.is_reply:

        msg = await event.get_reply_message()

        target = await msg.get_sender()

        if not target:
            return

        if target.id not in get_friends(user_id):
            return await event.reply(
                "Not your friend"
            )

        user = get_user(user_id)

        # cash index
        if user[1] < 3000:
            return await event.reply(
                "You need 3000$ cash."
            )

        remove_friend(
            user_id,
            target.id
        )

        cursor.execute(
            "UPDATE users SET cash=cash-3000 WHERE user_id=?",
            (user_id,)
        )

        conn.commit()

        target_name = clean_name(
            target.first_name or "user"
        )

        return await event.reply(
            f"{target_name} has been removed from your friends."
        )

    # ========= BUTTON MODE =========

    friends = get_friends(user_id)

    if not friends:
        return await event.reply(
            "You don't have friends."
        )

    buttons = []

    row = []

    for fid in friends:

        fname = get_cached_name(fid)

        row.append(

            Button.inline(
                fname[:18],
                f"uf_{user_id}_{fid}".encode()
            )
        )

        # 2 boutons par ligne
        if len(row) == 2:

            buttons.append(row)

            row = []

    if row:
        buttons.append(row)

    # bouton close
    buttons.append([
        Button.inline(
            "Close",
            f"ufclose_{user_id}".encode()
        )
    ])

    await event.reply(

        "⚠️ EACH PERSON REMOVED FROM YOUR FRIENDS "
        "WILL COST YOU 3000$",

        buttons=buttons
    )


# ========= BUTTON REMOVE =========
@client.on(events.CallbackQuery(pattern=b"uf_(\\d+)_(\\d+)"))
async def unfriend_button(event):

    user_id = int(
        event.pattern_match.group(1)
    )

    target_id = int(
        event.pattern_match.group(2)
    )

    # sécurité
    if event.sender_id != user_id:
        return await event.answer(
            "Not for you.",
            alert=True
        )

    if target_id not in get_friends(user_id):

        return await event.answer(
            "Already removed.",
            alert=True
        )

    user = get_user(user_id)

    if user[1] < 3000:

        return await event.answer(
            "Not enough cash.",
            alert=True
        )

    # ========= REMOVE =========
    remove_friend(
        user_id,
        target_id
    )

    cursor.execute(
        "UPDATE users SET cash=cash-3000 WHERE user_id=?",
        (user_id,)
    )

    conn.commit()

    # ========= REFRESH BUTTONS =========
    friends = get_friends(user_id)

    buttons = []

    row = []

    for fid in friends:

        fname = get_cached_name(fid)

        row.append(

            Button.inline(
                fname[:18],
                f"uf_{user_id}_{fid}".encode()
            )
        )

        if len(row) == 2:

            buttons.append(row)

            row = []

    if row:
        buttons.append(row)

    buttons.append([
        Button.inline(
            "Close",
            f"ufclose_{user_id}".encode()
        )
    ])

    target_name = get_cached_name(target_id)

    await event.edit(

        f"{target_name} has been removed from your friends.",

        buttons=buttons
    )


# ========= CLOSE =========
@client.on(events.CallbackQuery(pattern=b"ufclose_(\\d+)"))
async def unfriend_close(event):

    user_id = int(
        event.pattern_match.group(1)
    )

    if event.sender_id != user_id:

        return await event.answer(
            "Not for you.",
            alert=True
        )

    await event.delete()


@client.on(events.NewMessage(pattern=r"/frate"))
async def frate(event):
    if not event.is_reply:
        return

    target = await (await event.get_reply_message()).get_sender()

    await event.reply(
        "Choose rating:",
        buttons=[
            [Button.inline(str(i), f"rate_{i}_{target.id}") for i in range(1, 6)],
            [Button.inline(str(i), f"rate_{i}_{target.id}") for i in range(6, 11)]
        ]
    )

@client.on(events.CallbackQuery(pattern=b"rate_(\\d+)_(\\d+)"))
async def rate(event):
    value = int(event.pattern_match.group(1))
    target = int(event.pattern_match.group(2))
    sender = event.sender_id

    cursor.execute("SELECT * FROM ratings WHERE from_user=? AND to_user=?", (sender, target))
    if cursor.fetchone():
        return await event.answer("Already rated", alert=True)

    cursor.execute("INSERT INTO ratings VALUES (?,?,?)", (sender, target, value))
    conn.commit()

    add_rep(target, value)

    await event.edit("Rated!")

@client.on(events.NewMessage(pattern=r"/ratings"))
async def ratings(event):
    cursor.execute("""
    SELECT to_user, SUM(rating) as total
    FROM ratings
    GROUP BY to_user
    ORDER BY total DESC
    LIMIT 10
    """)

    data = cursor.fetchall()

    text = "🏆 Top Ratings:\n"

    for i, (uid, score) in enumerate(data, 1):
        try:
            user = await client.get_entity(uid)
            name = user.first_name
        except:
            name = str(uid)

        text += f"{i}. {name} - {score}\n"

    await event.reply(text)

# ========= ACCOUNT =========
@client.on(events.NewMessage(pattern=r"/acc(?: (.+))?"))
async def acc(event):

    user_id = None
    sender = None

    # reply
    if event.is_reply:
        reply = await event.get_reply_message()
        sender = await reply.get_sender()
        user_id = sender.id

    # @username
    elif event.pattern_match.group(1):
        try:
            sender = await client.get_entity(event.pattern_match.group(1))
            user_id = sender.id
        except:
            return await event.reply("User not found")

    # soi-même
    else:
        sender = await event.get_sender()
        user_id = sender.id

    # 🚫 bloquer bots
    if getattr(sender, "bot", False):
        return await event.reply("Bots don't have accounts.")

    user = get_user(user_id)
    name = sender.first_name

    text = f"""
{name}'s Profile

Money: 💲 {user[1]}
Bank Balance: 💲 {user[2]:,}
Health: {'❤️'*user[3] if user[3] > 0 else ''}
Weapon: {user[5].capitalize()}
Gemstone: {user[6].capitalize()}
Reputation: {round(user[4] / 10, 2)} ⭐️
"""

    if user_id == event.sender_id:
        await event.reply(text, buttons=[[Button.inline("Weapon", b"weapon")]])
    else:
        await event.reply(text)

# ========= SHOP =========
prices = {
    "punch":0,"blade":10000,"sword":25000,"bow":40000,
    "gun":70000,"pistolet":90000,"poison":120000,"rocket":200000
}

@client.on(events.CallbackQuery)
async def shop(event):
    if event.data == b"weapon":
        txt = "Weapons:\n"
        btn = []
        for w, p in prices.items():
            txt += f"{w} - ${p}\n"
            btn.append(Button.inline(w, w.encode()))
        await event.edit(txt, buttons=[btn])

    elif event.data.decode() in prices:
        w = event.data.decode()
        user = get_user(event.sender_id)

        if user[1] >= prices[w]:
            cursor.execute("UPDATE users SET cash=cash-?, weapon=? WHERE user_id=?",(prices[w], w, user[0]))
            conn.commit()

            # 💥 remplace le menu par message
            await event.edit(f"🔥 You bought {w.upper()}!")

        else:
            await event.answer("Not enough money")


#======== ADMIN RESERT RIT =========
@client.on(events.NewMessage(pattern=r"/rit (\d+) (\d+)"))
async def reset_rich(event):
    # 🔒 seulement en privé
    if not event.is_private:
        return await event.reply("Use this command in private.")

    admin_id = event.sender_id

    # 👉 (OPTIONNEL) protège la commande (recommandé)
    if admin_id != 5859678431:  # remplace par ton ID Telegram
        return await event.reply("Not authorized.")

    target_id = int(event.pattern_match.group(1))
    amount = int(event.pattern_match.group(2))

    if amount <= 0:
        return await event.reply("Invalid amount.")

    # créer user si pas existant
    cursor.execute(
        "INSERT OR IGNORE INTO users(user_id, cash, bank, reputation) VALUES (?, 0, 0, 0)",
        (target_id,)
    )

    # 💀 reset total
    cursor.execute(
        "UPDATE users SET cash=0, bank=? WHERE user_id=?",
        (amount, target_id)
    )

    conn.commit()

    await event.reply(
        f"💀 User {target_id} reset.\n"
        f"🏦 New balance: ${amount} (bank only)"
    )

#========= 4picgame=========
@client.on(events.NewMessage(pattern=r"/4p"))
async def start_4p(event):
    chat_id = event.chat_id

    data = None
    while not data:
        data = get_random_4pic()

    answer = data["answer"].lower()
    image = data["image"]

    hidden = ["+" for _ in answer]

    games_4p[chat_id] = {
        "answer": answer,
        "hidden": hidden,
        "start_time": time.time(),
        "last_hint": 0,
        "ended": False
    }

    await event.respond(
        f"Give 1 word for 4 pics ({len(answer)} letters, guide,use /4h :basic hint,,)",
        file=image
    )
@client.on(events.NewMessage(pattern=r"/4h"))
async def hint_4p(event):
    chat_id = event.chat_id

    if chat_id not in games_4p:
        return

    game = games_4p[chat_id]

    if game["ended"]:
        return

    now = time.time()
    if now - game["last_hint"] < 4:
        return

    answer = game["answer"]
    hidden = game["hidden"]

    if "+" not in hidden:
        await event.reply(
            f"Word is {''.join(hidden)} [{len(answer)} letters]\nUse /4p for new game"
        )
        return

    # révéler lettre aléatoire
    indexes = [i for i, l in enumerate(hidden) if l == "+"]
    i = random.choice(indexes)
    hidden[i] = answer[i]

    game["last_hint"] = now

    await event.reply(
        f"Word is {''.join(hidden)} [{len(answer)} letters]"
    )
@client.on(events.NewMessage)
async def answer_4p(event):
    chat_id = event.chat_id

    if chat_id not in games_4p:
        return

    game = games_4p[chat_id]

    if game["ended"]:
        return

    if not event.text:
        return

    user_answer = event.text.lower().strip()

    if user_answer != game["answer"]:
        return

    # ✅ BONNE RÉPONSE
    game["ended"] = True

    duration = time.time() - game["start_time"]

    # 💰 gain dynamique
    if duration <= 10:
        reward = 10000
    elif duration <= 30:
        reward = 8000
    elif duration <= 60:
        reward = 6000
    else:
        reward = 4000

    # 💾 AJOUT ARGENT (à adapter à ton système)
    add_money(event.sender_id, reward)

    # ⭐ réputation +0.1 (sans notif)
    add_rep(event.sender_id,1.00)

    await event.reply(
        f"Correct! You gained ${reward},took {duration:.2f}s. /4p to start a new game."
    )


# ========= LOTTERY =========
@client.on(events.NewMessage(pattern=r"^/lottery(?: (\d+))?$"))
async def lottery(event):
    global lottery_counter

    chat_id = event.chat_id
    user_id = event.sender_id
    arg = event.pattern_match.group(1)

    if not arg:
        return await event.reply(
            "Tip: /lottery [amount] to start lottery in group.\n"
            "It'll give all money to the winner!"
        )

    amount = int(arg)

    if amount <= 0 or amount > 1_000_000:
        return await event.reply("Amount must be between $1 and $1,000,000.")

    user = get_user(user_id)

    if user[1] < amount:
        return await event.reply("Not enough money.")

    # 💰 retirer argent
    cursor.execute("UPDATE users SET cash=cash-? WHERE user_id=?", (amount, user_id))
    conn.commit()

    lottery_counter += 1
    lot_id = lottery_counter

    if chat_id not in lotteries:
        lotteries[chat_id] = {}

    lotteries[chat_id][lot_id] = {
        "owner": user_id,
        "bet": amount,
        "players": {user_id: True},
        "pool": amount,
        "active": True
    }

    await event.reply(
        f"🎲 Lottery #{lot_id} started with ${amount:,}!\n"
        f"Join by clicking the button.\n"
        f"Winner gets all the money!",
        buttons=[
            [Button.inline("🎟 Join", f"lot_join_{lot_id}")],
            [Button.inline("▶️ Start", f"lot_start_{lot_id}")]
        ]
    )


# ========= JOIN =========
@client.on(events.CallbackQuery(pattern=b"lot_join_(\\d+)"))
async def lot_join(event):
    chat_id = event.chat_id
    user_id = event.sender_id
    lot_id = int(event.pattern_match.group(1))

    lot = lotteries.get(chat_id, {}).get(lot_id)

    if not lot or not lot["active"]:
        return await event.answer("Lottery not found", alert=True)

    if user_id in lot["players"]:
        return await event.answer("Already joined", alert=True)

    user = get_user(user_id)

    if user[1] < lot["bet"]:
        return await event.answer("Not enough money", alert=True)

    # 💰 payer
    cursor.execute("UPDATE users SET cash=cash-? WHERE user_id=?", (lot["bet"], user_id))
    conn.commit()

    lot["players"][user_id] = True
    lot["pool"] += lot["bet"]

    sender = await event.get_sender()
    name = sender.username or sender.first_name

    await event.answer("Joined!")

    await event.respond(
        f"@{name} joined Lottery #{lot_id}\nParticipants: {len(lot['players'])}\n"
        f"Type /leftlot to leave."
    )


# ========= START =========
@client.on(events.CallbackQuery(pattern=b"lot_start_(\\d+)"))
async def lot_start(event):
    chat_id = event.chat_id
    user_id = event.sender_id
    lot_id = int(event.pattern_match.group(1))

    lot = lotteries.get(chat_id, {}).get(lot_id)

    if not lot or not lot["active"]:
        return await event.answer("Lottery not found", alert=True)

    if lot["owner"] != user_id:
        return await event.answer("Only owner can start", alert=True)

    if len(lot["players"]) < 2:
        return await event.answer("Need at least 2 players", alert=True)

    # 🔥 RANDOM FIX
    players_list = list(lot["players"].keys())
    random.shuffle(players_list)
    winner_id = random.choice(players_list)

    prize = lot["pool"]

    cursor.execute("UPDATE users SET cash=cash+? WHERE user_id=?", (prize, winner_id))
    conn.commit()

    winner = await client.get_entity(winner_id)
    name = winner.username or winner.first_name

    await event.edit(
        f"🎲 Lottery #{lot_id}\n"
        f"🏆 Winner: @{name}\n"
        f"💰 Won ${prize:,}!"
    )

    del lotteries[chat_id][lot_id]


# ========= LEFT =========
@client.on(events.NewMessage(pattern=r"^/leftlot(?:@.+)?$"))
async def leftlot(event):
    chat_id = event.chat_id
    user_id = event.sender_id

    if chat_id not in lotteries:
        return await event.reply("No active lottery.")

    removed = False

    for lot_id, lot in list(lotteries[chat_id].items()):

        if user_id not in lot["players"]:
            continue

        # 🔥 OWNER QUIT → CANCEL
        if user_id == lot["owner"]:
            for uid in lot["players"]:
                cursor.execute(
                    "UPDATE users SET cash=cash+? WHERE user_id=?",
                    (lot["bet"], uid)
                )

            conn.commit()

            await event.reply(
                f"❌ Lottery #{lot_id} cancelled.\nEveryone got refunded."
            )

            del lotteries[chat_id][lot_id]
            removed = True
            continue

        # 🔹 joueur normal quitte
        cursor.execute(
            "UPDATE users SET cash=cash+? WHERE user_id=?",
            (lot["bet"], user_id)
        )

        conn.commit()

        del lot["players"][user_id]
        lot["pool"] -= lot["bet"]

        await event.reply(
            f"You left Lottery #{lot_id} and got refunded."
        )

        removed = True

    if not removed:
        return await event.reply("You're not in any lottery here.")

# ========= DAILY =========
gems = ["⚫️Onyx", "💎Diamond", "💠 Turquoise", "🌊 Aquamarine", "🌙Moonstone"]

@client.on(events.NewMessage(pattern="/daily"))
async def daily(event):
    user = get_user(event.sender_id)
    now = int(time.time())

    # Vérifie si le joueur a déjà pris son daily
    if now - user[7] < 86400:
        return await event.reply("Already checked daily!")

    # Génère argent et gem aléatoire
    money = random.randint(0, 20000)
    gem = random.choice(gems)

    # Met à jour la base de données
    cursor.execute("UPDATE users SET cash=cash+?, gem=?, last_daily=? WHERE user_id=?",
                   (money, gem, now, user[0]))
    conn.commit()

    # Envoie le message au joueur
    await event.reply(f"Collected ${money} from today's daily!\nYou got {gem} !")

#===========FUSE==============
@client.on(events.NewMessage(pattern="/fuse"))
async def fuse(event):
    if not event.is_reply:
        return await event.reply("Reply to someone to fuse gems")

    u1 = get_user(event.sender_id)
    msg = await event.get_reply_message()
    u2 = get_user(msg.sender_id)

    if u1[6] == "none" or u2[6] == "none":
        return await event.reply("One of you doesn't have a gem")

    if u1[6] != u2[6]:
        return await event.reply("You both need the same gem")

    cursor.execute("UPDATE users SET cash=cash+100000, gem='none' WHERE user_id=?", (u1[0],))
    cursor.execute("UPDATE users SET cash=cash+100000, gem='none' WHERE user_id=?", (u2[0],))
    conn.commit()

    name1 = (await event.get_sender()).first_name
    name2 = (await msg.get_sender()).first_name

    await event.reply(f"{name1} and {name2} fused 💎gems  (+100000$ each!)")

#============== KISS,HUG...ETC ============
ACTIONS = {
    "kiss": "kiss",
    "hug": "hug",
    "slap": "slap",
    "punch": "punch",
    "kick": "kick",
    "smile": "smile",
    "cry": "cry",
    "airkiss": "airkiss"
}

# charger les gifs
action_gifs = {}
for action, folder in ACTIONS.items():
    if os.path.exists(folder):
        action_gifs[action] = [os.path.join(folder, f) for f in os.listdir(folder)]
    else:
        action_gifs[action] = []


@client.on(events.NewMessage(pattern=r"^[,./](kiss|hug|slap|punch|kick|smile|cry|airkiss)$"))
async def actions_handler(event):

    action = event.pattern_match.group(1)

    sender = await event.get_sender()

    # 🚫 bloquer bots
    if getattr(sender, "bot", False):
        return

    # 📂 récupérer gif
    gifs = action_gifs.get(action, [])
    if not gifs:
        return await event.reply(f"No GIF found for {action}.")

    gif = random.choice(gifs)

    # 🔹 CAS SANS REPLY autorisé
    if action in ["smile", "cry", "airkiss"]:
        name = sender.first_name
        return await event.reply(
            f"{name} {action}s",
            file=gif
        )

    # 🔹 AUTRES → reply obligatoire
    if not event.is_reply:
        return  # ne rien faire

    reply_msg = await event.get_reply_message()
    target = await reply_msg.get_sender()

    # 🚫 bloquer bots
    if getattr(target, "bot", False):
        return await event.reply("You can't use this on bots.")

    # 🚫 empêcher soi-même
    if target.id == sender.id:
        return await event.reply("You can't use this on yourself.")

    sender_name = sender.first_name
    target_name = target.first_name

    # 💬 message stylé
    texts = {
        "kiss": f"{sender_name} kisses {target_name}",
        "hug": f"{sender_name} hugs {target_name}",
        "slap": f"{sender_name} slaps {target_name}",
        "punch": f"{sender_name} punches {target_name}",
        "kick": f"{sender_name} kicks {target_name}",
    }

    text = texts.get(action, f"{sender_name} {action}s {target_name}")

    await event.reply(text, file=gif)

#==========DONATEDBLOOD=============
@client.on(events.NewMessage(pattern="/donatedblood"))
async def donate_blood(event):
    if not event.is_reply:
        return await event.reply("Reply to someone to donate blood")

    donor = get_user(event.sender_id)
    now = int(time.time())

    if now - donor[11] < 86400:
        return await event.reply("You can donate blood once every 24h")

    if donor[3] <= 0:
        return await event.reply("You're dead, you can't donate blood")

    target_msg = await event.get_reply_message()
    target_entity = await target_msg.get_sender()

    # 🚫 bloquer bots
    if target_entity.bot:
        return await event.reply("You can't donate blood to bots.")

    # 🚫 empêcher de se donner à soi-même
    if target_entity.id == event.sender_id:
        return await event.reply("You can't donate blood to yourself.")

    target = get_user(target_entity.id)

    if target[3] >= 3:
        return await event.reply("Target already has full health")

    cursor.execute(
        "UPDATE users SET health=health-1, last_blood=? WHERE user_id=?",
        (now, donor[0])
    )
    cursor.execute(
        "UPDATE users SET health=health+1 WHERE user_id=?",
        (target[0],)
    )
    conn.commit()

    donor_name = (await event.get_sender()).first_name
    target_name = target_entity.first_name

    await event.reply(f"{donor_name} donated ❤️ to {target_name}!")

# ========= MEDICAL =========
@client.on(events.NewMessage(pattern="/medical"))
async def medical(event):
    user=get_user(event.sender_id)

    if user[1]<500:
        return await event.reply("Not enough money")

    if user[3]>=3:
        return await event.reply("Full health")

    cursor.execute("UPDATE users SET cash=cash-500, health=health+1 WHERE user_id=?",(user[0],))
    conn.commit()

    await event.reply("you Paid $500 for medical !")

#===========J'ESSAIE VOIR ==============
@client.on(events.NewMessage)
async def track_groups(event):
    if event.is_group or event.is_channel:
        groups.add(event.chat_id)

#======== RIPPLE =============================
@client.on(events.NewMessage(pattern=r"/ripple(?: (\d+))?"))
async def ripple(event):
    user_id = event.sender_id
    arg = event.pattern_match.group(1)

    if not arg:
        return await event.reply(
            "Please specify amount to bet in ripple! Example: /ripple 500, can only be from $10 to $100,000."
        )

    amount = int(arg)

    if amount < 10 or amount > 100000:
        return await event.reply("Bet must be between $10 and $100000.")

    user = get_user(user_id)

    if user[1] < amount:
        return await event.reply("Not enough money.")

    ripple_games[user_id] = {
        "bet": amount,
        "current": amount,
        "rows": [],  # historique des lignes
        "active": False
    }

    await event.reply(
        "Play ripple!\n\n"
        "Explore 🌿, Find 🌻 & gain money while avoiding 🐍.\n"
        "There's a single 🐍 on each step.\n"
        "Use /rbet if you run into flood limits!",
        buttons=[[Button.inline(f"Play with ${amount}", f"ripple_start_{user_id}".encode())]]
    )
@client.on(events.CallbackQuery(pattern=b"ripple_start_"))
async def ripple_start(event):
    user_id = int(event.data.decode().split("_")[2])

    if event.sender_id != user_id:
        return await event.answer("Not your game", alert=True)

    game = ripple_games.get(user_id)
    if not game:
        return

    user = get_user(user_id)

    if user[1] < game["bet"]:
        return await event.answer("Not enough money", alert=True)

    cursor.execute("UPDATE users SET cash=cash-? WHERE user_id=?", (game["bet"], user_id))
    conn.commit()

    game["active"] = True
    game["current"] = game["bet"]
    game["rows"] = []

    await send_new_row(event, user_id)
async def send_new_row(event, user_id):
    game = ripple_games[user_id]

    # nouvelle ligne avec feuilles
    row = ["🌿", "🌿", "🌿"]
    game["rows"].insert(0, row)

    await update_ripple_message(event, user_id)
async def update_ripple_message(event, user_id):
    game = ripple_games[user_id]

    gain = game["current"] + (game["bet"] // 2)

    buttons = []

    for row_index, row in enumerate(game["rows"]):
        btn_row = []
        for i, val in enumerate(row):
            # seule la ligne du haut est cliquable
            if row_index == 0 and game["active"]:
                btn_row.append(Button.inline(val, f"ripple_pick_{user_id}_{i}".encode()))
            else:
                btn_row.append(Button.inline(val, b"locked"))
        buttons.append(btn_row)

    # bouton CLAIM
    if game["active"]:
        buttons.append([Button.inline(f"Take ${game['current']}", f"ripple_claim_{user_id}".encode())])

    await event.edit(
        f"Find 🌻 & increase prize to ${gain}",
        buttons=buttons
    )
@client.on(events.CallbackQuery(pattern=b"ripple_pick_"))
async def ripple_pick(event):
    data = event.data.decode().split("_")
    user_id = int(data[2])
    choice = int(data[3])

    if event.sender_id != user_id:
        return await event.answer("Not your game", alert=True)

    game = ripple_games.get(user_id)
    if not game or not game["active"]:
        return

    snake = random.randint(0, 2)

    # 💥 LOSE
    if choice == snake:
        game["rows"][0][choice] = "🐍"
        lost = game["current"]
        game["active"] = False

        buttons = []
        for row in game["rows"]:
            buttons.append([Button.inline(x, b"locked") for x in row])

        buttons.append([Button.inline("Click to restart", f"ripple_restart_{user_id}".encode())])

        await event.edit(f"You lost ${lost}", buttons=buttons)

    # 🎯 WIN
    else:
        game["rows"][0][choice] = "🌻"
        game["current"] += game["bet"] // 2

        await send_new_row(event, user_id)
@client.on(events.CallbackQuery(pattern=b"ripple_claim_"))
async def ripple_claim(event):
    user_id = int(event.data.decode().split("_")[2])

    if event.sender_id != user_id:
        return await event.answer("Not your game", alert=True)

    game = ripple_games.get(user_id)
    if not game:
        return

    amount = game["current"]

    cursor.execute("UPDATE users SET cash=cash+? WHERE user_id=?", (amount, user_id))
    conn.commit()

    game["active"] = False

    await event.edit(
        f"You claimed ${amount}",
        buttons=[[Button.inline("Click to restart", f"ripple_restart_{user_id}".encode())]]
    )
@client.on(events.CallbackQuery(pattern=b"ripple_restart_"))
async def ripple_restart(event):
    user_id = int(event.data.decode().split("_")[2])

    if event.sender_id != user_id:
        return await event.answer("Not your game", alert=True)

    game = ripple_games.get(user_id)
    if not game:
        return

    user = get_user(user_id)

    if user[1] < game["bet"]:
        return await event.answer("Not enough money", alert=True)

    cursor.execute("UPDATE users SET cash=cash-? WHERE user_id=?", (game["bet"], user_id))
    conn.commit()

    game["current"] = game["bet"]
    game["active"] = True
    game["rows"] = []

    await send_new_row(event, user_id)


# ========= TOP USER =========
def get_top_rich():
    cursor.execute("""
        SELECT user_id, cash+bank 
        FROM users 
        ORDER BY (cash+bank) DESC 
        LIMIT 10
    """)
    return cursor.fetchall()


def get_top_rep():
    cursor.execute("""
        SELECT user_id, reputation 
        FROM users 
        ORDER BY reputation DESC 
        LIMIT 10
    """)
    return cursor.fetchall()


async def build_top_text(data, mode):
    text = ""
    rank = 0

    for uid, value in data:
        try:
            user = await client.get_entity(uid)

            # ❌ skip bots
            if getattr(user, "bot", False):
                continue

            # ❌ skip channels & groups
            if getattr(user, "broadcast", False):
                continue
            if getattr(user, "megagroup", False):
                continue

            rank += 1

            name = user.first_name
            mention = f"[{name}](tg://user?id={uid})"

        except:
            continue

        if mode == "money":
            text += f"{rank}. {mention} - ${value:,}\n"
        else:
            text += f"{rank}. {mention} - {value/10} ⭐️\n"

    return text


# ========= TOP USER =========
@client.on(events.NewMessage(pattern="/topuser"))
async def topuser(event):

    data = await build_top_text(get_top_rich(), "money")

    await event.reply(
        f"🏆 Top 10 Richest Players:\n\n{data}",
        buttons=[[Button.inline("⭐ Reputation", b"top_rep")]],
        link_preview=False
    )


# ========= TOP REP CALLBACK =========
@client.on(events.CallbackQuery(data=b"top_rep"))
async def top_rep(event):

    data = await build_top_text(get_top_rep(), "rep")

    await event.edit(
        f"⭐ Top 10 Reputation Players:\n\n{data}",
        buttons=[[Button.inline("🤑 Money", b"top_money")]],
        link_preview=False
    )


# ========= TOP MONEY CALLBACK =========
@client.on(events.CallbackQuery(data=b"top_money"))
async def top_money(event):

    data = await build_top_text(get_top_rich(), "money")

    await event.edit(
        f"🏆 Top 10 Richest Players:\n\n{data}",
        buttons=[[Button.inline("⭐ Reputation", b"top_rep")]],
        link_preview=False
    )


#========== PAY ==============
@client.on(events.NewMessage(pattern=r"^/pay (.+)$"))
async def pay(event):
    if not event.is_reply:
        return

    sender = get_user(event.sender_id)
    now = int(time.time())

    if now - sender[14] < 20:
        return await event.reply("Wait before paying again")

    try:
        amount = parse_amount(event.pattern_match.group(1))
    except:
        return await event.reply("Invalid amount")

    if amount <= 0:
        return await event.reply("Amount must be greater than 0")

    target_msg = await event.get_reply_message()
    target_entity = await target_msg.get_sender()

    if getattr(target_entity, "bot", False):
        return await event.reply("You cannot pay bots.")

    target = get_user(target_entity.id)

    if sender[1] < amount:
        return await event.reply("Not enough money")

    cursor.execute(
        "UPDATE users SET cash=cash-?, last_pay=? WHERE user_id=?",
        (amount, now, sender[0])
    )
    cursor.execute(
        "UPDATE users SET cash=cash+? WHERE user_id=?",
        (amount, target[0])
    )
    conn.commit()

    sender_entity = await event.get_sender()

    await event.reply(
        f"{sender_entity.first_name} paid ${amount} to {target_entity.first_name}!"
    )


#============ DEPOSIT =============
@client.on(events.NewMessage(pattern=r"^/deposit (.+)$"))
async def deposit(event):
    user = get_user(event.sender_id)

    try:
        amount = parse_amount(event.pattern_match.group(1))
    except:
        return await event.reply("Invalid amount")

    if amount <= 0:
        return await event.reply("Amount must be greater than 0")

    if user[1] < amount:
        return await event.reply("Not enough cash")

    cursor.execute(
        "UPDATE users SET cash=cash-?, bank=bank+? WHERE user_id=?",
        (amount, amount, user[0])
    )
    conn.commit()

    name = (await event.get_sender()).first_name
    await event.reply(f"{name} deposited ${amount}")


#========= WITHDRAW ========================
@client.on(events.NewMessage(pattern=r"^/withdraw (.+)$"))
async def withdraw(event):
    user = get_user(event.sender_id)

    try:
        amount = parse_amount(event.pattern_match.group(1))
    except:
        return await event.reply("Invalid amount")

    if amount <= 0:
        return await event.reply("Amount must be greater than 0")

    if user[2] < amount:
        return await event.reply("Not enough bank balance")

    cursor.execute(
        "UPDATE users SET cash=cash+?, bank=bank-? WHERE user_id=?",
        (amount, amount, user[0])
    )
    conn.commit()

    name = (await event.get_sender()).first_name
    await event.reply(f"{name} withdrew ${amount}")
#=========== RBET ============
@client.on(events.NewMessage(pattern=r"/rbet(?: (\d+))?"))
async def rbet(event):
    user_id = event.sender_id
    arg = event.pattern_match.group(1)

    user = get_user(user_id)

    if user_id not in rbet_players:
        rbet_players[user_id] = {"prize": 0, "active": False, "base": 0}

    player = rbet_players[user_id]

    # 🔹 START BET
    if arg:
        amount = int(arg)

        if amount <= 0:
            return await event.reply("Invalid bet amount.")

        if amount > 100000:
            return await event.reply("You cannot bet more than $100000.")

        if user[1] < amount:
            return await event.reply("Not enough money.")

        # 💰 retirer argent
        cursor.execute("UPDATE users SET cash=cash-? WHERE user_id=?", (amount, user_id))
        conn.commit()

        player["base"] = amount
        player["prize"] = amount
        player["active"] = True

        potential = amount + (amount // 2)

        return await event.reply(
            f"Rbet started. Use /rbet to increase prize to ${potential}"
        )

    # 🔹 CONTINUE
    else:
        if not player["active"]:
            return await event.reply("Start a bet first using /rbet <amount>.")

        # 🎯 CHANCE DYNAMIQUE
        chance = win_chance(player["base"])

        # 💥 PERTE
        if random.random() > chance:
            base = player["base"]

            player["active"] = False
            player["prize"] = 0
            player["base"] = 0

            return await event.reply(
                f"You lost your bet of ${base}. Use /rbet <amount> to start again."
            )

        # 🎯 GAIN
        else:
            increase = player["base"] // 2
            player["prize"] += increase

            potential = player["prize"] + (player["base"] // 2)

            return await event.reply(
                f"Hurray!, Prize: ${player['prize']}\n"
                f"/rbet => Make prize ${potential}\n"
                f"/rtake => Take prize."
            )

@client.on(events.NewMessage(pattern="/rtake"))
async def rtake(event):
    user_id = event.sender_id

    if user_id not in rbet_players:
        return await event.reply("No active bet.")

    player = rbet_players[user_id]

    if not player["active"]:
        return await event.reply("No active bet.")

    prize = player["prize"]

    if prize <= 0:
        player["active"] = False
        player["prize"] = 0
        player["base"] = 0
        return await event.reply("No prize to take.")

    # 💰 ajoute TOUT (mise + gain)
    cursor.execute("UPDATE users SET cash=cash+? WHERE user_id=?", (prize, user_id))
    conn.commit()

    # reset
    player["active"] = False
    player["prize"] = 0
    player["base"] = 0

    return await event.reply(
        f"You took prize ${prize} from bet. /rbet for new bet."
    )


#=========== SONAR =============
@client.on(events.NewMessage(pattern=r"/sonar"))
async def sonar(event):
    chat_id = event.chat_id

    sonar_games[chat_id] = {
        "grid": create_grid(),
        "treasures": random_treasures(),
        "found": set(),
        "players": {}
    }

    img = draw_grid(sonar_games[chat_id])

    await event.reply(
        file=img,
        message=(
            "Sonar game started! Grid is 10x10.\n"
            "There are 5 hidden treasures.\n"
            "Use /put [coords] (e.g., /put c7)\n"
            "(-3,000$ each try)"
        )
    )
@client.on(events.NewMessage(pattern=r"^/(put|p)(?:\s+([a-j](?:10|[1-9])))?$"))
async def put(event):
    chat_id = event.chat_id
    user_id = event.sender_id

    game = sonar_games.get(chat_id)
    if not game:
        return await event.reply("Start game with /sonar")

    coord = event.pattern_match.group(2)

    if not coord:
        return await event.reply("Use /put [coords] like /put a1")

    coord = coord.lower()

    user = get_user(user_id)

    if user[1] < 3000:
        return await event.reply("Not enough money.")

    if game["grid"][coord] is not None:
        return await event.reply("This location was already searched.")

    # payer
    cursor.execute("UPDATE users SET cash=cash-3000 WHERE user_id=?", (user_id,))
    conn.commit()

    game["players"].setdefault(user_id, 0)

    # 🎯 SI TRÉSOR
    if coord in game["treasures"]:
        game["grid"][coord] = "X"
        game["found"].add(coord)
        game["players"][user_id] += 20

        cursor.execute("UPDATE users SET cash=cash+25000 WHERE user_id=?", (user_id,))
        conn.commit()

        text = f"*** BOOM! ***\nYou found a treasure at {coord.upper()}!\n+25,000$ Added!\n"

    else:
        # distance dynamique
        remaining = [t for t in game["treasures"] if t not in game["found"]]
        dists = [distance(coord, t) for t in remaining]
        game["grid"][coord] = min(dists)

        text = (
            f"Sonar deployed at {coord.upper()}. Distance indicator: {game['grid'][coord]}\n"
            "/put [coords] to place another.\n(-3,000$ deducted)\n"
        )

    # 🔥 UPDATE GLOBAL DES DISTANCES
    update_distances(game)

    remaining = 5 - len(game["found"])

    # 🎉 FIN
    if remaining == 0:
        # révélation S
        for c in game["grid"]:
            if game["grid"][c] is None:
                game["grid"][c] = "S"

        winner = max(game["players"], key=game["players"].get)

        cursor.execute("UPDATE users SET reputation=reputation+2 WHERE user_id=?", (winner,))
        conn.commit()

        img = draw_grid(game)

        await event.reply(
            file=img,
            message=(
                text +
                "\n**Congratulations! You have found all 5 treasure chests!**"
            )
        )

        del sonar_games[chat_id]
        return

    img = draw_grid(game)

    await event.reply(
        file=img,
        message=text + f"\n{remaining} treasures remaining."
    )


#=============== NATION ===============
@client.on(events.NewMessage(pattern=r"/nation(?: (.+))?"))
async def nation(event):
    user = get_user(event.sender_id)
    now = int(time.time())

    # ⏱️ cooldown 10s
    if now - user[15] < 10:
        remaining = 10 - (now - user[15])
        return await event.reply(f"Wait {remaining}s before using /nation again.")

    # update cooldown
    cursor.execute("UPDATE users SET last_nation=? WHERE user_id=?", (now, user[0]))
    conn.commit()

    files = os.listdir("dataset")

    if len(files) < 3:
        return await event.reply("Not enough data.")

    # image aléatoire
    correct_file = random.choice(files)
    correct_country = correct_file.split(".")[0]

    # mauvaises réponses
    others = [f.split(".")[0] for f in files if f != correct_file]
    wrong = random.sample(others, 2)

    choices = [correct_country] + wrong
    random.shuffle(choices)

    buttons = [[Button.inline(c, c.encode())] for c in choices]

    msg = await event.reply(
    "Guess the nation. [?]",
    file=os.path.join("dataset", correct_file),
    buttons=buttons
)

    nation_games[msg.id] = {
    "answer": correct_country,
    "winner": None   # 🔥 ajouté ici
}

# ========= NATION ANSWER =========
@client.on(events.CallbackQuery)
async def nation_answer(event):

    # 🔥 récupère le message lié au bouton (SAFE)
    msg = await event.get_message()

    if not msg:
        return await event.answer("Message expired", alert=True)

    msg_id = msg.id
    user_id = event.sender_id

    game = nation_games.get(msg_id)
    if not game:
        return await event.answer("Game expired", alert=True)

    # 🔥 si déjà un gagnant → stop immédiat
    if game.get("winner") is not None:
        return await event.answer("Too late 😢", alert=True)

    choice = event.data.decode()
    correct = game["answer"]

    await event.answer()

    # 🔒 LOCK IMMÉDIAT
    game["winner"] = user_id

    user = get_user(user_id)

    if choice == correct:
        cursor.execute(
            "UPDATE users SET cash=cash+10000, reputation=reputation+1 WHERE user_id=?",
            (user_id,)
        )
        conn.commit()

        try:
            await msg.delete()
        except:
            pass

        await event.respond(
            "Correct! You get +$10000. /nation [continent] for new game."
        )

    else:
        cursor.execute(
            "UPDATE users SET reputation=reputation-1 WHERE user_id=?",
            (user_id,)
        )
        conn.commit()

        try:
            await msg.delete()
        except:
            pass

        await event.respond(
            f"Wrong answer. {correct} was correct."
        )

    nation_games.pop(msg_id, None)
# ========= KILL =========
@client.on(events.NewMessage(pattern="/kill"))
async def kill(event):
    if not event.is_reply:
        return

    attacker_entity = await event.get_sender()

    # 🚫 bloquer bots
    if getattr(attacker_entity, "bot", False):
        return await event.reply("Bots can't use this.")

    a = get_user(event.sender_id)
    attacker_name = attacker_entity.first_name

    now = int(time.time())

    if now - a[12] < 15:
        remaining = 15 - (now - a[12])
        return await event.reply(f"You can do your next kill after: {format_time(remaining)}")

    v_msg = await event.get_reply_message()
    victim_entity = await v_msg.get_sender()

    # 🚫 bloquer bots
    if getattr(victim_entity, "bot", False):
        return await event.reply("You can't attack bots.")

    v = get_user(victim_entity.id)
    victim_name = victim_entity.first_name

    if a[3] == 0:
        return await event.reply("You're dead, you can't kill.", file=random.choice(failed_gifs))

    if v[3] == 0:
        return await event.reply(f"{victim_name} is already dead!", file=random.choice(failed_gifs))

    reset_limits(a)

    if a[8] >= 5:
        return await event.reply("You already killed 5 people today!", file=random.choice(failed_gifs))

    success = random.choice([True, False])

    cursor.execute("UPDATE users SET last_kill=? WHERE user_id=?", (now, a[0]))

    if success:
        cursor.execute("UPDATE users SET cash=cash+50000,kills_today=kills_today+1 WHERE user_id=?", (a[0],))
        cursor.execute("UPDATE users SET health=health-1 WHERE user_id=?", (v[0],))
        conn.commit()

        gif = random.choice(killed_gifs.get(a[5], []))
        await event.reply(f"{attacker_name} killed {victim_name}! (+50000$)", file=gif)

    else:
        conn.commit()
        await event.reply(f"{attacker_name} failed to kill {victim_name}!", file=random.choice(failed_gifs))

#===============RAINING================
async def rain_loop():
    while True:
        await asyncio.sleep(RAIN_INTERVAL)

        for chat_id in groups:

            msg = await client.send_message(
                chat_id,
                "It's raining money! 🤑 press button to collect!",
                buttons=[[Button.inline("Collect 💰", b"collect_money")]]
            )

            rains[chat_id] = {
                "active": True,
                "collectors": [],
                "message": msg
            }

            client.loop.create_task(stop_rain(chat_id))

async def stop_rain(chat_id):
    await asyncio.sleep(RAIN_DURATION)

    if chat_id not in rains:
        return

    rain = rains[chat_id]

    if not rain["active"]:
        return

    rain["active"] = False

    if len(rain["collectors"]) == 0:
        text = "Raining has stopped!"
    else:
        text = "Raining has stopped!\n\n"
        for c in rain["collectors"]:
            text += f"{c[1]} collected ${c[2]}!\n"

    await rain["message"].edit(text)

@client.on(events.CallbackQuery(data=b"collect_money"))
async def collect_money(event):
    chat_id = event.chat_id

    if chat_id not in rains:
        return await event.answer("No rain here")

    rain = rains[chat_id]

    if not rain["active"]:
        return await event.answer("Too late")

    user_id = event.sender_id

    if user_id in [c[0] for c in rain["collectors"]]:
        return await event.answer("You already collected")

    if len(rain["collectors"]) >= 3:
        return await event.answer("Too late")

    # 💰 montants
    if len(rain["collectors"]) == 0:
        amount = random.randint(3000, 5000)
    elif len(rain["collectors"]) == 1:
        amount = random.randint(2000, 2900)
    else:
        amount = random.randint(1000, 1900)

    user = get_user(user_id)
    cursor.execute("UPDATE users SET cash=cash+? WHERE user_id=?", (amount, user[0]))
    conn.commit()

    sender = await event.get_sender()
    name = sender.first_name

    rain["collectors"].append((user_id, name, amount))

    # update message
    text = "It's raining money! 🤑 press button to collect!\n\n"
    for c in rain["collectors"]:
        text += f"{c[1]} collected ${c[2]}!\n"

    # fin si 3 joueurs
    if len(rain["collectors"]) == 3:
        rain["active"] = False

        final = "Raining has stopped!\n\n"
        for c in rain["collectors"]:
            final += f"{c[1]} collected ${c[2]}!\n"

        await rain["message"].edit(final)

    else:
        await rain["message"].edit(
            text,
            buttons=[[Button.inline("Collect 💰", b"collect_money")]]
        )

# ========= ROB =========
@client.on(events.NewMessage(pattern="/rob"))
async def rob(event):
    if not event.is_reply:
        return

    attacker_entity = await event.get_sender()

    # 🚫 bloquer bots
    if getattr(attacker_entity, "bot", False):
        return await event.reply("Bots can't rob.")

    a = get_user(event.sender_id)
    attacker_name = attacker_entity.first_name

    now = int(time.time())

    if now - a[13] < 15:
        remaining = 15 - (now - a[13])
        return await event.reply(f"You can do your next robbery after: {format_time(remaining)}")

    v_msg = await event.get_reply_message()
    victim_entity = await v_msg.get_sender()

    # 🚫 bloquer bots
    if getattr(victim_entity, "bot", False):
        return await event.reply("You can't rob bots.")

    v = get_user(victim_entity.id)
    victim_name = victim_entity.first_name

    if a[3] == 0:
        return await event.reply("You're dead, you can't steal.", file=random.choice(failed_gifs))

    if v[1] <= 0:
        return await event.reply(f"{victim_name} is too poor to be robbed.", file=random.choice(failed_gifs))

    reset_limits(a)

    if a[9] >= 5:
        return await event.reply("You already robbed 5 people today!", file=random.choice(failed_gifs))

    amount = min(v[1], random.randint(1, 50000))
    success = random.choice([True, False])

    cursor.execute("UPDATE users SET last_rob=? WHERE user_id=?", (now, a[0]))

    if success:
        cursor.execute("UPDATE users SET cash=cash+? WHERE user_id=?", (amount, a[0]))
        cursor.execute("UPDATE users SET cash=cash-? WHERE user_id=?", (amount, v[0]))
        conn.commit()

        await event.reply(f"{attacker_name} stole ${amount} from {victim_name}!", file=random.choice(rob_gifs))

    else:
        conn.commit()
        await event.reply(f"{attacker_name} failed to rob {victim_name}!", file=random.choice(failed_gifs))

#=========== FNATION ============
@client.on(events.NewMessage(pattern=r"/fnation (\d+)"))
async def fnation(event):
    chat_id = event.chat_id
    user_id = event.sender_id
    amount = int(event.pattern_match.group(1))

    if amount > 10_000_000:
        return await event.reply("Max bet is $10,000,000.")

    if chat_id in fnation_fights and fnation_fights[chat_id]["active"]:
        return await event.reply("A fight is already active here.")

    user = get_user(user_id)

    if user[1] < amount:
        return await event.reply("Not enough money.")

    cursor.execute("UPDATE users SET cash=cash-? WHERE user_id=?", (amount, user_id))
    conn.commit()

    fnation_fights[chat_id] = {
        "active": True,
        "owner": user_id,
        "bet": amount,
        "rounds": 0,
        "current_round": 0,
        "players": {user_id: {"score": 0}},
        "total_pool": amount,
        "started": False,
        "message": None,
        "answer": None
    }

    await event.reply(
        f"🔥 Fight created!\n"
        f"💰 Bet: ${amount}\n"
        f"Use /drop <max 20> to set rounds\n"
        f"Use /joinfight to join"
    )
@client.on(events.NewMessage(pattern=r"/drop(?:@\w+)? (\d+)"))
async def drop(event):
    chat_id = event.chat_id
    user_id = event.sender_id

    fight = fnation_fights.get(chat_id)
    if not fight or not fight["active"]:
        return await event.reply("No active fight here.")

    if fight["owner"] != user_id:
        return await event.reply("Only owner can set rounds.")

    rounds = int(event.pattern_match.group(1))

    if rounds > 20:
        return await event.reply("Max 20 rounds.")

    fight["rounds"] = rounds

    await event.reply(
        f"⚔️ Fight ready!\n"
        f"Rounds: {rounds}\n"
        f"Use /joinfight\n"
        f"Owner: /startfight"
    )
@client.on(events.NewMessage(pattern="/joinfight"))
async def joinfight(event):
    chat_id = event.chat_id
    user_id = event.sender_id

    fight = fnation_fights.get(chat_id)

    if not fight or not fight["active"]:
        return await event.reply("No active fight.")

    if fight["started"]:
        return await event.reply("Fight already started.")

    if user_id in fight["players"]:
        return await event.reply("Already joined.")

    user = get_user(user_id)

    if user[1] < fight["bet"]:
        return await event.reply("Not enough money.")

    cursor.execute("UPDATE users SET cash=cash-? WHERE user_id=?", (fight["bet"], user_id))
    conn.commit()

    fight["players"][user_id] = {"score": 0}
    fight["total_pool"] += fight["bet"]

    sender = await event.get_sender()
    name = sender.username or sender.first_name

    await event.reply(f"@{name} joined the fight! 💥")

@client.on(events.NewMessage(pattern="/killfight"))
async def killfight(event):
    chat_id = event.chat_id
    user_id = event.sender_id

    fight = fnation_fights.get(chat_id)

    if not fight:
        return await event.reply("No active fight.")

    if fight["owner"] != user_id:
        return await event.reply("Only owner can stop the fight.")

    # 💰 remboursement
    for uid in fight["players"]:
        cursor.execute(
            "UPDATE users SET cash=cash+? WHERE user_id=?",
            (fight["bet"], uid)
        )

    conn.commit()

    await event.reply("Fight cancelled. All players have been refunded.")

    del fnation_fights[chat_id]

@client.on(events.NewMessage(pattern="/startfight"))
async def startfight(event):
    chat_id = event.chat_id
    user_id = event.sender_id

    fight = fnation_fights.get(chat_id)

    if not fight:
        return await event.reply("No fight here.")

    if fight["owner"] != user_id:
        return await event.reply("Only owner can start.")

    if fight["started"]:
        return await event.reply("Already started.")

    if fight["rounds"] <= 0:
        return await event.reply("Set rounds first using /drop.")

    # 🔥 NOUVEAU CHECK
    if len(fight["players"]) < 2:
        return await event.reply("At least 2 players are required to start the fight.")

    fight["started"] = True
    fight["current_round"] = 1

    mentions = []
    for uid in fight["players"]:
        try:
            user = await client.get_entity(uid)
            mentions.append(f"[{user.first_name}](tg://user?id={uid})")
        except:
            mentions.append(str(uid))

    players_text = "\n".join(mentions)

    await event.reply(
        "FIGHT STARTED\n\n"
        f"Players:\n{players_text}\n\n"
        f"Total pool: ${fight['total_pool']}\n"
        f"Rounds: {fight['rounds']}"
    )

    # 🎮 lance la première manche
    await send_round(chat_id)
async def send_round(chat_id):
    fight = fnation_fights.get(chat_id)

    if not fight:
        return

    if fight["current_round"] > fight["rounds"]:
        return await end_fight(chat_id)

    files = os.listdir("dataset")
    correct_file = random.choice(files)
    correct = correct_file.split(".")[0]

    wrong = random.sample([f.split(".")[0] for f in files if f != correct], 2)

    choices = [correct] + wrong
    random.shuffle(choices)

    buttons = [[Button.inline(c, c.encode())] for c in choices]

    text = (
        f"🔥 Manche {fight['current_round']}/{fight['rounds']}\n"
        f"Guess the nation"
    )

    msg = await client.send_file(
        chat_id,
        file=os.path.join("dataset", correct_file),
        caption=text,
        buttons=buttons
    )

    fight["answer"] = correct
    fight["message"] = msg
@client.on(events.CallbackQuery)
async def fnation_answer(event):
    chat_id = event.chat_id
    user_id = event.sender_id
    choice = event.data.decode()

    fight = fnation_fights.get(chat_id)

    if not fight or not fight["started"]:
        return

    if user_id not in fight["players"]:
        return await event.answer("Not in fight", alert=True)

    if choice != fight["answer"]:
        return await event.answer("Wrong ❌")

    await event.answer("Correct! ✅")

    fight["players"][user_id]["score"] += 1

    await fight["message"].delete()

    fight["current_round"] += 1

    await send_round(chat_id)
async def end_fight(chat_id):
    fight = fnation_fights.get(chat_id)

    if not fight:
        return

    winner_id, data = max(
        fight["players"].items(),
        key=lambda x: x[1]["score"]
    )

    prize = fight["total_pool"]

    cursor.execute("UPDATE users SET cash=cash+? WHERE user_id=?", (prize, winner_id))
    conn.commit()

    winner = await client.get_entity(winner_id)
    name = winner.username or winner.first_name

    await client.send_message(
        chat_id,
        f"🏆 WINNER: @{name}\n💰 Won ${prize}"
    )

    del fnation_fights[chat_id]

# ========= RUN =========

client.loop.create_task(rain_loop())

load_groups()

client.run_until_disconnected()
