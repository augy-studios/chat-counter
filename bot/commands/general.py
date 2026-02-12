import discord
import random
from discord.ext import commands
from discord import app_commands
from core.logger import log_action

class HelpView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=120)
        self.pages = pages
        self.current = 0

        # Navigation buttons
        self.prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary)
        self.page_button = discord.ui.Button(label=f"1/{len(pages)}", style=discord.ButtonStyle.gray, disabled=True)
        self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary)

        # Assign callbacks
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

        # Add buttons to view
        self.add_item(self.prev_button)
        self.add_item(self.page_button)
        self.add_item(self.next_button)

        self.update_buttons()

    async def prev_page(self, interaction: discord.Interaction):
        self.current = max(self.current - 1, 0)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current = min(self.current + 1, len(self.pages) - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    def update_buttons(self):
        self.prev_button.disabled = (self.current == 0)
        self.next_button.disabled = (self.current == len(self.pages) - 1)
        self.page_button.label = f"{self.current + 1}/{len(self.pages)}"

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.command_ids = {}  # Store command IDs dynamically

    async def fetch_command_ids(self):
        """Fetch and store command IDs after syncing."""
        commands = await self.bot.tree.fetch_commands()
        for cmd in commands:
            self.command_ids[cmd.name] = cmd.id

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! 🏓 Latency: {latency}ms")
        await log_action(self.bot, interaction)

    @app_commands.command(name="hello", description="Learn more about the bot.")
    async def hello(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Hello!", color=discord.Color.random())
        link_to_add_bot = f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}"
        embed.add_field(name="Add Me to Your Server", value=f"[Click here!]({link_to_add_bot})")
        link_to_hello = "https://discord.gg/H4YYsgkYSa"
        embed.add_field(name="Bot Support", value=f"[Got questions? Join here!]({link_to_hello})")
        link_to_docs = "https://chatcounter.augystudios.com/"
        embed.add_field(name="How to Use", value=f"[View the documentation!]({link_to_docs})")
        link_to_status = "https://pages.statusbot.us/id/873989298507120690"
        embed.add_field(name="Bot Status", value=f"[Check the bot's status here!]({link_to_status})")
        link_to_coffee = "https://donate.stripe.com/28o2akeAr3hv0DK6oo"
        embed.add_field(name="Support the Bot", value=f"[Buy me a coffee!]({link_to_coffee})")
        link_to_monthly_support = "https://donate.stripe.com/6oEbKUdwn9FTgCI7st"
        embed.add_field(name="Monthly Support", value=f"[Support us monthly!]({link_to_monthly_support})")
        embed.add_field(name="Privacy Policy", value="[Click Here](https://augystudios.com/privacy)", inline=False)
        embed.set_footer(text="Made with ❤️ by Augy Studios © 2025 All Rights Sniffed • https://augystudios.com/")
        await interaction.response.send_message(embed=embed)
        await log_action(self.bot, interaction)

    @app_commands.command(name="help", description="Display a list of available commands categorized by their category.")
    @app_commands.describe(category="Choose a category to see its commands")
    async def help_command(self, interaction: discord.Interaction, category: str | None = None):
        base_embed = discord.Embed(
            title="Help - Available Commands",
            color=discord.Color.random()
        )
        base_embed.set_footer(text="Made with ❤️ by Augy Studios © 2025 All Rights Sniffed • https://augystudios.com/")

        # Collect commands grouped by Cog
        cog_commands: dict[str, list[str]] = {}
        for cog_name, cog in self.bot.cogs.items():
            lines: list[str] = []
            for cmd in cog.get_app_commands():
                cmd_id = self.command_ids.get(cmd.name)
                mention = f"</{cmd.name}:{cmd_id}>" if cmd_id else f"/{cmd.name}"
                lines.append(f"**{mention}** - {cmd.description}\n")
            if lines:
                cog_commands[cog_name] = lines

        # Handle invalid category
        if category and category not in cog_commands:
            await interaction.response.send_message(
                f"❌ No commands found for category: {category}",
                ephemeral=True
            )
            return

        # Build pages with a 1024-character limit per page
        pages_content: list[str] = []
        current_content = ""
        items = ((category, cog_commands[category]),) if category else cog_commands.items()

        for cog_name, lines in items:
            header = f"**{cog_name} Commands**\n"
            # Start new page if header itself doesn't fit
            if current_content and len(current_content) + len(header) > 1024:
                pages_content.append(current_content)
                current_content = ""

            # Ensure header present
            if not current_content.startswith(header):
                current_content += header

            # Add each command line, splitting pages as needed
            for line in lines:
                if len(current_content) + len(line) > 1024:
                    pages_content.append(current_content)
                    current_content = header + line
                else:
                    current_content += line

        if current_content:
            pages_content.append(current_content)

        # Convert to embeds
        pages: list[discord.Embed] = []
        for content in pages_content:
            embed = base_embed.copy()
            embed.description = content
            pages.append(embed)

        # Send paginated view
        view = HelpView(pages)
        await interaction.response.send_message(embed=pages[0], view=view)

    @help_command.autocomplete("category")
    async def help_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=c, value=c)
            for c in self.bot.cogs.keys()
            if current.lower() in c.lower()
        ]

async def setup(bot):
    cog = General(bot)
    await cog.fetch_command_ids()  # Fetch IDs before adding the cog
    await bot.add_cog(cog)
    # Fetch command IDs in the on_ready event instead of here
