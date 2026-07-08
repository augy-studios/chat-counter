# In-memory cache of per-user message stats, backed by the SQLite database
stats = {}

# In-memory cache of per-guild word usage stats, backed by the SQLite database
# key=(guild_id, word); value: { 'id', 'word_id', 'guild_id', 'word', 'count', 'is_dict' }
words_stats = {}
