import discord
from discord.ext import commands
from .utils.dataIO import dataIO
from .utils import checks
from __main__ import send_cmd_help, settings
from collections import deque, defaultdict
from cogs.utils.chat_formatting import escape_mass_mentions, box
import os
import re
import logging
import asyncio

default_settings = {
    "ban_mention_spam" : False,
    "delete_repeats"   : False,
    "mod-log"          : None
                   }


class ModError(Exception):
    pass


class UnauthorizedCaseEdit(ModError):
    pass


class CaseMessageNotFound(ModError):
    pass


class NoModLogChannel(ModError):
    pass


class Mod:
    """Moderation tools."""

    def __init__(self, bot):
        self.bot = bot
        self.whitelist_list = dataIO.load_json("data/mod/whitelist.json")
        self.blacklist_list = dataIO.load_json("data/mod/blacklist.json")
        self.ignore_list = dataIO.load_json("data/mod/ignorelist.json")
        self.filter = dataIO.load_json("data/mod/filter.json")
        self.past_names = dataIO.load_json("data/mod/past_names.json")
        self.past_nicknames = dataIO.load_json("data/mod/past_nicknames.json")
        settings = dataIO.load_json("data/mod/settings.json")
        self.settings = defaultdict(lambda: default_settings.copy(), settings)
        self.cache = defaultdict(lambda: deque(maxlen=3))
        self.cases = dataIO.load_json("data/mod/modlog.json")
        self.last_case = defaultdict(dict)
        self._tmp_banned_cache = []
        perms_cache = dataIO.load_json("data/mod/perms_cache.json")
        self._perms_cache = defaultdict(dict, perms_cache)

    @commands.group(pass_context=True, no_pm=True)
    @checks.serverowner_or_permissions(administrator=True)
    async def modset(self, ctx):
        """Gestion des paramètres de modération serveur."""
        if ctx.invoked_subcommand is None:
            server = ctx.message.server
            await send_cmd_help(ctx)
            roles = settings.get_server(server).copy()
            _settings = {**self.settings[server.id], **roles}
            msg = ("Role Admin: {ADMIN_ROLE}\n"
                   "Role Modération: {MOD_ROLE}\n"
                   "Logs de modération: {mod-log}\n"
                   "Supprimer les répetitions: {delete_repeats}\n"
                   "Bannir les spam de mention: {ban_mention_spam}\n"
                   "".format(**_settings))
            await self.bot.say(box(msg))

    @modset.command(name="adminrole", pass_context=True, no_pm=True)
    async def _modset_adminrole(self, ctx, role_name: str):
        """Change le rôle d'administrateur."""
        server = ctx.message.server
        settings.set_server_admin(server, role_name)
        await self.bot.say("Rôle d'Admin: '{}'".format(role_name))

    @modset.command(name="modrole", pass_context=True, no_pm=True)
    async def _modset_modrole(self, ctx, role_name: str):
        """Change le rôle de modérateur."""
        server = ctx.message.server
        settings.set_server_mod(server, role_name)
        await self.bot.say("Rôle Modérateur '{}'".format(role_name))

    @modset.command(pass_context=True, no_pm=True)
    async def modlog(self, ctx, channel : discord.Channel=None):
        """Change le channel où est publié les logs de modération

        Laisser le channel vide désactive cette fonction"""
        server = ctx.message.server
        if channel:
            self.settings[server.id]["mod-log"] = channel.id
            await self.bot.say("Logs envoyés sur {}"
                               "".format(channel.mention))
        else:
            if self.settings[server.id]["mod-log"] is None:
                await send_cmd_help(ctx)
                return
            self.settings[server.id]["mod-log"] = None
            await self.bot.say("Logs désactivés.")
        dataIO.save_json("data/mod/settings.json", self.settings)

    @modset.command(pass_context=True, no_pm=True)
    async def banmentionspam(self, ctx, max_mentions : int=False):
        """Active le ban automatique pour la mention de X personnes différentes dans le même message

        Valeures acceptées: 5 ou supérieur"""
        server = ctx.message.server
        if max_mentions:
            if max_mentions < 5:
                max_mentions = 5
            self.settings[server.id]["ban_mention_spam"] = max_mentions
            await self.bot.say("Autoban pour spam de mention activé. "
                               "Les personnes mentionnant {} ou plus de personnes"
                               " dans un seul message seront bannis."
                               "".format(max_mentions))
        else:
            if self.settings[server.id]["ban_mention_spam"] is False:
                await send_cmd_help(ctx)
                return
            self.settings[server.id]["ban_mention_spam"] = False
            await self.bot.say("Autoban désactivé.")
        dataIO.save_json("data/mod/settings.json", self.settings)

    @modset.command(pass_context=True, no_pm=True)
    async def deleterepeats(self, ctx):
        """Active la suppression automatique des doubles messages."""
        server = ctx.message.server
        if not self.settings[server.id]["delete_repeats"]:
            self.settings[server.id]["delete_repeats"] = True
            await self.bot.say("Les messages se répétant au moins 3 fois seront supprimés")
        else:
            self.settings[server.id]["delete_repeats"] = False
            await self.bot.say("Messages répétés ignorés.")
        dataIO.save_json("data/mod/settings.json", self.settings)

    @modset.command(pass_context=True, no_pm=True)
    async def resetcases(self, ctx):
        """Reset la DB des logs"""
        server = ctx.message.server
        self.cases[server.id] = {}
        dataIO.save_json("data/mod/modlog.json", self.cases)
        await self.bot.say("Reset effectué.")

    @commands.command(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(kick_members=True)
    async def kick(self, ctx, user: discord.Member):
        """Kick l'utilisateur."""
        author = ctx.message.author
        server = author.server
        try:
            await self.bot.kick(user)
            logger.info("{}({}) a kick {}({})".format(
                author.name, author.id, user.name, user.id))
            await self.new_case(server,
                                action="Kick \N{WOMANS BOOTS}",
                                mod=author,
                                user=user)
            await self.bot.say("Fait.")
        except discord.errors.Forbidden:
            await self.bot.say("Je ne suis pas autorisé à le faire.")
        except Exception as e:
            print(e)

    @commands.command(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(ban_members=True)
    async def ban(self, ctx, user: discord.Member, days: int=0):
        """Ban un utilisateur et supprime X jours de messages.

        Par défaut 0 jours."""
        author = ctx.message.author
        server = author.server
        if days < 0 or days > 7:
            await self.bot.say("Les jours doivent être compris entre 0 et 7.")
            return
        try:
            self._tmp_banned_cache.append(user)
            await self.bot.ban(user, days)
            logger.info("{}({}) banned {}({}), deleting {} days worth of messages".format(
                author.name, author.id, user.name, user.id, str(days)))
            await self.new_case(server,
                                action="Ban \N{HAMMER}",
                                mod=author,
                                user=user)
            await self.bot.say("Fait.")
        except discord.errors.Forbidden:
            await self.bot.say("Je ne suis pas autorisé à le faire.")
        except Exception as e:
            print(e)
        finally:
            await asyncio.sleep(1)
            self._tmp_banned_cache.remove(user)

    @commands.command(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(ban_members=True)
    async def softban(self, ctx, user: discord.Member):
        """Kick un utilisateur à travers un ban furtif. Supprime 1 jour de message."""
        server = ctx.message.server
        channel = ctx.message.channel
        can_ban = channel.permissions_for(server.me).ban_members
        author = ctx.message.author
        try:
            invite = await self.bot.create_invite(server, max_age=3600*24)
            invite = "\nInvitation: " + invite
        except:
            invite = ""
        if can_ban:
            try:
                try:  # We don't want blocked DMs preventing us from banning
                    msg = await self.bot.send_message(user, "Tu as été banni puis "
                              "débanni de façon à pouvoir reset totalement ta présence sur le serveur.\n"
                              "Tu peux maintenant rejoindre à nouveau le serveur.{}".format(invite))
                except:
                    pass
                self._tmp_banned_cache.append(user)
                await self.bot.ban(user, 1)
                logger.info("{}({}) softbanned {}({}), deleting 1 day worth "
                    "of messages".format(author.name, author.id, user.name,
                     user.id))
                await self.new_case(server,
                                    action="Softban \N{DASH SYMBOL} \N{HAMMER}",
                                    mod=author,
                                    user=user)
                await self.bot.unban(server, user)
                await self.bot.say("Fait.")
            except discord.errors.Forbidden:
                await self.bot.say("Je n'ai pas les autorisations pour le faire.")
                await self.bot.delete_message(msg)
            except Exception as e:
                print(e)
            finally:
                await asyncio.sleep(1)
                self._tmp_banned_cache.remove(user)
        else:
            await self.bot.say("Je ne suis pas autorisé à le faire")

    @commands.command(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(manage_nicknames=True)
    async def rename(self, ctx, user : discord.Member, *, nickname=""):
        """Change le pseudo d'un utilisateur."""
        nickname = nickname.strip()
        if nickname == "":
            nickname = None
        try:
            await self.bot.change_nickname(user, nickname)
            await self.bot.say("Fait.")
        except discord.Forbidden:
            await self.bot.say("Je n'ai pas pu le faire parce que mes autorisations ne me le permettent pas.")

    @commands.group(pass_context=True, no_pm=True, invoke_without_command=True)
    @checks.mod_or_permissions(administrator=True)
    async def mute(self, ctx, user : discord.Member):
        """Mute les utilisateurs"""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.channel_mute, user=user)

    @mute.command(name="channel", pass_context=True, no_pm=True)
    async def channel_mute(self, ctx, user : discord.Member):
        """Mute les utilisateur dans ce channel."""
        channel = ctx.message.channel
        overwrites = channel.overwrites_for(user)
        if overwrites.send_messages is False:
            await self.bot.say("Cet utilisateur ne peut pas envoyer de message sur ce channel.")
            return
        self._perms_cache[user.id][channel.id] = overwrites.send_messages
        overwrites.send_messages = False
        try:
            await self.bot.edit_channel_permissions(channel, user, overwrites)
        except discord.Forbidden:
            await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
        else:
            dataIO.save_json("data/mod/perms_cache.json", self._perms_cache)
            await self.bot.say("Utilisateur mute.")

    @mute.command(name="server", pass_context=True, no_pm=True)
    async def server_mute(self, ctx, user : discord.Member):
        """Mute un utilisateur dans le serveur entier."""
        server = ctx.message.server
        register = {}
        for channel in server.channels:
            if channel.type != discord.ChannelType.text:
                continue
            overwrites = channel.overwrites_for(user)
            if overwrites.send_messages is False:
                continue
            register[channel.id] = overwrites.send_messages
            overwrites.send_messages = False
            try:
                await self.bot.edit_channel_permissions(channel, user,
                                                        overwrites)
            except discord.Forbidden:
                await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
                return
            else:
                await asyncio.sleep(0.1)
        if not register:
            await self.bot.say("Cet utilisateur est déjà mute sur tout les channels.")
            return
        self._perms_cache[user.id] = register
        dataIO.save_json("data/mod/perms_cache.json", self._perms_cache)
        await self.bot.say("Utilisateur mute.")

    @commands.group(pass_context=True, no_pm=True, invoke_without_command=True)
    @checks.mod_or_permissions(administrator=True)
    async def unmute(self, ctx, user : discord.Member):
        """Enlève le mute d'un utilisateur."""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.channel_unmute, user=user)

    @unmute.command(name="channel", pass_context=True, no_pm=True)
    async def channel_unmute(self, ctx, user : discord.Member):
        """Enlève le mute de ce channel"""
        channel = ctx.message.channel
        overwrites = channel.overwrites_for(user)
        if overwrites.send_messages:
            await self.bot.say("Cet utilisateur n'est pas mute.")
            return
        if user.id in self._perms_cache:
            old_value = self._perms_cache[user.id].get(channel.id, None)
        else:
            old_value = None
        overwrites.send_messages = old_value
        is_empty = self.are_overwrites_empty(overwrites)
        try:
            if not is_empty:
                await self.bot.edit_channel_permissions(channel, user,
                                                        overwrites)
            else:
                await self.bot.delete_channel_permissions(channel, user)
        except discord.Forbidden:
            await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
        else:
            try:
                del self._perms_cache[user.id][channel.id]
            except KeyError:
                pass
            if user.id in self._perms_cache and not self._perms_cache[user.id]:
                del self._perms_cache[user.id] #cleanup
            dataIO.save_json("data/mod/perms_cache.json", self._perms_cache)
            await self.bot.say("Utilisateur libéré")

    @unmute.command(name="server", pass_context=True, no_pm=True)
    async def server_unmute(self, ctx, user : discord.Member):
        """Demute sur le serveur entier"""
        server = ctx.message.server
        if user.id not in self._perms_cache:
            await self.bot.say("L'utilisateur n'a pas été mute avec la commande liée.")
            return
        for channel in server.channels:
            if channel.type != discord.ChannelType.text:
                continue
            if channel.id not in self._perms_cache[user.id]:
                continue
            value = self._perms_cache[user.id].get(channel.id)
            overwrites = channel.overwrites_for(user)
            if overwrites.send_messages is False:
                overwrites.send_messages = value
                is_empty = self.are_overwrites_empty(overwrites)
                try:
                    if not is_empty:
                        await self.bot.edit_channel_permissions(channel, user,
                                                                overwrites)
                    else:
                        await self.bot.delete_channel_permissions(channel, user)
                except discord.Forbidden:
                    await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
                    return
                else:
                    del self._perms_cache[user.id][channel.id]
                    await asyncio.sleep(0.1)
        if user.id in self._perms_cache and not self._perms_cache[user.id]:
            del self._perms_cache[user.id] #cleanup
        dataIO.save_json("data/mod/perms_cache.json", self._perms_cache)
        await self.bot.say("Utilisateur démute.")

    @commands.group(pass_context=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def cleanup(self, ctx):
        """Suppression de messages."""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @cleanup.command(pass_context=True, no_pm=True)
    async def text(self, ctx, text: str, number: int):
        """Suppression des x derniers messages contenant le texte

        Utilisez des guillemets pour le texte."""

        channel = ctx.message.channel
        author = ctx.message.author
        server = author.server
        is_bot = self.bot.user.bot
        has_permissions = channel.permissions_for(server.me).manage_messages

        def check(m):
            if text in m.content:
                return True
            elif m == ctx.message:
                return True
            else:
                return False

        to_delete = [ctx.message]

        if not has_permissions:
            await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
            return

        tries_left = 5
        tmp = ctx.message

        while tries_left and len(to_delete) - 1 < number:
            async for message in self.bot.logs_from(channel, limit=100,
                                                    before=tmp):
                if len(to_delete) - 1 < number and check(message):
                    to_delete.append(message)
                tmp = message
            tries_left -= 1

        logger.info("{}({}) deleted {} messages "
                    " containing '{}' in channel {}".format(author.name,
                    author.id, len(to_delete), text, channel.id))

        if is_bot:
            await self.mass_purge(to_delete)
        else:
            await self.slow_deletion(to_delete)

    @cleanup.command(pass_context=True, no_pm=True)
    async def user(self, ctx, user: discord.Member, number: int):
        """Supprimer les x derniers messages d'un utilisateur."""

        channel = ctx.message.channel
        author = ctx.message.author
        server = author.server
        is_bot = self.bot.user.bot
        has_permissions = channel.permissions_for(server.me).manage_messages

        def check(m):
            if m.author == user:
                return True
            elif m == ctx.message:
                return True
            else:
                return False

        to_delete = [ctx.message]

        if not has_permissions:
            await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
            return

        tries_left = 5
        tmp = ctx.message

        while tries_left and len(to_delete) - 1 < number:
            async for message in self.bot.logs_from(channel, limit=100,
                                                    before=tmp):
                if len(to_delete) - 1 < number and check(message):
                    to_delete.append(message)
                tmp = message
            tries_left -= 1

        logger.info("{}({}) deleted {} messages "
                    " made by {}({}) in channel {}"
                    "".format(author.name, author.id, len(to_delete),
                              user.name, user.id, channel.name))

        if is_bot:
            await self.mass_purge(to_delete)
        else:
            await self.slow_deletion(to_delete)

    @cleanup.command(pass_context=True, no_pm=True)
    async def after(self, ctx, message_id : int):
        """Supprime l'ensemble des messages après un certain message (ID)
        """

        channel = ctx.message.channel
        author = ctx.message.author
        server = channel.server
        is_bot = self.bot.user.bot
        has_permissions = channel.permissions_for(server.me).manage_messages

        if not is_bot:
            await self.bot.say("Cette commande ne peut être réalisée que par les vrais bots.")
            return

        to_delete = []

        after = await self.bot.get_message(channel, message_id)

        if not has_permissions:
            await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
            return
        elif not after:
            await self.bot.say("Message introuvable.")
            return

        async for message in self.bot.logs_from(channel, limit=2000,
                                                after=after):
            to_delete.append(message)

        logger.info("{}({}) deleted {} messages in channel {}"
                    "".format(author.name, author.id,
                              len(to_delete), channel.name))

        await self.mass_purge(to_delete)

    @cleanup.command(pass_context=True, no_pm=True)
    async def messages(self, ctx, number: int):
        """Supprime les x derniers messages"""

        channel = ctx.message.channel
        author = ctx.message.author
        server = author.server
        is_bot = self.bot.user.bot
        has_permissions = channel.permissions_for(server.me).manage_messages

        to_delete = []

        if not has_permissions:
            await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
            return

        async for message in self.bot.logs_from(channel, limit=number+1):
            to_delete.append(message)

        logger.info("{}({}) deleted {} messages in channel {}"
                    "".format(author.name, author.id,
                              number, channel.name))

        if is_bot:
            await self.mass_purge(to_delete)
        else:
            await self.slow_deletion(to_delete)

    @cleanup.command(pass_context=True, no_pm=True, name='bot')
    async def cleanup_bot(self, ctx, number: int):
        """Supprime les messages de commandes et les messages du bot"""

        channel = ctx.message.channel
        author = ctx.message.author
        server = channel.server
        is_bot = self.bot.user.bot
        has_permissions = channel.permissions_for(server.me).manage_messages

        prefixes = self.bot.command_prefix
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        elif callable(prefixes):
            if asyncio.iscoroutine(prefixes):
                await self.bot.say('Préfixes de coroutine non-implémentés pour le moment.')
                return
            prefixes = prefixes(self.bot, ctx.message)

        # In case some idiot sets a null prefix
        if '' in prefixes:
            prefixes.pop('')

        def check(m):
            if m.author.id == self.bot.user.id:
                return True
            elif m == ctx.message:
                return True
            p = discord.utils.find(m.content.startswith, prefixes)
            if p and len(p) > 0:
                return m.content[len(p):].startswith(tuple(self.bot.commands))
            return False

        to_delete = [ctx.message]

        if not has_permissions:
            await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
            return

        tries_left = 5
        tmp = ctx.message

        while tries_left and len(to_delete) - 1 < number:
            async for message in self.bot.logs_from(channel, limit=100,
                                                    before=tmp):
                if len(to_delete) - 1 < number and check(message):
                    to_delete.append(message)
                tmp = message
            tries_left -= 1

        logger.info("{}({}) deleted {} "
                    " command messages in channel {}"
                    "".format(author.name, author.id, len(to_delete),
                              channel.name))

        if is_bot:
            await self.mass_purge(to_delete)
        else:
            await self.slow_deletion(to_delete)

    @cleanup.command(pass_context=True, name='self')
    async def cleanup_self(self, ctx, number: int, match_pattern: str = None):
        """Supprime les messages du bot.

        Le troisième champ permet d'utiliser regex
        """
        channel = ctx.message.channel
        author = ctx.message.author
        is_bot = self.bot.user.bot

        # You can always delete your own messages, this is needed to purge
        can_mass_purge = False
        if type(author) is discord.Member:
            me = channel.server.me
            can_mass_purge = channel.permissions_for(me).manage_messages

        use_re = (match_pattern and match_pattern.startswith('r(') and
                  match_pattern.endswith(')'))

        if use_re:
            match_pattern = match_pattern[1:]  # strip 'r'
            match_re = re.compile(match_pattern)

            def content_match(c):
                return bool(match_re.match(c))
        elif match_pattern:
            def content_match(c):
                return match_pattern in c
        else:
            def content_match(_):
                return True

        def check(m):
            if m.author.id != self.bot.user.id:
                return False
            elif content_match(m.content):
                return True
            return False

        to_delete = []
        # Selfbot convenience, delete trigger message
        if author == self.bot.user:
            to_delete.append(ctx.message)
            number += 1

        tries_left = 5
        tmp = ctx.message

        while tries_left and len(to_delete) < number:
            async for message in self.bot.logs_from(channel, limit=100,
                                                    before=tmp):
                if len(to_delete) < number and check(message):
                    to_delete.append(message)
                tmp = message
            tries_left -= 1

        if channel.name:
            channel_name = 'channel ' + channel.name
        else:
            channel_name = str(channel)

        logger.info("{}({}) deleted {} messages "
                    "sent by the bot in {}"
                    "".format(author.name, author.id, len(to_delete),
                              channel_name))

        if is_bot and can_mass_purge:
            await self.mass_purge(to_delete)
        else:
            await self.slow_deletion(to_delete)

    @commands.command(pass_context=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def raison(self, ctx, case, *, reason : str=""):
        """Permet de rajouter une raison à un Log de modération

        Par défaut votre dernier log assigné à vous-même."""
        author = ctx.message.author
        server = author.server
        try:
            case = int(case)
            if not reason:
                await send_cmd_help(ctx)
                return
        except:
            if reason:
                reason = "{} {}".format(case, reason)
            else:
                reason = case
            case = self.last_case[server.id].get(author.id, None)
            if case is None:
                await send_cmd_help(ctx)
                return
        try:
            await self.update_case(server, case=case, mod=author,
                                   reason=reason)
        except UnauthorizedCaseEdit:
            await self.bot.say("Ce n'est pas à vous.")
        except KeyError:
            await self.bot.say("Il n'existe pas.")
        except NoModLogChannel:
            await self.bot.say("Aucun log défini.")
        except CaseMessageNotFound:
            await self.bot.say("Je ne retrouve pas ce log...")
        else:
            await self.bot.say("Log #{} mis à jour.".format(case))

    @commands.group(pass_context=True)
    @checks.is_owner()
    async def blacklist(self, ctx):
        """Interdit un utilisateur d'utiliser le bot"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @blacklist.command(name="add")
    async def _blacklist_add(self, user: discord.Member):
        """Ajoute un utilisateur."""
        if user.id not in self.blacklist_list:
            self.blacklist_list.append(user.id)
            dataIO.save_json("data/mod/blacklist.json", self.blacklist_list)
            await self.bot.say("Rajouté.")
        else:
            await self.bot.say("Déjà blacklisté.")

    @blacklist.command(name="remove")
    async def _blacklist_remove(self, user: discord.Member):
        """Enlève un utilisateur."""
        if user.id in self.blacklist_list:
            self.blacklist_list.remove(user.id)
            dataIO.save_json("data/mod/blacklist.json", self.blacklist_list)
            await self.bot.say("Retiré.")
        else:
            await self.bot.say("N'est pas présent dans la blacklist.")

    @blacklist.command(name="clear")
    async def _blacklist_clear(self):
        """Reset la blacklist"""
        self.blacklist_list = []
        dataIO.save_json("data/mod/blacklist.json", self.blacklist_list)
        await self.bot.say("Vidée.")

    @commands.group(pass_context=True)
    @checks.is_owner()
    async def whitelist(self, ctx):
        """Autorise un utilisateur à utiliser le bot. Supprime l'autorisation aux autres."""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @whitelist.command(name="add")
    async def _whitelist_add(self, user: discord.Member):
        """Ajoute un utilisateur."""
        if user.id not in self.whitelist_list:
            if not self.whitelist_list:
                msg = " Whitelist ouverte, l'ensemble des utilisateurs sont maintenant blacklistés."
            else:
                msg = ""
            self.whitelist_list.append(user.id)
            dataIO.save_json("data/mod/whitelist.json", self.whitelist_list)
            await self.bot.say("Ajouté." + msg)
        else:
            await self.bot.say("Utilisateur déjà présent.")

    @whitelist.command(name="remove")
    async def _whitelist_remove(self, user: discord.Member):
        """Retire un utilisateur"""
        if user.id in self.whitelist_list:
            self.whitelist_list.remove(user.id)
            dataIO.save_json("data/mod/whitelist.json", self.whitelist_list)
            await self.bot.say("Retiré.")
        else:
            await self.bot.say("Utilisateur non présent dans la liste.")

    @whitelist.command(name="clear")
    async def _whitelist_clear(self):
        """Reset la whitelist"""
        self.whitelist_list = []
        dataIO.save_json("data/mod/whitelist.json", self.whitelist_list)
        await self.bot.say("Vidée.")

    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_channels=True)
    async def ignore(self, ctx):
        """Ignore un serveur ou un channel"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            await self.bot.say(self.count_ignored())

    @ignore.command(name="channel", pass_context=True)
    async def ignore_channel(self, ctx, channel: discord.Channel=None):
        """Ignore un chan"""
        current_ch = ctx.message.channel
        if not channel:
            if current_ch.id not in self.ignore_list["CHANNELS"]:
                self.ignore_list["CHANNELS"].append(current_ch.id)
                dataIO.save_json("data/mod/ignorelist.json", self.ignore_list)
                await self.bot.say("Chan ignoré.")
            else:
                await self.bot.say("Chan déjà ignoré.")
        else:
            if channel.id not in self.ignore_list["CHANNELS"]:
                self.ignore_list["CHANNELS"].append(channel.id)
                dataIO.save_json("data/mod/ignorelist.json", self.ignore_list)
                await self.bot.say("Chan ajouté.")
            else:
                await self.bot.say("Chan déjà ajouté.")

    @ignore.command(name="server", pass_context=True)
    async def ignore_server(self, ctx):
        """Ignore ce serveur"""
        server = ctx.message.server
        if server.id not in self.ignore_list["SERVERS"]:
            self.ignore_list["SERVERS"].append(server.id)
            dataIO.save_json("data/mod/ignorelist.json", self.ignore_list)
            await self.bot.say("Serveur ignoré.")
        else:
            await self.bot.say("Serveur déjà ignoré.")

    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_channels=True)
    async def unignore(self, ctx):
        """Retire un channel ou un serveur des ignorés."""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            await self.bot.say(self.count_ignored())

    @unignore.command(name="channel", pass_context=True)
    async def unignore_channel(self, ctx, channel: discord.Channel=None):
        """Retire un chan des ignorés"""
        current_ch = ctx.message.channel
        if not channel:
            if current_ch.id in self.ignore_list["CHANNELS"]:
                self.ignore_list["CHANNELS"].remove(current_ch.id)
                dataIO.save_json("data/mod/ignorelist.json", self.ignore_list)
                await self.bot.say("Chan plus ignoré.")
            else:
                await self.bot.say("Ce chan n'était pas ignoré.")
        else:
            if channel.id in self.ignore_list["CHANNELS"]:
                self.ignore_list["CHANNELS"].remove(channel.id)
                dataIO.save_json("data/mod/ignorelist.json", self.ignore_list)
                await self.bot.say("Chan plus ignoré.")
            else:
                await self.bot.say("Ce chan n'était pas ignoré.")

    @unignore.command(name="server", pass_context=True)
    async def unignore_server(self, ctx):
        """Retire un utilisateur des ignorés"""
        server = ctx.message.server
        if server.id in self.ignore_list["SERVERS"]:
            self.ignore_list["SERVERS"].remove(server.id)
            dataIO.save_json("data/mod/ignorelist.json", self.ignore_list)
            await self.bot.say("Ce serveur n'est plus ignoré.")
        else:
            await self.bot.say("Serveur non ignoré.")

    def count_ignored(self):
        msg = "```Ignorés:\n"
        msg += str(len(self.ignore_list["CHANNELS"])) + " channels\n"
        msg += str(len(self.ignore_list["SERVERS"])) + " serveurs\n```\n"
        return msg

    @commands.group(name="filter", pass_context=True, no_pm=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def _filter(self, ctx):
        """Rajoute un mot/phrase dans le filtre."""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            server = ctx.message.server
            author = ctx.message.author
            msg = ""
            if server.id in self.filter.keys():
                if self.filter[server.id] != []:
                    word_list = self.filter[server.id]
                    for w in word_list:
                        msg += '"' + w + '" '
                    await self.bot.send_message(author, "Chaines filtrés: " + msg)

    @_filter.command(name="add", pass_context=True)
    async def filter_add(self, ctx, *words: str):
        """Ajoute une chaine de caractères au filtre."""
        if words == ():
            await send_cmd_help(ctx)
            return
        server = ctx.message.server
        added = 0
        if server.id not in self.filter.keys():
            self.filter[server.id] = []
        for w in words:
            if w.lower() not in self.filter[server.id] and w != "":
                self.filter[server.id].append(w.lower())
                added += 1
        if added:
            dataIO.save_json("data/mod/filter.json", self.filter)
            await self.bot.say("Ajouté.")
        else:
            await self.bot.say("Déjà filtrés.")

    @_filter.command(name="remove", pass_context=True)
    async def filter_remove(self, ctx, *words: str):
        """Retire un filtre"""
        if words == ():
            await send_cmd_help(ctx)
            return
        server = ctx.message.server
        removed = 0
        if server.id not in self.filter.keys():
            await self.bot.say("Aucun mot n'est filtré..")
            return
        for w in words:
            if w.lower() in self.filter[server.id]:
                self.filter[server.id].remove(w.lower())
                removed += 1
        if removed:
            dataIO.save_json("data/mod/filter.json", self.filter)
            await self.bot.say("Mots retirés du filtre.")
        else:
            await self.bot.say("Ces mots n'étaient pas filtrés.")

    @commands.group(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(manage_roles=True)
    async def editrole(self, ctx):
        """Gestion des paramètres de rôle"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @editrole.command(aliases=["color"], pass_context=True)
    async def colour(self, ctx, role: discord.Role, value: discord.Colour):
        """Change la couleur (Hex) d'un rôle."""
        author = ctx.message.author
        try:
            await self.bot.edit_role(ctx.message.server, role, color=value)
            logger.info("{}({}) changed the colour of role '{}'".format(
                author.name, author.id, role.name))
            await self.bot.say("Fait.")
        except discord.Forbidden:
            await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
        except Exception as e:
            print(e)
            await self.bot.say("Un truc s'est mal passé...")

    @editrole.command(name="name", pass_context=True)
    @checks.admin_or_permissions(administrator=True)
    async def edit_role_name(self, ctx, role: discord.Role, name: str):
        """Change le nom d'un rôle"""
        if name == "":
            await self.bot.say("Le nom ne peut pas être vide.")
            return
        try:
            author = ctx.message.author
            old_name = role.name  # probably not necessary?
            await self.bot.edit_role(ctx.message.server, role, name=name)
            logger.info("{}({}) changed the name of role '{}' to '{}'".format(
                author.name, author.id, old_name, name))
            await self.bot.say("Fait.")
        except discord.Forbidden:
            await self.bot.say("Impossible de le faire. Mon rôle ne le permet pas.")
        except Exception as e:
            print(e)
            await self.bot.say("Quelque chose s'est mal passé.")

    @commands.command()
    async def names(self, user : discord.Member):
        """Change le nom d'un utilisateur."""
        server = user.server
        names = self.past_names[user.id] if user.id in self.past_names else None
        try:
            nicks = self.past_nicknames[server.id][user.id]
            nicks = [escape_mass_mentions(nick) for nick in nicks]
        except:
            nicks = None
        msg = ""
        if names:
            names = [escape_mass_mentions(name) for name in names]
            msg += "**20 derniers pseudos**:\n"
            msg += ", ".join(names)
        if nicks:
            if msg:
                msg += "\n\n"
            msg += "**20 derniers surnoms**:\n"
            msg += ", ".join(nicks)
        if msg:
            await self.bot.say(msg)
        else:
            await self.bot.say("Cet utilisateur est clean...")

    async def mass_purge(self, messages):
        while messages:
            if len(messages) > 1:
                await self.bot.delete_messages(messages[:100])
                messages = messages[100:]
            else:
                await self.bot.delete_message(messages[0])
                messages = []
            await asyncio.sleep(1.5)

    async def slow_deletion(self, messages):
        for message in messages:
            try:
                await self.bot.delete_message(message)
            except:
                pass

    def is_mod_or_superior(self, message):
        user = message.author
        server = message.server
        admin_role = settings.get_server_admin(server)
        mod_role = settings.get_server_mod(server)

        if user.id == settings.owner:
            return True
        elif discord.utils.get(user.roles, name=admin_role):
            return True
        elif discord.utils.get(user.roles, name=mod_role):
            return True
        else:
            return False

    async def new_case(self, server, *, action, mod=None, user, reason=None):
        channel = server.get_channel(self.settings[server.id]["mod-log"])
        if channel is None:
            return

        if server.id in self.cases:
            case_n = len(self.cases[server.id]) + 1
        else:
            case_n = 1

        case = {"case"         : case_n,
                "action"       : action,
                "user"         : user.name,
                "user_id"      : user.id,
                "reason"       : reason,
                "moderator"    : mod.name if mod is not None else None,
                "moderator_id" : mod.id if mod is not None else None}

        if server.id not in self.cases:
            self.cases[server.id] = {}

        tmp = case.copy()
        if case["reason"] is None:
            tmp["reason"] = "Tapez [p]raison {} <raison> pour en changer ".format(case_n)
        if case["moderator"] is None:
            tmp["moderator"] = "Inconnu"
            tmp["moderator_id"] = "Le modérateur n'assume pas"

        case_msg = ("**Action #{case}** | {action}\n"
                    "**Utilisateur:** {user} ({user_id})\n"
                    "**Moderateur:** {moderator} ({moderator_id})\n"
                    "**Raison:** {reason}"
                    "".format(**tmp))

        try:
            msg = await self.bot.send_message(channel, case_msg)
        except:
            msg = None

        case["message"] = msg.id if msg is not None else None

        self.cases[server.id][str(case_n)] = case

        if mod:
            self.last_case[server.id][mod.id] = case_n

        dataIO.save_json("data/mod/modlog.json", self.cases)

    async def update_case(self, server, *, case, mod, reason):
        channel = server.get_channel(self.settings[server.id]["mod-log"])
        if channel is None:
            raise NoModLogChannel()

        case = str(case)
        case = self.cases[server.id][case]

        if case["moderator_id"] is not None:
            if case["moderator_id"] != mod.id:
                raise UnauthorizedCaseEdit()

        case["reason"] = reason
        case["moderator"] = mod.name
        case["moderator_id"] = mod.id

        case_msg = ("**Action #{case}** | {action}\n"
                    "**utilisateur:** {user} ({user_id})\n"
                    "**Moderateur:** {moderator} ({moderator_id})\n"
                    "**Raison:** {reason}"
                    "".format(**case))

        dataIO.save_json("data/mod/modlog.json", self.cases)

        msg = await self.bot.get_message(channel, case["message"])
        if msg:
            await self.bot.edit_message(msg, case_msg)
        else:
            raise CaseMessageNotFound()

    async def check_filter(self, message):
        server = message.server
        if server.id in self.filter.keys():
            for w in self.filter[server.id]:
                if w in message.content.lower():
                    try:
                        await self.bot.delete_message(message)
                        logger.info("Message supprimé {}."
                                    "Filtré: {}"
                                    "".format(server.id, w))
                        return True
                    except:
                        pass
        return False

    async def check_duplicates(self, message):
        server = message.server
        author = message.author
        if server.id not in self.settings:
            return False
        if self.settings[server.id]["delete_repeats"]:
            self.cache[author].append(message)
            msgs = self.cache[author]
            if len(msgs) == 3 and \
                    msgs[0].content == msgs[1].content == msgs[2].content:
                if any([m.attachments for m in msgs]):
                    return False
                try:
                    await self.bot.delete_message(message)
                    return True
                except:
                    pass
        return False

    async def check_mention_spam(self, message):
        server = message.server
        author = message.author
        if server.id not in self.settings:
            return False
        if self.settings[server.id]["ban_mention_spam"]:
            max_mentions = self.settings[server.id]["ban_mention_spam"]
            mentions = set(message.mentions)
            if len(mentions) >= max_mentions:
                try:
                    self._tmp_banned_cache.append(author)
                    await self.bot.ban(author, 1)
                except:
                    logger.info("Impossible de ban pour spam {}".format(server.id))
                else:
                    await self.new_case(server,
                                        action="Ban \N{HAMMER}",
                                        mod=server.me,
                                        user=author,
                                        reason="Mention spam (Autoban)")
                    return True
                finally:
                    await asyncio.sleep(1)
                    self._tmp_banned_cache.remove(author)
        return False

    async def on_message(self, message):
        if message.channel.is_private or self.bot.user == message.author \
         or not isinstance(message.author, discord.Member):
            return
        elif self.is_mod_or_superior(message):
            return
        deleted = await self.check_filter(message)
        if not deleted:
            deleted = await self.check_duplicates(message)
        if not deleted:
            deleted = await self.check_mention_spam(message)

    async def on_member_ban(self, member):
        if member not in self._tmp_banned_cache:
            server = member.server
            await self.new_case(server,
                                user=member,
                                action="Ban \N{HAMMER}")

    async def check_names(self, before, after):
        if before.name != after.name:
            if before.id not in self.past_names.keys():
                self.past_names[before.id] = [after.name]
            else:
                if after.name not in self.past_names[before.id]:
                    names = deque(self.past_names[before.id], maxlen=20)
                    names.append(after.name)
                    self.past_names[before.id] = list(names)
            dataIO.save_json("data/mod/past_names.json", self.past_names)

        if before.nick != after.nick and after.nick is not None:
            server = before.server
            if server.id not in self.past_nicknames:
                self.past_nicknames[server.id] = {}
            if before.id in self.past_nicknames[server.id]:
                nicks = deque(self.past_nicknames[server.id][before.id],
                              maxlen=20)
            else:
                nicks = []
            if after.nick not in nicks:
                nicks.append(after.nick)
                self.past_nicknames[server.id][before.id] = list(nicks)
                dataIO.save_json("data/mod/past_nicknames.json",
                                 self.past_nicknames)

    def are_overwrites_empty(self, overwrites):
        """There is currently no cleaner way to check if a
        PermissionOverwrite object is empty"""
        original = [p for p in iter(overwrites)]
        empty = [p for p in iter(discord.PermissionOverwrite())]
        return original == empty


def check_folders():
    folders = ("data", "data/mod/")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def check_files():
    ignore_list = {"SERVERS": [], "CHANNELS": []}

    files = {
        "blacklist.json"      : [],
        "whitelist.json"      : [],
        "ignorelist.json"     : ignore_list,
        "filter.json"         : {},
        "past_names.json"     : {},
        "past_nicknames.json" : {},
        "settings.json"       : {},
        "modlog.json"         : {},
        "perms_cache.json"    : {}
    }

    for filename, value in files.items():
        if not os.path.isfile("data/mod/{}".format(filename)):
            print("Creating empty {}".format(filename))
            dataIO.save_json("data/mod/{}".format(filename), value)


def setup(bot):
    global logger
    check_folders()
    check_files()
    logger = logging.getLogger("mod")
    # Prevents the logger from being loaded again in case of module reload
    if logger.level == 0:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(
            filename='data/mod/mod.log', encoding='utf-8', mode='a')
        handler.setFormatter(
            logging.Formatter('%(asctime)s %(message)s', datefmt="[%d/%m/%Y %H:%M]"))
        logger.addHandler(handler)
    n = Mod(bot)
    bot.add_listener(n.check_names, "on_member_update")
    bot.add_cog(n)
