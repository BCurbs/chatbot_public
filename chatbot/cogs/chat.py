"""Records members' XP and level."""

import asyncio
import concurrent.futures
import logging
import re

import aiohttp
import discord
from chatterbot import ChatBot
from chatterbot.trainers import ListTrainer, ChatterBotCorpusTrainer
from discord.ext import commands
from discord.ext.commands import guild_only, has_permissions, NotOwner, UserInputError
from discord.ext.tasks import loop

from ._utils import *
from .. import db
from ..utils import clean

globalratelimit = 2
clearcache = False
blurple = discord.Color.blurple()
db_url = "postgres://postgres:thick31BPC@192.168.86.94"
CHATBOT_LOGGER = logging.getLogger(__name__)
readOnlyBot = ChatBot(
    'Fred',
    read_only=True,
    storage_adapter='chatterbot.storage.SQLStorageAdapter',
    logic_adapters=[
        'chatterbot.logic.BestMatch'
    ],
    database_uri=db_url
)
bot = ChatBot(
    'Fred',
    storage_adapter='chatterbot.storage.SQLStorageAdapter',
    logic_adapters=[
        'chatterbot.logic.BestMatch'
    ],
    database_uri=db_url
)


async def train_process(a, b):
    loop = asyncio.get_running_loop()
    with concurrent.futures.ProcessPoolExecutor() as pool:
        loop.run_in_executor(pool, train, a, b)


def train(a, b):
    try:
        ListTrainer(ChatBot(
            'Fred',
            storage_adapter='chatterbot.storage.SQLStorageAdapter',
            logic_adapters=[
                'chatterbot.logic.BestMatch'
            ],
            database_uri=db_url
        )).train([a, b])
    except:
        pass


async def respond_process(content):
    loop = asyncio.get_running_loop()
    with concurrent.futures.ProcessPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, respond, content)
        return result


def respond(a):
    try:
        bot_input = ChatBot(
            'Fred',
            read_only=True,
            storage_adapter='chatterbot.storage.SQLStorageAdapter',
            logic_adapters=[
                'chatterbot.logic.BestMatch'
            ],
            database_uri=db_url
        ).get_response(a)
    except Exception as e:
        bot_input = "You broke the chatbot. Sorry for the inconvenience. " + \
                    str(e)

    return str(bot_input)


class Chat(Cog):
    """Commands and event handlers for chatting with the bot"""

    def __init__(self, bot):
        super().__init__(bot)
        self._loop = bot.loop
        self.session = aiohttp.ClientSession(loop=bot.loop)
        self._channel_cache = {}

    @Cog.listener("on_ready")
    async def on_ready(self):
        await db.Pool.execute("""
            UPDATE chatbot_channels
            SET processing = 0
            WHERE true;
        """)
        await self.preloadcache()

    async def is_developer(ctx):
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('You are not a developer!')
        else:
            return True

    @command()
    @commands.check(is_developer)
    async def ban(self, ctx, user: discord.User):
        """Bans a user from the chatbot. """
        if user is None:
            raise UserInputError('You must specify a user')
        db_user = await ChatbotUser.get_user(user_id=user.id)
        if db_user is not None:
            await db_user.ban()
            await ctx.send('User banned from chatbot. ')
        else:
            db_user = await ChatbotUser.create_user(user_id=user.id, user_name=user.name, banned=True)

            await ctx.send('User banned from chatbot. ')

    @command()
    @commands.check(is_developer)
    async def unban(self, ctx, user: discord.User):
        """Unbans a user from the chatbot. """
        if user is None:
            raise UserInputError('You must specify a user')
        db_user = await ChatbotUser.get_user(user_id=user.id)
        if db_user is not None:
            if db_user.banned:
                await db_user.unban()
                await ctx.send('User unbanned from chatbot. ')
            else:
                await ctx.send('User is not banned. ')
        else:
            await ctx.send('User is not in database. ')

    @command()
    @commands.check(is_developer)
    async def getdatabasecolumns(self, ctx):
        results = await db.Pool.fetch("""
            SELECT * FROM chatbot_channels;
        """)
        await ctx.send(str(len(results)))

    @command(name='train')
    async def usertrain(self, ctx):
        """Allows users to add custom training to the bot"""
        message = ctx.message
        user = await ChatbotUser.get_user(user_id=message.author.id)
        if user is None:
            user = ChatbotUser.create_user(
                user_id=message.author.id, user_name=message.author.name)

        if user.banned:
            await message.channel.send('You are banned from training the chatbot to ensure the safety of other users.')
            return
        if '-trigger' not in message.content:
            await message.channel.send('You are missing your -trigger argument.')
            # check to see if trigger is present
            return

        if '-response' not in message.content:
            await message.channel.send('Sorry it appears that you are missing your -response argument. ')
            # check to see if response is present
            return

        part1re = re.search('-trigger(.*)-response', message.content).group(0)
        part1 = part1re[8:].replace('-response', '')
        part1 = part1.replace("\n", "/n")
        # trim the regex statement to the necessary part

        part2 = message.content.partition('-response')[2]
        part2 = part2.replace("\n", "/n")
        # get the part after -response
        if len(part1.replace(' ', '')) < 1:
            await message.channel.send(
                'Your trigger looks like its either all spaces or has like 1 character in it. Maybe try again with '
                'more real charachters?')
            return
            # make sure it isnt all spaces or 1 letter
        if len(part2.replace(' ', '')) < 1:
            await message.channel.send(
                'Your response looks like its either all spaces or has like 1 character in it. Maybe try again with '
                'more real charachters?')
            return
            # make sure it isnt all spaces or 1 letter
        part1 = part1.strip()
        part2 = part2.strip()
        a = await message.channel.send(
            'Training: \n' + part1.replace("/n", "\n") + '\nWith: \n' + part2.replace("/n", "\n"))

        await train_process(part1, part2)
        await a.edit(content='Trained: \n' + part1.replace("/n", "\n") + ' \nWith: \n' + part2.replace("/n", "\n"))
        await ChatbotTraining.new_training(part1=part1, part2=part2, message_id=message.id, user_id=message.author.id,
                                           user_name=message.author.name, is_manual=True)

    usertrain.example_usage = """
    `{prefix}train -trigger Hi -response Hello` - Trains Hi with the response Hello
    """

    @command()
    @guild_only()
    @has_permissions(manage_guild=True)
    async def stoptraining(self, ctx, *, channel: discord.TextChannel = None):
        """Stop the chatbot from learning in a channel. """
        if channel is None:
            channel = ctx.channel

        db_channel = await self.load_channel(channel.id, channel.guild.id)

        if not db_channel.train_in:
            await ctx.send('Chatbot already did not train in <#{}>'.format(channel.id))
        else:
            db_channel.train_in = False
            db_channel.dirty = True
            await self.sync_channel(channel.id, channel.guild.id)
            await ctx.send('Chatbot will not train in <#{}>'.format(channel.id))

    @command()
    @guild_only()
    @has_permissions(manage_guild=True)
    async def trainin(self, ctx, *, channel: discord.TextChannel = None):
        """Make the chatbot learn in a channel. """
        if channel is None:
            channel = ctx.channel

        db_channel = await self.load_channel(channel.id, channel.guild.id)

        if db_channel.train_in is False:
            db_channel.train_in = True
            db_channel.dirty = True
            await self.sync_channel(channel.id, channel.guild.id)
            await ctx.send(f'Chatbot will now train in channel <#{channel.id}>.')
        else:
            await ctx.send(f'Chatbot already trained in channel <#{channel.id}>.')

    @command()
    @guild_only()
    @has_permissions(manage_guild=True)
    async def removechannel(self, ctx, *, channel: discord.TextChannel = None):
        """Remove a channel that the bot responds in"""
        if channel is None:
            channel = ctx.channel

        db_channel = await self.load_channel(channel.id, channel.guild.id)

        if not db_channel.respond_in:
            await ctx.send(f'Chatbot already did not respond in <#{channel.id}>')
        else:
            db_channel.respond_in = False
            db_channel.dirty = True
            await self.sync_channel(channel.id, channel.guild.id)
            await ctx.send(f'Chatbot will not respond in <#{channel.id}>')

    @command()
    @guild_only()
    @has_permissions(manage_guild=True)
    async def addchannel(self, ctx, *, channel: discord.TextChannel = None):
        """Add a new channel that the bot responds in"""
        if channel is None:
            channel = ctx.channel

        db_channel = await self.load_channel(channel.id, channel.guild.id)

        if db_channel.respond_in is False:
            db_channel.respond_in = True
            db_channel.dirty = True
            await self.sync_channel(channel.id, channel.guild.id)
            await ctx.send(f'Chatbot will now respond in channel <#{channel.id}>')
        else:
            await ctx.send(f'Chatbot already responded in channel <#{channel.id}>')

    @command()
    @commands.check(is_developer)
    async def droptraining(self, ctx):
        await db.Pool.execute("""DROP TABLE statement CASCADE; """)
        await db.Pool.execute("""DROP TABLE tag CASCADE; """)
        await db.Pool.execute("""DROP TABLE tag_association CASCADE; """)
        await ctx.send("Dropped training. Reloading cog. ")
        await self.bot.reload_cog('chatbot.cogs.chat')

    @command()
    @commands.check(is_developer)
    async def loadtraining(self, ctx):
        msg = await ctx.send("Loading from sql server")
        i = 0
        data = await ChatbotTraining.get_by()
        await msg.edit(content=f"Loaded {str(len(data))} statements from sql server. ")
        if data:
            for strings in data:
                i += 1
                await train_process(strings.part1, strings.part2)
        await ctx.send(f"Done training. Trained {str(i)} statements")

    @command()
    @commands.check(is_developer)
    async def checkcache(self, ctx):
        await ctx.send("Cache contains: " + str(len(self._channel_cache.keys())))

    @command()
    @commands.check(is_developer)
    async def loadcorpustraining(self, ctx):
        await ctx.send("Loading training from corpus. ")
        trainer = ChatterBotCorpusTrainer(bot)
        list = [
            "chatterbot.corpus.english.ai",
            "chatterbot.corpus.english.computers",
            "chatterbot.corpus.english.conversations",
            "chatterbot.corpus.english.botprofile",
            "chatterbot.corpus.english.emotion",
            "chatterbot.corpus.english.gossip",
            "chatterbot.corpus.english.food",
            "chatterbot.corpus.english.greetings",
            "chatterbot.corpus.english.health",
            # "chatterbot.corpus.english.history",
            # "chatterbot.corpus.english.humor",
            "chatterbot.corpus.english.literature",
            "chatterbot.corpus.english.money",
            "chatterbot.corpus.english.movies",
            # "chatterbot.corpus.english.politics",
            "chatterbot.corpus.english.psychology",
            # "chatterbot.corpus.english.science",
            "chatterbot.corpus.english.sports",
            "chatterbot.corpus.english.trivia"
            #    "chatterbot.corpus.english"
        ]
        for a in list:
            await ctx.send(f"Training {a.split('.')[3]}")
            trainer.train(a)
        await ctx.send("Done training. ")

    async def load_channel(self, channel_id, guild_id):
        """Check to see if a member is in the level cache and if not load from the database"""
        cached_channel = self._channel_cache.get(channel_id)
        if cached_channel is None:
            CHATBOT_LOGGER.debug("Cache miss: channel_id = %d", channel_id)
            cached_channel = await ChatbotChannelCache.from_channel_id(channel_id=channel_id, guild_id=guild_id)
            # records = await ChatbotChannel.get_by(channel_id=channel_id)
            # if records:
            #     CHATBOT_LOGGER.debug("Loading from database")
            #     cached_channel = ChatbotChannelCache.from_record(records[0])
            # else:
            #     CHATBOT_LOGGER.debug("Creating from scratch")
            #     cached_channel = ChatbotChannelCache(
            #         0, datetime.now(tz=timezone.utc), 0, True)
            self._channel_cache[channel_id] = cached_channel
        return cached_channel

    async def sync_channel(self, channel_id, guild_id):
        """Sync an individual member to the database"""
        cached_member = self._channel_cache.get(channel_id)
        if cached_member:
            e = ChatbotChannel(channel_id=channel_id, guild_id=guild_id,
                               messages=cached_member.messages,
                               respond_in=cached_member.respond_in, processing=cached_member.processing,
                               last_message=cached_member.last_message, train_in=cached_member.train_in,
                               trained_messages=cached_member.trained_messages,
                               channel_name=cached_member.channel_name)
            await e.update_or_add()
            cached_member.dirty = False
            return True
        else:
            return False

    async def should_respond_channel(self, channel):

        if channel.respond_in is True:
            return True
        return False

    async def should_respond_message(self, message, author, channel):
        if message.content.lower().startswith('-'):
            return False
        if author.banned is True:
            await message.reply('You have been banned from the chatbot for the safety of our users. ',
                                mention_author=False)
            return False
        if message.reference is not None and message.reference.message_id is not None:
            repliedto = await message.channel.fetch_message(message.reference.message_id)
            if not repliedto.content.startswith('-'):
                if repliedto.author.id != self.bot.user.id:
                    return False
            else:
                return False
        # bot should not respond if processing is > rate limit
        if channel.processing >= globalratelimit:
            await message.reply('Your channel has too many messages waiting to be processed. Your input has been '
                                'ignored. ')
            return False
        else:
            # await channel.updateProcessing(1)
            channel.processing += 1
            channel.dirty = True

        return True

    async def should_train(self, channel, message):
        if message.content.startswith("-"):
            return False, "", ""
        if channel:
            if not channel.train_in:
                return False, "", ""
            if message.reference is not None and message.reference.message_id is not None:
                repliedto = await message.channel.fetch_message(message.reference.message_id)
                if not repliedto.content.startswith('-'):
                    return True, repliedto.content, message.content
                else:
                    return False, "", ""
            else:
                if channel.last_message is not None:
                    return True, channel.last_message, message.content
                else:
                    return False, "", ""
        else:
            return False, "", ""

    @Cog.listener('on_message')
    @guild_only()
    async def respond_to_message(self, message):
        """Check if message channel is valid and if so respond in it."""
        try:
            if message.author.bot:
                return
            ctx = await self.bot.get_context(message)
            channel = await self.load_channel(message.channel.id, message.channel.guild.id)
            print(channel)
            if channel.channel_name != message.channel.name:
                channel.channel_name = message.channel.name
                channel.dirty = True
            toTrain, part1, part2 = await self.should_train(channel, message)
            part1 = clean(ctx, part1)
            part2 = clean(ctx, part2)
            if await self.should_respond_channel(channel):

                author = await ChatbotUser.get_user(user_id=message.author.id)

                if author is None:
                    author = await ChatbotUser.create_user(message.author.id, message.author.name)
                if await self.should_respond_message(message, author, channel):

                    a = await message.reply('Processing:', mention_author=False)
                    user_content = clean(ctx, message.content)
                    if message.attachments:
                        for attachment in message.attachments:
                            url = attachment.url
                            user_content = user_content + '\n' + url

                    result = await respond_process(user_content)
                    await a.edit(content=clean(ctx, result.replace("/n", "\n")))
                    if not result.startswith("You broke the chatbot. Sorry for the inconvenience. "):
                        # await db.Pool.execute(f"""UPDATE chatbot_channels
                        # SET last_message = $1
                        # WHERE channel_id = {message.channel.id};""", result)
                        channel.last_message = result
                        channel.messages += 1
                        channel.dirty = True
                    channel.processing -= 1
                    # await channel.updateProcessing(-1)
                    await author.update_messages(+1, message.author.name)
            if toTrain is True:
                await train_process(part1, part2)
                await ChatbotTraining.new_training(part1=part1, part2=part2, is_manual=False, message_id=message.id,
                                                   user_id=message.author.id, user_name=message.author.name)

                # await channel.updateSelf()

                # await db.Pool.execute(f"""UPDATE chatbot_channels
                #     SET trained_messages = {channel.trained_messages + 1}
                #     WHERE channel_id = {message.channel.id};""")

                # trained_messages = channel.messages
                channel.trained_messages += 1
                channel.dirty = True
                # await db.Pool.execute("""UPDATE chatbot_channels
                # SET messages = {}
                # WHERE channel_id = {};""".format(trained_messages + 1, message.channel.id))

        except Exception as e:
            await message.channel.send("```" + str(e) + "```")
            await message.channel.send("```" + str(e.__traceback__.tb_lineno) + "```")

    async def preloadcache(self):
        results = await ChatbotChannel.get_by()
        # await ctx.send(f"Loaded {str(len(results))} channels from database")
        if results:
            for result in results:
                self._channel_cache[result.channel_id] = ChatbotChannelCache.from_record(
                    result)
            # await ctx.send(f"Loaded {str(len(self._channel_cache.keys()))} channels to cache")

    @loop(minutes=2.5)
    async def sync_task(self):
        """Sync dirty records to the database, and evict others from the cache.
        This function merely wraps `sync_to_database` into a periodic task.
        """
        # @loop(...) assumes that getattr(self, func.__name__) is the task, so this needs to be a new function instead
        # of `sync_task = loop(minutes=1)(sync_to_database)`

        await self.sync_to_database()

    async def sync_to_database(self):
        """Sync dirty records to the database, and evict others from the cache."""

        # Deleting from a dict while iterating will error, so collect the keys up front and iterate that
        # Note that all mutation of `self._xp_cache` happens before the first yield point to prevent race conditions
        keys = list(self._channel_cache.keys())
        to_write = []  # records to write to the database
        evicted = 0
        for (channel_id) in keys:
            cached_channel = self._channel_cache[channel_id]
            if clearcache:
                if not cached_channel.dirty:
                    # Evict records that haven't changed since last run from cache to conserve memory
                    del self._channel_cache[channel_id]
                    evicted += 1
                    continue
            to_write.append((channel_id, cached_channel.messages, cached_channel.respond_in, 0,
                             cached_channel.last_message, cached_channel.train_in, cached_channel.trained_messages,
                             cached_channel.channel_name))
            cached_channel.dirty = False

        if not to_write:
            CHATBOT_LOGGER.debug("Sync task skipped, nothing to do")
            return
        # Query written manually to insert all records at once
        try:
            async with db.Pool.acquire() as conn:
                await conn.executemany(f"INSERT INTO {ChatbotChannel.__tablename__} (channel_id, messages, "
                                       f"respond_in, last_message, processing, train_in, trained_messages, "
                                       f"channel_name) "
                                       f" VALUES ($1, $2, $3, $4, $5, $6, $7, $8) ON CONFLICT ({ChatbotChannel.__uniques__}) DO UPDATE "
                                       f" SET messages = EXCLUDED.messages, respond_in = EXCLUDED.respond_in, "
                                       f"last_message = EXCLUDED.last_message, "
                                       f"processing = EXCLUDED.processing, train_in = EXCLUDED.train_in, "
                                       f"trained_messages = EXCLUDED.trained_messages, channel_name = "
                                       f"EXCLUDED.channel_name;",
                                       to_write)
            CHATBOT_LOGGER.debug(
                f"Inserted/updated {len(to_write)} record(s); Evicted {evicted} records(s)")
        except Exception as e:
            CHATBOT_LOGGER.error(
                f"Failed to sync levels cache to db, Reason:{e}")


class ChatbotTraining(db.DatabaseTable):
    """Database table mapping all training from chatbot"""
    __tablename__ = "chatbot_training"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""CREATE TABLE IF NOT EXISTS chatbot_training (
                    user_name varchar NULL,
                    part1 varchar NOT NULL,
                    part2 varchar NOT NULL,
                    user_id int8 NOT NULL,
                    message_id int8 NULL,
                    is_manual bool NOT NULL DEFAULT true
                );
            """)

    def __init__(self, user_name, part1, part2, user_id, message_id, is_manual):
        super().__init__()
        self.user_name = user_name
        self.part1 = part1
        self.part2 = part2
        self.user_id = user_id
        self.message_id = message_id
        self.is_manual = is_manual

    @classmethod
    async def new_training(cls, user_name, part1, part2, user_id, message_id, is_manual):
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
                        INSERT INTO chatbot_training
                        (user_name, part1, part2, user_id, message_id, is_manual)
                        VALUES ($1, $2, $3, $4, $5, $6);
                    """, user_name, part1, part2, user_id, message_id,
                               is_manual)

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ChatbotTraining(user_id=result.get("user_id"), part1=result.get("part1"),
                                  part2=result.get("part2"), user_name=result.get("user_name"),
                                  message_id=result.get("message_id"), is_manual=result.get("is_manual"))
            result_list.append(obj)
        return result_list


class ChatbotUser(db.DatabaseTable):
    """Database table mapping a user to their chatbot stuff"""
    __tablename__ = "chatbot_users"
    __uniques__ = "user_id"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS chatbot_users (
                user_id int8 NOT NULL,
                banned bool NOT NULL DEFAULT false,
                messages int4 NULL DEFAULT 0,
                user_name varchar NULL,
                CONSTRAINT chatbot_users_pk PRIMARY KEY (user_id)
            );
            """)

    def __init__(self, user_id, banned, messages, user_name):
        super().__init__()
        self.user_id = user_id
        self.banned = banned
        self.messages = messages
        self.user_name = user_name

    async def updateSelf(self):
        result = await db.Pool.fetchrow(f"""
        SELECT * FROM chatbot_users
        WHERE user_id = $1;""", self.user_id)
        self.user_id = result.get("user_id")
        self.banned = result.get("banned")
        self.messages = result.get("messages")
        self.user_name = result.get("user_name")

    @classmethod
    async def create_user(cls, user_id, user_name, banned=False, messages=0):
        await db.Pool.execute(
            f"""INSERT INTO chatbot_users
                VALUES ($1,$2,$3,$4);""",
            user_id, banned, messages, user_name)

        return await cls.get_user(user_id=user_id)

    async def update_messages(self, messages, user_name):
        self.messages = await db.Pool.fetchval(f"""
            SELECT messages 
            FROM chatbot_users
            WHERE user_id = {self.user_id};
        """)
        self.messages += messages
        self.user_name = user_name
        await db.Pool.execute("""UPDATE chatbot_users
            SET messages = {}, user_name = $1
            WHERE user_id = {};""".format(self.messages, self.user_id), self.user_name)

    async def ban(self):
        await db.Pool.execute(f"""UPDATE chatbot_users
                SET banned = true
                WHERE user_id = {self.user_id};""")
        self.banned = True

    async def unban(self):
        await db.Pool.execute(f"""UPDATE chatbot_users
                SET banned = false
                WHERE user_id = {self.user_id};""")
        self.banned = False

    @classmethod
    async def get_user(cls, **kwargs):
        results = await ChatbotUser.get_by(**kwargs)

        if results:
            return results[0]
        return None

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ChatbotUser(user_id=result.get("user_id"), banned=result.get("banned"),
                              messages=result.get("messages"), user_name=result.get("user_name"))
            result_list.append(obj)
        return result_list


class ChatbotChannelCache:
    """ A cached record of a user's XP.
        This has all of the fields of `MemberXP` except the primary key, and an additional `dirty` flag that indicates
        whether the record has been changed since it was loaded from the database or created.
    """

    def __init__(self, guild_id, messages, respond_in, last_message, train_in, trained_messages, channel_name):
        super().__init__()
        self.guild_id = guild_id
        self.messages = messages
        self.respond_in = respond_in
        self.processing = 0
        self.last_message = last_message
        self.train_in = train_in
        self.trained_messages = trained_messages
        self.channel_name = channel_name
        self.dirty = False

    # def __repr__(self):
    #     return f"<MemberXPCache total_xp={self.total_xp!r} last_given_at={self.last_given_at!r} total_messages={self.last_given_at!r}" \
    #            f" dirty={self.dirty!r}>"

    @classmethod
    async def from_channel_id(cls, channel_id, guild_id):
        record = await ChatbotChannel.get_channel(channel_id=channel_id)
        if record is None:
            return cls(guild_id, 0, False, None, False, 0, "")
        else:
            return cls(record.guild_id, record.messages, record.respond_in, record.last_message, record.train_in,
                       record.trained_messages, record.channel_name)

    @classmethod
    def from_record(cls, record):
        """Create a cache entry from a database record. This copies all shared fields and sets `dirty` to False."""
        return cls(record.guild_id, record.messages, record.respond_in, record.last_message, record.train_in, record.trained_messages,
                   record.channel_name)


class ChatbotChannel(db.DatabaseTable):
    """Database table containing per-channel settings related to chatbot stuff."""
    __tablename__ = "chatbot_channels"
    __uniques__ = "channel_id"

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE chatbot_channels (
                channel_id int8 NOT NULL,
                guild_id int8 NOT NULL,
                messages int4 NOT NULL DEFAULT 0,
                respond_in bool NOT NULL,
                processing int4 NOT NULL DEFAULT 0,
                last_message varchar NULL,
                train_in bool NOT NULL DEFAULT true,
                trained_messages int4 NOT NULL DEFAULT 0,
                channel_name varchar NULL,
                CONSTRAINT chatbot_channels_pkey PRIMARY KEY (channel_id)
            );
            CREATE UNIQUE INDEX chatbot_channels_channel_id_idx ON public.chatbot_channels USING btree (channel_id);
            CREATE INDEX chatbot_channels_guild_id_idx ON public.chatbot_channels USING btree (guild_id);
            """)

    def __init__(self, channel_id, guild_id, messages, respond_in, processing, last_message, train_in,
                 trained_messages, channel_name):
        super().__init__()
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.messages = messages
        self.respond_in = respond_in
        self.processing = processing
        self.last_message = last_message
        self.train_in = train_in
        self.trained_messages = trained_messages
        self.channel_name = channel_name

    async def updateSelf(self):
        result = await db.Pool.fetchrow("""
            SELECT * FROM chatbot_channels
            WHERE channel_id = {};
            """.format(self.channel_id))
        self.channel_id = result.get("channel_id")
        self.guild_id = result.get("guild_id")
        self.messages = result.get("messages")
        self.respond_in = result.get("respond_in")
        self.processing = result.get("processing")
        self.last_message = result.get("last_message")
        self.train_in = result.get("train_in")
        self.trained_messages = result.get("trained_messages")

    async def update_messages(self, messages):
        self.messages = await db.Pool.fetchval(f"""
            SELECT messages 
            FROM chatbot_channels
            WHERE channel_id = {self.channel_id};
        """)
        self.messages += messages
        await db.Pool.execute("""UPDATE chatbot_channels
            SET messages = {}
            WHERE channel_id = {};""".format(self.messages, self.channel_id))

    async def updateProcessing(self, processing):
        self.processing = await db.Pool.fetchval(f"""
            SELECT processing 
            FROM chatbot_channels 
            WHERE channel_id = {self.channel_id};
        """)
        self.processing += processing
        await db.Pool.execute("""
        UPDATE chatbot_channels
        SET processing = {}
        WHERE channel_id = {};""".format(self.processing, self.channel_id))

    @classmethod
    async def create_channel(cls, channel_id, guild_id, train_in=True, respond_in=True, channel_name=None):
        await db.Pool.execute("""INSERT INTO chatbot_channels 
        VALUES ($1,$2,0,$3,0,null,$4,0, $5);""", channel_id, guild_id, respond_in, train_in, channel_name)
        return await cls.get_channel(channel_id=channel_id, guild_id=guild_id)

    @classmethod
    async def get_channel(cls, **kwargs):
        results = await ChatbotChannel.get_by(**kwargs)

        if results:
            return results[0]
        return None

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ChatbotChannel(channel_id=result.get("channel_id"), guild_id=result.get("guild_id"),
                                 messages=result.get("messages"),
                                 respond_in=result.get("respond_in"), processing=result.get("processing"),
                                 last_message=result.get("last_message"), train_in=result.get("train_in"),
                                 trained_messages=result.get(
                                     "trained_messages"),
                                 channel_name=result.get("channel_name"))
            result_list.append(obj)
        return result_list

    # __versions__ = [version_1]


def setup(bot):
    """Add the levels cog to a bot."""
    bot.add_cog(Chat(bot))
