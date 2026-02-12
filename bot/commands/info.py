from discord.ext import commands
from discord import app_commands, ui
import discord
import platform
import random
from core.logger import log_action
from config import BOT_OWNER_ID
from user_utils import ensure_users_file, get_known_users

# Function to split long messages into pages
def paginate_list(items, title):
    """Splits long lists into pages that fit within Discord's message limits."""
    chunk_size = 1900  # Discord's message character limit is around 2000
    pages = []
    current_page = title + "\n"

    for item in items:
        if len(current_page) + len(item) + 2 > chunk_size:  # +2 for newline characters
            pages.append(current_page)
            current_page = title + "\n" + item + "\n"
        else:
            current_page += item + "\n"

    if current_page.strip():
        pages.append(current_page)

    return pages

class BotInfoView(ui.View):
    """Handles button interactions for listing known users, channels, and guilds."""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def show_paginated_list(self, interaction, item_type, items):
        """Handles showing paginated lists when a button is clicked."""
        if not items:
            await interaction.response.send_message(f"No {item_type.lower()} found.", ephemeral=True)
            return

        items = sorted(items, key=lambda x: x.lower())  # Sort items alphabetically
        view = PaginatedListView(self.bot, item_type, items)
        await interaction.response.send_message(content=f"```{view.pages[0]}```", ephemeral=True, view=view)

    @ui.button(label="List Known Users", style=discord.ButtonStyle.primary, custom_id="list_users")
    async def list_users(self, interaction: discord.Interaction, button: ui.Button):
        known_users = get_known_users()
        await self.show_paginated_list(interaction, "Known Users", known_users)

    @ui.button(label="List Channels", style=discord.ButtonStyle.success, custom_id="list_channels")
    async def list_channels(self, interaction: discord.Interaction, button: ui.Button):
        channels = sorted([f"{channel.name} ({channel.id})" for guild in self.bot.guilds for channel in guild.channels], key=lambda x: x.lower())
        await self.show_paginated_list(interaction, "Channels", channels)

    @ui.button(label="List Guilds", style=discord.ButtonStyle.danger, custom_id="list_guilds")
    async def list_guilds(self, interaction: discord.Interaction, button: ui.Button):
        guilds = sorted([f"{guild.name} ({guild.id})" for guild in self.bot.guilds], key=lambda x: x.lower())
        await self.show_paginated_list(interaction, "Guilds", guilds)

class PaginatedListView(ui.View):
    """Handles paginated navigation for large lists."""
    def __init__(self, bot, item_type, items):
        super().__init__(timeout=None)
        self.bot = bot
        self.item_type = item_type
        self.items = items
        self.page = 0
        self.pages = paginate_list(items, f"{item_type} List:")
        self.update_page_counter()

    def update_page_counter(self):
        """Updates the page counter label dynamically."""
        self.children[2].label = f"Page {self.page + 1}/{len(self.pages)}"

    async def update_page(self, interaction):
        """Updates the page content when a button is clicked."""
        self.update_page_counter()
        content = f"```{self.pages[self.page]}```"
        await interaction.response.edit_message(content=content, view=self)

    @ui.button(label="⏮ First", style=discord.ButtonStyle.secondary, custom_id="first_page")
    async def first_page(self, interaction: discord.Interaction, button: ui.Button):
        if self.page > 0:
            self.page = 0
            await self.update_page(interaction)

    @ui.button(label="⬅ Previous", style=discord.ButtonStyle.secondary, custom_id="prev_page")
    async def prev_page(self, interaction: discord.Interaction, button: ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_page(interaction)
    
    @ui.button(label="Page 1/1", style=discord.ButtonStyle.grey, custom_id="page_number", disabled=True)
    async def page_number(self, interaction: discord.Interaction, button: ui.Button):
        pass  # This button is just for display

    @ui.button(label="Next ➡", style=discord.ButtonStyle.secondary, custom_id="next_page")
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        if self.page < len(self.pages) - 1:
            self.page += 1
            await self.update_page(interaction)

    @ui.button(label="⏭ Last", style=discord.ButtonStyle.secondary, custom_id="last_page")
    async def last_page(self, interaction: discord.Interaction, button: ui.Button):
        if self.page < len(self.pages) - 1:
            self.page = len(self.pages) - 1
            await self.update_page(interaction)

class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="Get user information.")
    @app_commands.describe(member="The user to get information about")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member):
        embed = discord.Embed(title="User Info", color=discord.Color.random())
        embed.add_field(name="Username", value=member.name, inline=False)
        embed.add_field(name="User ID", value=member.id, inline=False)
        embed.add_field(name="Joined", value=member.joined_at, inline=False)
        await interaction.response.send_message(embed=embed)
        await log_action(self.bot, interaction)

    @app_commands.command(name="serverinfo", description="Get server information.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title="Guild Info", color=discord.Color.random())
        embed.add_field(name="Guild Name", value=guild.name)
        embed.add_field(name="Guild ID", value=guild.id)
        embed.add_field(name="Member Count", value=guild.member_count)
        await interaction.response.send_message(embed=embed)
        await log_action(self.bot, interaction)

    @app_commands.command(name="botinfo", description="Get detailed bot information.")
    async def botinfo(self, interaction: discord.Interaction):
        ensure_users_file()  # Make sure the users.txt file is checked/created
        known_users = get_known_users()  # Get users from users.txt
        total_channels = sum(len(guild.channels) for guild in self.bot.guilds)
        total_guilds = len(self.bot.guilds)
        
        # Count the total number of commands across all cogs
        total_commands = 0
        for cog_name, cog in self.bot.cogs.items():
            total_commands += len(cog.get_app_commands())

        # Get bot description from application info
        app_info = await self.bot.application_info()
        bot_description = app_info.description or "No description provided."
        shard_count = self.bot.shard_count

        # Embed information
        embed = discord.Embed(title="Bot Info", color=discord.Color.random())
        embed.add_field(name="Bot Name", value=self.bot.user.name, inline=True)
        embed.add_field(name="Owner ID", value=str(BOT_OWNER_ID), inline=True)
        embed.add_field(name="Bot Description", value=bot_description, inline=False)
        embed.add_field(name="Python Version", value=platform.python_version(), inline=True)
        embed.add_field(name="Library", value="discord.py", inline=True)
        embed.add_field(name="Commands", value=str(total_commands), inline=True)
        embed.add_field(name="Shards", value=shard_count, inline=True)
        embed.add_field(name="Guilds", value=str(total_guilds), inline=True)
        embed.add_field(name="Channels", value=str(total_channels), inline=True)
        embed.add_field(name="Known Users", value=str(len(known_users)), inline=True)
        embed.add_field(name="Privacy Policy", value="[Click Here](https://augystudios.com/privacy)", inline=False)

        # If the user is the bot owner, provide buttons to list users, channels, or guilds
        if interaction.user.id == BOT_OWNER_ID:
            await interaction.response.send_message(embed=embed, view=BotInfoView(self.bot))
        else:
            await interaction.response.send_message(embed=embed)

        await log_action(self.bot, interaction)

async def setup(bot):
    await bot.add_cog(Info(bot))
