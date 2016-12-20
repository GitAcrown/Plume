import asyncio
import os
import time
import sys
import logging
import logging.handlers
import shutil
import traceback
import datetime

try:
    assert sys.version_info >= (3, 5)
    from discord.ext import commands
    import discord
except ImportError:
    print("Discord.py n'est pas installé.\n")
    sys.exit()
except AssertionError:
    print("Issou nécéssite Python 3.5 ou supérieur pour fonctionner.")
    sys.exit()

from cogs.utils.settings import Settings
from cogs.utils.dataIO import dataIO
from cogs.utils.chat_formatting import inline
from collections import Counter

#
# Ambre - Un bot discord modulaire adapté partiellement de Red by Twentysix26
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Les modules marqués d'un "Exclusif" sont des modules crées pour ce bot.
# Les modules marqués d'un "Optimisé pour TdK" ou "Op" sont des modules réalisés pour le serveur Taverne des Kheys.
#

description = "Ambre - Un bot Discord modulaire"


class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        self.counter = Counter()
        self.uptime = datetime.datetime.now()
        self._message_modifiers = []
        super().__init__(*args, **kwargs)

    async def send_message(self, *args, **kwargs):
        if self._message_modifiers:
            if "content" in kwargs:
                pass
            elif len(args) == 2:
                args = list(args)
                kwargs["content"] = args.pop()
            else:
                return await super().send_message(*args, **kwargs)

            content = kwargs['content']
            for m in self._message_modifiers:
                try:
                    content = str(m(content))
                except:   # Faulty modifiers should not
                    pass  # break send_message
            kwargs['content'] = content

        return await super().send_message(*args, **kwargs)

    def add_message_modifier(self, func):
        """
        Adds a message modifier to the bot

        A message modifier is a callable that accepts a message's
        content as the first positional argument.
        Before a message gets sent, func will get called with
        the message's content as the only argument. The message's
        content will then be modified to be the func's return
        value.
        Exceptions thrown by the callable will be catched and
        silenced.
        """
        if not callable(func):
            raise TypeError("The message modifier function "
                            "must be a callable.")

        self._message_modifiers.append(func)

    def remove_message_modifier(self, func):
        """Removes a message modifier from the bot"""
        if func not in self._message_modifiers:
            raise RuntimeError("Function not present in the message "
                               "modifiers.")

        self._message_modifiers.remove(func)

    def clear_message_modifiers(self):
        """Removes all message modifiers from the bot"""
        self._message_modifiers.clear()

    async def send_cmd_help(self, ctx):
        if ctx.invoked_subcommand:
            pages = bot.formatter.format_help_for(ctx, ctx.invoked_subcommand)
            for page in pages:
                await bot.send_message(ctx.message.channel, page)
        else:
            pages = bot.formatter.format_help_for(ctx, ctx.command)
            for page in pages:
                await bot.send_message(ctx.message.channel, page)

    def user_allowed(self, message):
        author = message.author

        if author.bot or author == self.user:
            return False

        mod = self.get_cog('Mod')

        if mod is not None:
            if settings.owner == author.id:
                return True
            if not message.channel.is_private:
                server = message.server
                names = (settings.get_server_admin(
                    server), settings.get_server_mod(server))
                results = map(
                    lambda name: discord.utils.get(author.roles, name=name),
                    names)
                for r in results:
                    if r is not None:
                        return True

            if author.id in mod.blacklist_list:
                return False

            if mod.whitelist_list:
                if author.id not in mod.whitelist_list:
                    return False

            if not message.channel.is_private:
                if message.server.id in mod.ignore_list["SERVERS"]:
                    return False

                if message.channel.id in mod.ignore_list["CHANNELS"]:
                    return False
            return True
        else:
            return True


class Formatter(commands.HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _add_subcommands_to_page(self, max_width, commands):
        for name, command in sorted(commands, key=lambda t: t[0]):
            if name in command.aliases:
                # skip aliases
                continue

            entry = '  {0:<{width}} {1}'.format(name, command.short_doc,
                                                width=max_width)
            shortened = self.shorten(entry)
            self._paginator.add_line(shortened)


formatter = Formatter(show_check_failure=False)

bot = Bot(command_prefix=["_"], formatter=formatter,
          description=description, pm_help=None)

send_cmd_help = bot.send_cmd_help  # Backwards
user_allowed = bot.user_allowed    # compatibility

settings = Settings()


@bot.event
async def on_ready():
    owner_cog = bot.get_cog('Owner')
    total_cogs = len(owner_cog._list_cogs())
    users = len(set(bot.get_all_members()))
    servers = len(bot.servers)
    channels = len([c for c in bot.get_all_channels()])
    if settings.login_type == "token" and settings.owner == "id_here":
        await set_bot_owner()
    print('~~~~~~')
    print("{} est en ligne.".format(bot.user.name))
    print('~~~~~~')
    print("Stats:")
    print("{} serveurs".format(servers))
    print("{} channels".format(channels))
    print("{} utilisateurs".format(users))
    print("\n{}/{} modules activés pour {} commandes".format(
        len(bot.cogs), total_cogs, len(bot.commands)))
    prefix_label = "Prefixes:" if len(bot.command_prefix) > 1 else "Prefix:"
    print("{} {}\n".format(prefix_label, " ".join(bot.command_prefix)))
    if settings.login_type == "token":
        print("~~~~~~")
        print("URL d'invitation:")
        url = await get_oauth_url()
        bot.oauth_url = url
        print(url)
        print("~~~~~~")
    await bot.get_cog('Owner').disable_commands()


@bot.event
async def on_command(command, ctx):
    bot.counter["processed_commands"] += 1


@bot.event
async def on_message(message):
    bot.counter["messages_read"] += 1
    if user_allowed(message):
        await bot.process_commands(message)


@bot.event
async def on_command_error(error, ctx):
    channel = ctx.message.channel
    if isinstance(error, commands.MissingRequiredArgument):
        await send_cmd_help(ctx)
    elif isinstance(error, commands.BadArgument):
        await send_cmd_help(ctx)
    elif isinstance(error, commands.DisabledCommand):
        await bot.send_message(channel, "Commande désactivée.")
    elif isinstance(error, commands.CommandInvokeError):
        logger.exception("Exception dans '{}'".format(
            ctx.command.qualified_name), exc_info=error.original)
        oneliner = "Erreur dans la commande '{}' - {}: {}".format(
            ctx.command.qualified_name, type(error.original).__name__,
            str(error.original))
        await ctx.bot.send_message(channel, inline(oneliner))
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CheckFailure):
        pass
    elif isinstance(error, commands.NoPrivateMessage):
        await bot.send_message(channel, "Cette commande n'est pas disponible en MP.")
    else:
        logger.exception(type(error).__name__, exc_info=error)

async def get_oauth_url():
    try:
        data = await bot.application_info()
    except Exception as e:
        return "Impossible de retrouver l'URL: {}".format(e)
    return discord.utils.oauth_url(data.id)

async def set_bot_owner():
    try:
        data = await bot.application_info()
        settings.owner = data.owner.id
    except Exception as e:
        print("Impossible de retrouver l'ID de propriétaire: {}".format(e))
        return
    print("{} a été reconnu en tant que Propriétaire.".format(data.owner.name))


def check_folders():
    folders = ("data", "data/red", "cogs", "cogs/utils")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def check_configs():
    if settings.bot_settings == settings.default_settings:
        print("Issou - Réglages\n")
        print("Si ce n'est pas encore fait, vous devez créer un compte BOT:\n"
              "https://twentysix26.github.io/Red-Docs/red_guide_bot_accounts/"
              "#creating-a-new-bot-account")
        print("et obtenir le token comme décrit dans ce tutoriel.")
        print("\nInsérez le token du bot:")

        choice = input("> ")

        if "@" not in choice and len(choice) >= 50:  # Assuming token
            settings.login_type = "token"
            settings.email = choice
        elif "@" in choice:
            settings.login_type = "email"
            settings.email = choice
            settings.password = input("\nPassword> ")
        else:
            os.remove('data/red/settings.json')
            input("Invalide, redémarrez le programme et réessayez.")
            exit(1)

        print("\nChoisissez un préfixe.\n"
              "Il est possible de mettre plusieurs caractères.\n"
              "Vous pourrez le changer plus tard\nPréfixe:")
        confirmation = False
        while confirmation is False:
            new_prefix = ensure_reply("\nPrefix> ").strip()
            print("\nÊtes-vous sûr de vouloir {0} comme préfixe ?\nYou "
                  "Les commandes seront sous cette forme: {0}help"
                  "\nTapez 'yes' pour confirmer, 'no' pour le changer".format(new_prefix))
            confirmation = get_answer()

        settings.prefixes = [new_prefix]
        if settings.login_type == "email":
            print("\nUne fois le bot configuré, utilisez"
                  "'{}set owner' *dans le tchat Discord*\nPour vous mettre vous-même propriétaire.\n"
                  "Press enter to continue".format(new_prefix))
            settings.owner = input("") # Shh, they will never know it's here
            if settings.owner == "":
                settings.owner = "id_here"
            if not settings.owner.isdigit() or len(settings.owner) < 17:
                if settings.owner != "id_here":
                    print("\nl'ID entré est invalide.\nUtilisez '{}set owner' surle tchat pour vous mettre propriétaire".format(new_prefix))
                settings.owner = "id_here"
        else:
            settings.owner = "id_here"

        print("\nRôle d'Administrateur ?")
        settings.default_admin = input("\nAdmin role> ")
        if settings.default_admin == "":
            settings.default_admin = "Transistor"

        print("\nRôle de Modérateur ?")
        settings.default_mod = input("\nModerator role> ")
        if settings.default_mod == "":
            settings.default_mod = "Process"

        print("\nLa configuration est terminée. Cette fenêtre passe en Lecture Seulement.\nN'oubliez pas 'set owner' pour vous mettre propriétaire.\nUtilisez 'help' pour avoir les commandes disponibles.")
        input("\n")

    if not os.path.isfile("data/red/cogs.json"):
        print("Creating new cogs.json...")
        dataIO.save_json("data/red/cogs.json", {})

def set_logger():
    global logger
    logger = logging.getLogger("discord")
    logger.setLevel(logging.WARNING)
    handler = logging.FileHandler(
        filename='data/red/discord.log', encoding='utf-8', mode='a')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d: '
        '%(message)s',
        datefmt="[%d/%m/%Y %H:%M]"))
    logger.addHandler(handler)

    logger = logging.getLogger("red")
    logger.setLevel(logging.INFO)

    red_format = logging.Formatter(
        '%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d: '
        '%(message)s',
        datefmt="[%d/%m/%Y %H:%M]")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(red_format)
    stdout_handler.setLevel(logging.INFO)

    fhandler = logging.handlers.RotatingFileHandler(
        filename='data/red/red.log', encoding='utf-8', mode='a',
        maxBytes=10**7, backupCount=5)
    fhandler.setFormatter(red_format)

    logger.addHandler(fhandler)
    logger.addHandler(stdout_handler)

def ensure_reply(msg):
    choice = ""
    while choice == "":
        choice = input(msg)
    return choice

def get_answer():
    choices = ("yes", "y", "no", "n")
    c = ""
    while c not in choices:
        c = input(">").lower()
    if c.startswith("y"):
        return True
    else:
        return False

def set_cog(cog, value):
    data = dataIO.load_json("data/red/cogs.json")
    data[cog] = value
    dataIO.save_json("data/red/cogs.json", data)

def load_cogs():
    no_prompt = "--no-prompt" in sys.argv[1:]

    try:
        registry = dataIO.load_json("data/red/cogs.json")
    except:
        registry = {}

    bot.load_extension('cogs.owner')
    owner_cog = bot.get_cog('Owner')
    if owner_cog is None:
        print("Hey ! J'en ai besoin du module Owner pour fonctionner ! S'il-te-plait, remet-le !")
        exit(1)

    failed = []
    extensions = owner_cog._list_cogs()
    for extension in extensions:
        if extension.lower() == "cogs.owner":
            continue
        in_reg = extension in registry
        if in_reg is False:
            if no_prompt is True:
                registry[extension] = False
                continue
            print("\nNouvelle extension détectée: {}".format(extension))
            print("Charger ?(y/n)")
            if not get_answer():
                registry[extension] = False
                continue
            registry[extension] = True
        if not registry[extension]:
            continue
        try:
            owner_cog._load_cog(extension)
        except Exception as e:
            print("{}: {}".format(e.__class__.__name__, str(e)))
            logger.exception(e)
            failed.append(extension)
            registry[extension] = False

    if extensions:
        dataIO.save_json("data/red/cogs.json", registry)

    if failed:
        print("\nChargement impossible: ", end="")
        for m in failed:
            print(m + " ", end="")
        print("\n")

    return owner_cog


def main():
    global settings

    check_folders()
    check_configs()
    set_logger()
    owner_cog = load_cogs()
    if settings.prefixes != []:
        bot.command_prefix = settings.prefixes
    else:
        print("Aucun préfixe réglé, par défaut !")
        bot.command_prefix = ["!"]
        if settings.owner != "id_here":
            print("utilisez !set prefix pour le changer.")
        else:
            print("Changez le préfixe avec !set prefix lorsque vous serez propriétaire.")
    if settings.owner == "id_here" and settings.login_type == "email":
        print("Aucun propriétaire réglé. Utilisez '{}set owner' pour le faire".format(bot.command_prefix[0]))
    else:
        owner_cog.owner.hidden = True  # Hides the set owner command from help
    print("~~ Connection... ~~")
    if os.name == "nt" and os.path.isfile("update.bat"):
        print("Gardez le bot à jour en lançant régulièrement "
              "update.bat")
    else:
        print("Gardez le bot à jour en utilisant régulièrement: git pull")
        print("et: pip3 install -U git+https://github.com/Rapptz/"
              "discord.py@master#egg=discord.py[voice]")
    print("Serveur EK: https://discord.me/ekheysn")
    if settings.login_type == "token":
        yield from bot.login(settings.email)
    else:
        yield from bot.login(settings.email, settings.password)
    yield from bot.connect()

if __name__ == '__main__':
    error = False
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except discord.LoginFailure:
        error = True
        logger.error(traceback.format_exc())
        choice = input("Login indisponible. "
            "Si le bot fonctionnait normalement, l'erreur vient de chez Discord"
            "\nSi c'est le cas, faîtes Entrer "
            "et réessayez plus tard.\nSinon, tapez 'reset' pour "
            "repasser le bot en configuration usine.\n> ")
        if choice.strip() == "reset":
            shutil.copy('data/red/settings.json',
                        'data/red/settings-{}.bak'.format(int(time.time())))
            os.remove('data/red/settings.json')
    except KeyboardInterrupt:
        loop.run_until_complete(bot.logout())
    except:
        error = True
        logger.error(traceback.format_exc())
        loop.run_until_complete(bot.logout())
    finally:
        loop.close()
        if error:
            exit(1)
