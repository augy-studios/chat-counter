import os
import string
import datetime
import random

import discord
from discord.ext import commands

import db
from core.logger import setup_error_handling
from config import DISCORD_TOKEN, LOG_GUILD_ID, DISCORD_CLIENT_ID
from user_utils import record_known_user
from shared import stats, words_stats

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

# ----- Stats storage setup (encrypted SQLite) -----
db.init_db()
stats.update(db.load_stats())
words_stats.update(db.load_words())

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

    record_known_user(message.author)

    # Update message stats
    if key not in stats:
        stats[key] = {'id': None, 'entry_id': generate_word_id(), 'user_id': uid, 'guild_id': gid, 'messages': 0, 'words': 0, 'characters': 0}

    rec = stats[key]
    rec["messages"] += 1
    content = message.content or ""
    tokens = content.split()
    rec['words'] += len(tokens)
    rec["characters"] += len(content)

    # Track each word
    changed_words = []
    for token in tokens:
        w = clean_token(token)
        if not w:
            continue
        wkey = (gid, w)
        if wkey not in words_stats:
            words_stats[wkey] = {
                'id': None,
                'word_id': generate_word_id(),
                'guild_id': gid,
                'word': w,
                'count': 0,
                'is_dict': w in ENGLISH_WORDS,
            }
        words_stats[wkey]['count'] += 1
        changed_words.append(words_stats[wkey])

    db.record_message(rec, changed_words)

    await bot.process_commands(message)

# ----- Session-ID generation & logging -----
def generate_session_id():
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(8))

# Pick a fresh session_id
_existing_sessions = db.get_session_ids()
session_id = generate_session_id()
while session_id in _existing_sessions:
    session_id = generate_session_id()

db.add_session(session_id, datetime.datetime.now().isoformat())

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
        "bot.commands.privacy",
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

@bot.event
async def on_ready():
    global cogs_loaded
    if not globals().get("cogs_loaded", False):
        await load_cogs()
        globals()["cogs_loaded"] = True
    await bot.tree.sync()
    await bot.tree.sync(guild=discord.Object(id=LOG_GUILD_ID))
    await fetch_command_ids()  # Fetch and display command IDs
    await update_activity()  # Update the status on startup
    print(f"Logged in as {bot.user} (ID: {bot.user.id}) "
          f"with {bot.shard_count} shard(s) [Session ID: {session_id}]")

# Update activity when joining a new guild
@bot.event
async def on_guild_join(guild):
    print(f"Joined new guild: {guild.name} (ID: {guild.id})")
    await update_activity()

# Update activity when leaving a guild
@bot.event
async def on_guild_remove(guild):
    print(f"Left guild: {guild.name} (ID: {guild.id})")
    await update_activity()

# ----- Error handling & run bot -----
if __name__ == "__main__":
    setup_error_handling(bot)
    bot.run(DISCORD_TOKEN)
