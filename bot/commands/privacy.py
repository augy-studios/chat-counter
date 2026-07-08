import discord
from discord import app_commands
from discord.ext import commands

import db
from shared import stats
from core.logger import log_action


class Privacy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="deletemydata",
        description="Delete your message/word/character stats tracked by this bot"
    )
    async def deletemydata(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)

        deleted = db.delete_user_stats(uid)
        for key in [k for k in stats if k[0] == uid]:
            del stats[key]

        if deleted:
            await interaction.response.send_message(
                f"✅ Deleted your message/word/character stats from {deleted} server(s). "
                "Note: word-usage frequency stats are tracked in aggregate per server and aren't "
                "attributed to individual users, so they can't be selectively removed.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "You have no tracked stats to delete.", ephemeral=True
            )
        await log_action(self.bot, interaction)


async def setup(bot):
    await bot.add_cog(Privacy(bot))
