"""Provides commands for pulling certain information."""

import os
import subprocess

import discord
from discord.ext.commands import BucketType, cooldown, guild_only
from discord_slash import SlashContext, cog_ext

from ._utils import *
from .chat import ChatbotChannel, ChatbotUser

blurple = discord.Color.blurple()
datetime_format = '%Y-%m-%d %H:%M:%S\nUTC'


class Info(Cog):
    """Commands for getting information about people and things on Discord."""

    def __init__(self, bot):

        super().__init__(bot)
        self.bot_version = os.popen("git rev-list --count HEAD").read()

    @cog_ext.cog_slash(name="user", description="Returns user information")
    async def slash_member(self, ctx: SlashContext, member: discord.Member = None):
        """Users slash handler"""
        if member is None:
            member = ctx.guild.get_member(ctx.author.id)
        await self.member(ctx, member=member)

    @command(name='user')
    @guild_only()
    async def member(self, ctx, *, member: discord.Member = None):
        """Retrieves how much a user has talked to the chatbot.  """
        if member is None:
            member = ctx.author

        user_data = await ChatbotUser.get_user(user_id=member.id)
        if user_data is not None:
            embed = discord.Embed(
                title=member.display_name, description=f'{member!s} ({member.id})', color=member.color)
            embed.set_thumbnail(url=member.avatar_url)
            embed.add_field(name='Total responded messages: ',
                            value=str(user_data.messages))
            embed.add_field(name='Banned: ', value=str(user_data.banned))
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title=member.display_name, description=f'{member!s} ({member.id})', color=member.color)
            embed.set_thumbnail(url=member.avatar_url)
            embed.add_field(name='Total responded messages: ', value=str(0))
            embed.add_field(name='Banned: ', value=str(False))
            await ctx.send(embed=embed)

    @cog_ext.cog_slash(name="channel", description="Returns channel information")
    async def slash_member(self, ctx: SlashContext, channel: discord.TextChannel = None):
        """Users slash handler"""
        if channel is None:
            channel = ctx.guild.get_channel(ctx.channel.id)
        await self.guildchannelgetter(ctx, channel=channel)

    @command(name='channel')
    async def guildchannelgetter(self, ctx, *, channel: discord.TextChannel = None):
        if channel is None:
            channel = ctx.channel
        channel_data = await ChatbotChannel.get_channel(channel_id=channel.id)
        if (channel_data is not None):
            embed = discord.Embed(
                title=channel.name, description=f'{channel.name}, ({channel.id})')
            embed.add_field(name='Total responded messages: ',
                            value=str(channel_data.messages))
            embed.add_field(name='Total trained messages: ',
                            value=str(channel_data.trained_messages))
            embed.add_field(name='Will respond in: ',
                            value=str(channel_data.respond_in))
            embed.add_field(name='Will train in: ',
                            value=str(channel_data.train_in))
        else:
            embed = discord.Embed(
                title=channel.name, description=f'{channel.name}, ({channel.id})')
            embed.add_field(name='Total responded messages: ', value=str(0))
            embed.add_field(name='Total trained messages: ',
                            value=str(0))
            embed.add_field(name='Will respond in: ', value=str('False'))
            embed.add_field(name='Will train in: ', value=str('False'))
        await ctx.send(embed=embed)

    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    @command(aliases=['server', 'guildinfo', 'serverinfo'])
    async def guild(self, ctx):
        """Retrieve information about this guild."""
        guild = ctx.guild
        embed = discord.Embed(title=f"Info for guild: {guild.name}",
                              color=blurple)

        embed.set_thumbnail(url=guild.icon_url)
        results = await ChatbotChannel.get_by(guild_id=guild.id)
        if results:
            channels = ''
            trainChannels = ''
            totalMessages = 0
            totalTrained = 0
            for result in results:
                totalMessages += result.messages
                totalTrained += result.trained_messages
                if result.train_in:
                    trainChannels += ' <#{}>'.format(result.channel_id)
                if result.respond_in:
                    channels += ' <#{}>'.format(result.channel_id)
            embed.add_field(name='Channels to respond in: ', value=channels)
            embed.add_field(name='Channels to train in: ', value=trainChannels)
            embed.add_field(name='Total messages: ', value=str(totalMessages))
            embed.add_field(name='Total trained messages: ', value=str(totalTrained))
            await ctx.send(embed=embed)
    
    @command(aliases=['botinfo'])
    async def info(self, ctx):
        """Retrieve statistics about the bot. """
        embed = discord.Embed(title=f"Info for bot: {ctx.bot.user.name}",
                              description=f'{ctx.bot.user.name!s} ({ctx.bot.user.id})', color=blurple)

        embed.set_thumbnail(url=ctx.bot.user.avatar_url)
        results = await ChatbotChannel.get_by()
        if results:
            totalMessages = 0
            totalTrained = 0
            trainingChannels = 0
            respondingChannels = 0
            for result in results:
                if result.train_in:
                    trainingChannels += 1
                if result.respond_in:
                    respondingChannels += 1
                totalMessages += result.messages
                totalTrained += result.trained_messages
            temp = os.popen("/opt/vc/bin/vcgencmd measure_temp").read()
            embed.add_field(name='Bot Version:', value=str(self.bot_version))
            embed.add_field(name='Server Temperature: ', value=temp[5:])
            embed.add_field(name='Messages responded to total:',
                            value=str(totalMessages))
            embed.add_field(name='Messages learned from total:',
                            value=str(totalTrained))
            embed.add_field(name='Channels responding in: ',
                            value=str(respondingChannels))
            embed.add_field(name='Channels learning in: ',
                            value=str(trainingChannels))
            up = subprocess.check_output(['uptime', '-p']).decode('utf-8').strip()
            embed.add_field(name='Server uptime: ', value=up[2:])
            await ctx.send(embed=embed)


def setup(bot):
    """Adds the info cog to the bot"""
    bot.add_cog(Info(bot))
