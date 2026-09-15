import datetime
from zoneinfo import ZoneInfo
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_OWNER_ID, LOG_GUILD_ID
from core.logger import log_action
from shared import stats, words_stats

# Discord rejects embed field names longer than 256 characters
EMBED_FIELD_NAME_LIMIT = 256

def word_field_name(rank: int, word: str) -> str:
    name = f"{rank}. {word}"
    if len(name) > EMBED_FIELD_NAME_LIMIT:
        name = name[:EMBED_FIELD_NAME_LIMIT - 1] + "…"
    return name

# Pagination view for dump command
class DumpView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=None)
        self.pages = pages
        self.current = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ===== Server Stats Command =====
    @app_commands.command(
        name="serverstats",
        description="Show an at-a-glance summary of server stats"
    )
    async def serverstats(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command must be used in a guild.")
            return

        gid_str = str(guild.id)
        # Total word count in this guild
        total_words = 0
        word_counts: dict[str, int] = {}
        dict_counts: dict[str, int] = {}
        non_dict_counts: dict[str, int] = {}

        for rec in words_stats.values():
            if rec.get('guild_id') != gid_str:
                continue
            word = rec['word']
            count = rec['count']
            total_words += count
            # aggregate overall
            word_counts[word] = word_counts.get(word, 0) + count
            # aggregate by dict flag
            if rec.get('is_dict'):
                dict_counts[word] = dict_counts.get(word, 0) + count
            else:
                non_dict_counts[word] = non_dict_counts.get(word, 0) + count

        # Determine most-used words
        most_used_word = max(word_counts.items(), key=lambda kv: kv[1])[0] if word_counts else None
        most_dict_word = max(dict_counts.items(), key=lambda kv: kv[1])[0] if dict_counts else None
        most_non_dict_word = max(non_dict_counts.items(), key=lambda kv: kv[1])[0] if non_dict_counts else None

        # Most chatty member (by message count)
        chatty_totals: dict[str, int] = {}
        for (uid, gid), rec in stats.items():
            if gid != gid_str:
                continue
            chatty_totals[uid] = chatty_totals.get(uid, 0) + rec.get('messages', 0)
        if chatty_totals:
            top_uid, _ = max(chatty_totals.items(), key=lambda kv: kv[1])
            member = self.bot.get_user(int(top_uid))
            most_chatty = member.name if member else f"Unknown User ({top_uid})"
        else:
            most_chatty = None

        embed = discord.Embed(
            title=f"📊 Server Stats: {guild.name}",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        embed.add_field(name="Total Words", value=str(total_words), inline=False)
        embed.add_field(name="Most Used Word", value=most_used_word or "N/A", inline=False)
        embed.add_field(name="Most Used Dictionary Word", value=most_dict_word or "N/A", inline=False)
        embed.add_field(name="Most Used Non-Dictionary Word", value=most_non_dict_word or "N/A", inline=False)
        embed.add_field(name="Most Chatty Member", value=most_chatty or "N/A", inline=False)

        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    # ===== Leaderboard Commands =====
    lb = app_commands.Group(
        name="lb",
        description="Leaderboard commands"
    )

    @lb.command(
        name="global",
        description="Show the global message leaderboard"
    )
    async def global_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        if not stats:
            await interaction.followup.send("No message data yet.")
            return

        # Aggregate totals per user across all guilds
        user_totals: dict[str, dict[str, int]] = {}
        for (uid, _), rec in stats.items():
            totals = user_totals.setdefault(uid, {"messages": 0, "words": 0, "characters": 0})
            totals["messages"] += rec["messages"]
            totals["words"] += rec["words"]
            totals["characters"] += rec["characters"]

        # Take top 10 by message count
        top = sorted(
            user_totals.items(),
            key=lambda kv: kv[1]["messages"],
            reverse=True
        )[:10]

        embed = discord.Embed(
            title="🏆 Global Message Leaderboard",
            description="Top 10 users by message count",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        for rank, (uid, tot) in enumerate(top, start=1):
            member = self.bot.get_user(int(uid))
            name = member.name if member else f"Unknown User ({uid})"
            embed.add_field(
                name=f"{rank}. {name}",
                value=(
                    f"{tot['messages']} messages | "
                    f"{tot['words']} words | "
                    f"{tot['characters']} characters"
                ),
                inline=False
            )

        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    @lb.command(
        name="guild",
        description="Show the guild-specific leaderboard"
    )
    @app_commands.describe(
        guild_id="Guild ID to view, defaults to current guild"
    )
    async def guild_leaderboard(
        self,
        interaction: discord.Interaction,
        guild_id: Optional[int] = None
    ):
        await interaction.response.defer(thinking=True)

        gid_str = str(guild_id) if guild_id else str(interaction.guild_id)
        # Filter stats for this guild
        user_totals: dict[str, dict[str, int]] = {}
        for (uid, gid), rec in stats.items():
            if gid != gid_str:
                continue
            totals = user_totals.setdefault(uid, {"messages": 0, "words": 0, "characters": 0})
            totals["messages"] += rec["messages"]
            totals["words"] += rec["words"]
            totals["characters"] += rec["characters"]

        if not user_totals:
            await interaction.followup.send("No message data for this guild.")
            return

        top = sorted(
            user_totals.items(),
            key=lambda kv: kv[1]["messages"],
            reverse=True
        )[:10]

        # Determine guild name if possible
        guild_obj = self.bot.get_guild(int(gid_str)) if gid_str.isdigit() else None
        guild_name = guild_obj.name if guild_obj else gid_str

        embed = discord.Embed(
            title=f"🏆 Guild Leaderboard: {guild_name}",
            description="Top 10 users by message count in this guild",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        for rank, (uid, tot) in enumerate(top, start=1):
            member = self.bot.get_user(int(uid))
            name = member.name if member else f"Unknown User ({uid})"
            embed.add_field(
                name=f"{rank}. {name}",
                value=(
                    f"{tot['messages']} messages | "
                    f"{tot['words']} words | "
                    f"{tot['characters']} characters"
                ),
                inline=False
            )

        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    # ===== Top Words Commands =====
    topwords = app_commands.Group(
        name="topwords",
        description="Word usage commands"
    )

    @topwords.command(
        name="overall",
        description="Show the top 10 most used words across all guilds"
    )
    async def topwords_overall(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        if not words_stats:
            await interaction.followup.send("No word data yet.")
            return

        # Aggregate counts per word across all guilds
        totals: dict[str, int] = {}
        for rec in words_stats.values():
            word = rec['word']
            count = rec['count']
            totals[word] = totals.get(word, 0) + count

        top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]

        embed = discord.Embed(
            title="🔤 Top 10 Words Overall",
            description="Most frequently used words across all guilds",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        for rank, (word, count) in enumerate(top, start=1):
            embed.add_field(name=word_field_name(rank, word), value=f"{count} uses", inline=False)

        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    @topwords.command(
        name="guild",
        description="Show the top 10 most used words in a guild"
    )
    @app_commands.describe(
        guild_id="Guild ID to view, defaults to current guild"
    )
    async def topwords_guild(
        self,
        interaction: discord.Interaction,
        guild_id: Optional[int] = None
    ):
        await interaction.response.defer(thinking=True)

        gid_str = str(guild_id) if guild_id else str(interaction.guild_id)

        totals: dict[str, int] = {}
        for (gid, _), rec in words_stats.items():
            if gid != gid_str:
                continue
            word = rec['word']
            count = rec['count']
            totals[word] = totals.get(word, 0) + count

        if not totals:
            await interaction.followup.send("No word data for this guild.")
            return

        top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]

        guild_obj = self.bot.get_guild(int(gid_str)) if gid_str.isdigit() else None
        guild_name = guild_obj.name if guild_obj else gid_str

        embed = discord.Embed(
            title=f"🔤 Top 10 Words in Guild: {guild_name}",
            description="Most frequently used words in this guild",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        for rank, (word, count) in enumerate(top, start=1):
            embed.add_field(name=word_field_name(rank, word), value=f"{count} uses", inline=False)

        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    @topwords.command(name="user", description="Show the top 10 most used words by a user")
    @app_commands.describe(user="User to view, defaults to yourself")
    async def topwords_user(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        await interaction.response.defer(thinking=True)
        # Word usage is only tracked in aggregate per guild, not per user,
        # so per-user word breakdowns aren't available.
        await interaction.followup.send(
            f"Per-user word tracking isn't available; word stats are only tracked per server, not per user. "
            f"Try `/topwords guild` or `/topwords overall` instead."
        )
        await log_action(self.bot, interaction)

    # ===== Word Stats Commands =====
    wordstats = app_commands.Group(
        name="wordstats",
        description="Word statistics commands"
    )

    @wordstats.command(
        name="dictionary",
        description="Show percentage of dictionary or non-dictionary words"
    )
    @app_commands.describe(
        is_dict="True for dictionary words; False for non-dictionary words"
    )
    async def dictionary(self, interaction: discord.Interaction, is_dict: bool):
        await interaction.response.defer(thinking=True)

        total = len(words_stats)
        if total == 0:
            await interaction.followup.send("No word data yet.")
            return

        count = sum(1 for rec in words_stats.values() if rec.get('is_dict') == is_dict)
        percent = (count / total) * 100

        embed = discord.Embed(
            title="🔢 Word Dictionary Stats",
            description=(
                f"{percent:.2f}% of recorded words are "
                f"{'dictionary' if is_dict else 'non-dictionary'} words"
                f"\n({count} of {total})"
            ),
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    @wordstats.command(
        name="leastused",
        description="Show the 10 least used words"
    )
    async def leastused(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        if not words_stats:
            await interaction.followup.send("No word data yet.")
            return

        least = sorted(words_stats.values(), key=lambda rec: rec['count'])[:10]

        embed = discord.Embed(
            title="🔡 Least Used Words",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        for rank, rec in enumerate(least, start=1):
            embed.add_field(
                name=f"{rank}. {rec['word']}",
                value=f"{rec['count']} uses | is_dict={rec['is_dict']}",
                inline=False
            )

        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    @wordstats.command(
        name="search",
        description="Search usage stats for a specific word"
    )
    @app_commands.describe(
        word="Word to search"
    )
    async def search(self, interaction: discord.Interaction, word: str):
        await interaction.response.defer(thinking=True)

        matches = [rec for rec in words_stats.values() if rec['word'].lower() == word.lower()]
        if not matches:
            await interaction.followup.send(f"No stats found for '{word}'.")
            return

        total_count = sum(rec['count'] for rec in matches)
        is_dict = matches[0].get('is_dict')

        embed = discord.Embed(
            title=f"🔍 Word Stats: {word.lower()}",
            description=(
                f"Total uses: {total_count}\n"
                f"Dictionary word: {is_dict}"
            ),
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    @wordstats.command(
        name="dump",
        description="Dump all word statistics (global or guild) with pagination"
    )
    @app_commands.describe(
        scope="Scope to dump: 'global' or 'guild' (defaults to global)"
    )
    async def dump(self, interaction: discord.Interaction, scope: Optional[str] = "global"):  # noqa: C901
        await interaction.response.defer(thinking=True)

        scope_lower = scope.lower()
        if scope_lower not in ("global", "guild"):
            await interaction.followup.send("Invalid scope; choose 'global' or 'guild'.")
            return

        records: list[tuple[str, int, bool]] = []
        title = ""
        if scope_lower == "global":
            for rec in words_stats.values():
                records.append((rec['word'], rec['count'], rec['is_dict']))
            title = "Wordstats Dump (Global)"
        else:
            gid_str = str(interaction.guild_id)
            for rec in words_stats.values():
                if rec.get('guild_id') != gid_str:
                    continue
                records.append((rec['word'], rec['count'], rec['is_dict']))
            guild_obj = self.bot.get_guild(interaction.guild_id)
            title = f"Wordstats Dump (Guild: {guild_obj.name if guild_obj else gid_str})"

        if not records:
            await interaction.followup.send("No word data to dump.")
            return

        # Sort records alphabetically by word
        records.sort(key=lambda x: x[0].lower())

        # Paginate records into embeds
        chunk_size = 10
        pages: list[discord.Embed] = []
        total_pages = (len(records) + chunk_size - 1) // chunk_size
        for page_index in range(total_pages):
            chunk = records[page_index*chunk_size:(page_index+1)*chunk_size]
            embed = discord.Embed(
                title=title,
                color=discord.Color.random(),
                timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
            )
            lines = []
            start_num = page_index * chunk_size
            for idx, (word, count, is_dict) in enumerate(chunk, start=1):
                lines.append(f"{start_num + idx}. {word}: {count} uses | is_dict={is_dict}")
            embed.description = "\n".join(lines)
            embed.set_footer(text=f"Page {page_index+1}/{total_pages}")
            pages.append(embed)

        view = DumpView(pages)
        await interaction.followup.send(embed=pages[0], view=view)
        await log_action(self.bot, interaction)

    # ===== TopDict Commands =====
    topdict = app_commands.Group(
        name="topdict",
        description="Top dictionary words commands"
    )

    @topdict.command(
        name="global",
        description="Show the top 10 dictionary words used globally"
    )
    async def topdict_global(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        totals: dict[str, int] = {}
        for rec in words_stats.values():
            if not rec.get('is_dict'):
                continue
            word = rec['word']
            count = rec['count']
            totals[word] = totals.get(word, 0) + count
        if not totals:
            await interaction.followup.send("No dictionary word data yet.")
            return
        top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
        embed = discord.Embed(
            title="📚 Top 10 Dictionary Words (Global)",
            description="Most frequently used dictionary words across all guilds",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        for rank, (word, count) in enumerate(top, start=1):
            embed.add_field(name=word_field_name(rank, word), value=f"{count} uses", inline=False)
        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    @topdict.command(
        name="guild",
        description="Show the top 10 dictionary words in a guild"
    )
    @app_commands.describe(
        guild_id="Guild ID to view, defaults to current guild"
    )
    async def topdict_guild(
        self,
        interaction: discord.Interaction,
        guild_id: Optional[int] = None
    ):
        await interaction.response.defer(thinking=True)
        gid = str(guild_id) if guild_id else str(interaction.guild_id)
        totals: dict[str, int] = {}
        for rec in words_stats.values():
            if rec.get('guild_id') != gid or not rec.get('is_dict'):
                continue
            word = rec['word']
            count = rec['count']
            totals[word] = totals.get(word, 0) + count
        if not totals:
            await interaction.followup.send("No dictionary word data for this guild.")
            return
        top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
        guild_obj = self.bot.get_guild(int(gid)) if gid.isdigit() else None
        guild_name = guild_obj.name if guild_obj else gid
        embed = discord.Embed(
            title=f"📚 Top 10 Dictionary Words in {guild_name}",
            description="Most frequently used dictionary words in this guild",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        for rank, (word, count) in enumerate(top, start=1):
            embed.add_field(name=word_field_name(rank, word), value=f"{count} uses", inline=False)
        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    # ===== Non-Dictionary Words Commands =====
    nondict = app_commands.Group(
        name="nondict",
        description="Top non-dictionary words commands"
    )

    @nondict.command(
        name="global",
        description="Show the top 10 non-dictionary words used globally"
    )
    async def nondict_global(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        totals: dict[str, int] = {}
        for rec in words_stats.values():
            if rec.get('is_dict'):
                continue
            word = rec['word']
            count = rec['count']
            totals[word] = totals.get(word, 0) + count
        if not totals:
            await interaction.followup.send("No non-dictionary word data yet.")
            return
        top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
        embed = discord.Embed(
            title="📝 Top 10 Non-Dictionary Words (Global)",
            description="Most frequently used non-dictionary words across all guilds",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        for rank, (word, count) in enumerate(top, start=1):
            embed.add_field(name=word_field_name(rank, word), value=f"{count} uses", inline=False)
        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

    @nondict.command(
        name="guild",
        description="Show the top 10 non-dictionary words in a guild"
    )
    @app_commands.describe(
        guild_id="Guild ID to view, defaults to current guild"
    )
    async def nondict_guild(
        self,
        interaction: discord.Interaction,
        guild_id: Optional[int] = None
    ):
        await interaction.response.defer(thinking=True)
        gid = str(guild_id) if guild_id else str(interaction.guild_id)
        totals: dict[str, int] = {}
        for rec in words_stats.values():
            if rec.get('guild_id') != gid or rec.get('is_dict'):
                continue
            word = rec['word']
            count = rec['count']
            totals[word] = totals.get(word, 0) + count
        if not totals:
            await interaction.followup.send("No non-dictionary word data for this guild.")
            return
        top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
        guild_obj = self.bot.get_guild(int(gid)) if gid.isdigit() else None
        guild_name = guild_obj.name if guild_obj else gid
        embed = discord.Embed(
            title=f"📝 Top 10 Non-Dictionary Words in {guild_name}",
            description="Most frequently used non-dictionary words in this guild",
            color=discord.Color.random(),
            timestamp=datetime.datetime.now(ZoneInfo("Asia/Singapore"))
        )
        for rank, (word, count) in enumerate(top, start=1):
            embed.add_field(name=word_field_name(rank, word), value=f"{count} uses", inline=False)
        await interaction.followup.send(embed=embed)
        await log_action(self.bot, interaction)

async def setup(bot):
    await bot.add_cog(Stats(bot))
