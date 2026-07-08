import os
import csv
import string
import datetime
import random

import discord
from discord.ext import commands

from core.logger import setup_error_handling
from config import DISCORD_TOKEN, LOG_GUILD_ID, DISCORD_CLIENT_ID
from user_utils import update_known_users
from shared import stats, max_id, words_stats, max_word_id

# ----- Directory setup -----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'db')
os.makedirs(DB_DIR, exist_ok=True)

# ----- English words loader -----
# Load the `american-english` word list from the db directory into a set for O(1) lookups
AMERICAN_ENGLISH_FILE = os.path.join(DB_DIR, 'american-english')
if os.path.exists(AMERICAN_ENGLISH_FILE):
    with open(AMERICAN_ENGLISH_FILE, encoding='utf-8') as f:
        ENGLISH_WORDS = set(line.strip().lower() for line in f if line.strip())
    print(f"Loaded {len(ENGLISH_WORDS)} English words from '{AMERICAN_ENGLISH_FILE}'")
else:
    ENGLISH_WORDS = set()
    print(f"Warning: English word list file '{AMERICAN_ENGLISH_FILE}' not found. ENGLISH_WORDS is empty.")

# ----- Stats CSV setup -----
COUNTER_FILE = os.path.join(DB_DIR, 'counter.csv')
WORDS_FILE = os.path.join(DB_DIR, 'words.csv')

# Initialize or load counter.csv
if not os.path.exists(COUNTER_FILE):
    with open(COUNTER_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["id", "entry_id", "user_id", "guild_id", "messages", "words", "characters"])
else:
    with open(COUNTER_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rid = int(row['id'])
                uid = row["user_id"]
                gid = row["guild_id"]
                stats[(uid, gid)] = {
                    "id": rid,
                    "entry_id": row["entry_id"],
                    "user_id": uid,
                    "guild_id": gid,
                    "messages": int(row["messages"]),
                    "words": int(row["words"]),
                    "characters": int(row["characters"]),
                }
                max_id = max(max_id, rid)
            except (KeyError, ValueError):
                continue

# Initialize or load words.csv
if not os.path.exists(WORDS_FILE):
    with open(WORDS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'word_id', 'guild_id', 'word', 'count', 'is_dict'])
else:
    with open(WORDS_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                wid = int(row['id'])
                gid = row['guild_id']
                word = row['word']
                count = int(row['count'])
                is_dict = row['is_dict'] in ('True', 'true', '1')
                word_id = row['word_id']
                words_stats[(gid, word)] = {
                    'id': wid,
                    'word_id': word_id,
                    'guild_id': gid,
                    'word': word,
                    'count': count,
                    'is_dict': is_dict,
                }
                max_word_id = max(max_word_id, wid)
            except (KeyError, ValueError):
                continue

# Persist stats to CSV
def save_stats():
    with open(COUNTER_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id','entry_id','user_id','guild_id','messages','words','characters'])
        writer.writeheader()
        for rec in stats.values():
            writer.writerow(rec)

# Persist word stats to CSV
def save_words():
    with open(WORDS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id','word_id','guild_id','word','count','is_dict'])
        writer.writeheader()
        for rec in words_stats.values():
            writer.writerow({
                'id': rec['id'],
                'word_id': rec['word_id'],
                'guild_id': rec['guild_id'],
                'word': rec['word'],
                'count': rec['count'],
                'is_dict': rec['is_dict'],
            })

# Generate a unique 8-char word_id
def generate_word_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

# ----- Bot setup -----
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.AutoShardedBot(
    command_prefix="!",
    intents=intents,
    application_id=int(DISCORD_CLIENT_ID)
)

# Clean a token: strip leading punctuation/symbols and lower
def clean_token(token: str) -> str:
    # Remove leading and trailing punctuation/symbols and convert to lowercase
    return token.strip(string.punctuation + '“”‘’').lower()

# ----- Event: track every user message and words -----
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    uid = str(message.author.id)
    gid = str(message.guild.id)
    key = (uid, gid)

    global max_id, max_word_id
    # Update message stats
    if key not in stats:
        max_id += 1
        entry_id = generate_word_id()
        stats[key] = {'id': max_id, 'entry_id': entry_id, 'user_id': uid, 'guild_id': gid, 'messages':0,'words':0,'characters':0}

    rec = stats[key]
    rec["messages"] += 1
    content = message.content or ""
    tokens = content.split()
    rec['words'] += len(tokens)
    rec["characters"] += len(content)

    save_stats()

    # Track each word
    for token in tokens:
        w = clean_token(token)
        if not w:
            continue
        wkey = (gid, w)
        if wkey not in words_stats:
            max_word_id += 1
            wid = max_word_id
            word_id = generate_word_id()
            is_dict = w in ENGLISH_WORDS
            words_stats[wkey] = {
                'id': wid,
                'word_id': word_id,
                'guild_id': gid,
                'word': w,
                'count': 1,
                'is_dict': is_dict,
            }
        else:
            words_stats[wkey]['count'] += 1
    save_words()

    await bot.process_commands(message)

# ----- Session-ID generation & logging -----
SESSION_FILE = "sessions.csv"

def generate_session_id():
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(8))

# Create file + header if it doesn't exist
if not os.path.exists(SESSION_FILE):
    with open(SESSION_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "session_id", "datetime_now"])

# Read existing IDs & find max row-ID
existing = set()
max_id = 0
with open(SESSION_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        existing.add(row["session_id"])
        try:
            row_id = int(row["id"])
            max_id = max(max_id, row_id)
        except ValueError:
            pass

# Pick a fresh session_id
session_id = generate_session_id()
while session_id in existing:
    session_id = generate_session_id()

# Append new row
new_id = max_id + 1
now_iso = datetime.datetime.now().isoformat()
with open(SESSION_FILE, "a", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([new_id, session_id, now_iso])

# ----- Activity updater -----
async def update_activity():
    # set a custom status with an emoji
    await bot.change_presence(
        activity=discord.CustomActivity(name=f"Hello, chat! (Session ID: {session_id})", emoji=":wave:")
    )

# ----- Load extensions, events, etc. -----
async def load_cogs():
    extensions = [
        "bot.commands.general",
        "bot.commands.info",
        "bot.commands.stats",
        "bot.commands.admin",
    ]
    for ext in extensions:
        if ext not in bot.extensions:
            try:
                await bot.load_extension(ext)
                print(f"Loaded extension: {ext}")
            except commands.ExtensionAlreadyLoaded:
                print(f"Extension already loaded, skipping: {ext}")

# Function to fetch and display command IDs
async def fetch_command_ids():
    commands = await bot.tree.fetch_commands()
    print("\n=== Registered Slash Commands ===")
    for cmd in commands:
        print(f"/{cmd.name} - ID: {cmd.id}")
    print("================================\n")

# Event to update known users when the bot is ready
@bot.event
async def on_ready():
    global cogs_loaded
    if not globals().get("cogs_loaded", False):
        await load_cogs()
        globals()["cogs_loaded"] = True
    await bot.tree.sync()
    await bot.tree.sync(guild=discord.Object(id=LOG_GUILD_ID))
    await fetch_command_ids()  # Fetch and display command IDs
    await update_known_users(bot)  # Update known users with all guild members
    await update_activity()  # Update the status on startup
    print(f"Logged in as {bot.user} (ID: {bot.user.id}) "
          f"with {bot.shard_count} shard(s) [Session ID: {session_id}]")

# Update known users and activity when joining a new guild
@bot.event
async def on_guild_join(guild):
    print(f"Joined new guild: {guild.name} (ID: {guild.id})")
    await update_known_users(bot)
    await update_activity()

# Update known users and activity when leaving a guild
@bot.event
async def on_guild_remove(guild):
    print(f"Left guild: {guild.name} (ID: {guild.id})")
    await update_known_users(bot)
    await update_activity()

# ----- Error handling & run bot -----
if __name__ == "__main__":
    setup_error_handling(bot)
    bot.run(DISCORD_TOKEN)
