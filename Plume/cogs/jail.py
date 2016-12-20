import discord
from discord.ext import commands
from .utils import checks
import asyncio
import os
import random
from cogs.utils.dataIO import fileIO, dataIO
from __main__ import send_cmd_help, settings

default = {"DETECT_ACTIF" : False, "DETECT_CHAN" : None, "DETECT_LIST" : None}

class Jail:
    """Collection d'actions de punition."""

    def __init__(self, bot):
        self.bot = bot
        self.prfl = dataIO.load_json("data/puser/prfl.json")
        self.sys = dataIO.load_json("data/jail/sys.json")
        self.vig = dataIO.load_json("data/jail/vig.json")
        self.vigset = dataIO.load_json("data/jail/vigset.json")
        self.scenario = [["Vous tentez de scier les barreaux avec un couteau récupéré à la cantine. (-10%)", 10],
                         ["Vous essayez de creuser le mur fissuré avec une cuillère. (-15%)", 15],
                         ["Vous essayez d'assomer le gardien. (-10%)", 10],
                         ["Vous tentez de faire croire à votre mort (-20%)", 20],
                         ["Vous tentez d'aller à l'infirmerie en vous enfonçant une savonette dans l'anus (-10%)", 10],
                         ["Vous essayez de fuir par les aérations des douches (-15%)", 15],
                         ["Vous arrivez à voler une tenue sale d'un gardien (-5%)", 5],
                         ["Vous étalez différentes purées sur vos vetements pour s'en servir de camouflage (-10%)", 10],
                         ["Vous tentez de fuir avec un complice garde dans la prison (-5%)", 5]] #Rajouter si désiré. Format : ["Message (-x%)", x],

    @commands.group(pass_context=True)
    async def jail(self, ctx):
        """Gestion de la prison."""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            msg = "```"
            for k, v in settings.get_server(ctx.message.server).items():
                msg += str(k) + ": " + str(v) + "\n"
            msg += "```"
            await self.bot.say(msg)

    @jail.command(pass_context=True, hidden=True)
    @checks.mod_or_permissions(ban_members=True)
    async def reset(self, ctx):
        """Reset de Jail"""
        self.sys = {"ROLE" : None, "USERS" : {}, "ITEMS" : {}}
        await self.bot.say("Module *Jail* reset.")
        fileIO("data/jail/sys.json", "save", self.sys)

    @jail.command(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(ban_members=True)
    async def role(self, ctx, *nom):
        """Crée le rôle pour la prison."""
        server = ctx.message.server
        nom = " ".join(nom)
        r = discord.utils.get(ctx.message.server.roles, name=nom)
        if self.sys["ROLE"] is None:
            if nom not in [r.name for r in server.roles]:
                await self.bot.say("Aucun rôle de prison n'est présent sur ce serveur, je vais donc créer le rôle **{}**.".format(nom))
                try:
                    perms = discord.Permissions.none()
                    # Active les permissions voulues (si nécéssaire)
                    await self.bot.create_role(server, name=nom, permissions=perms)
                    await self.bot.say("Rôle crée ! Permissions reglées !\nAssurez-vous que les modérateurs soient au dessus de ce rôle.")
                    self.sys["ROLE"] = nom
                    fileIO("data/jail/sys.json", "save", self.sys)
                    try:
                        for c in server.channels:
                            if c.type.name == 'text':
                                perms = discord.PermissionOverwrite()
                                perms.send_messages = False
                                r = discord.utils.get(ctx.message.server.roles, name=nom)
                                await self.bot.edit_channel_permissions(c, r, perms)
                            await asyncio.sleep(1)
                    except discord.Forbidden:
                        await self.bot.say("Une erreur est apparue.")
                except discord.Forbidden:
                    await self.bot.say("Je ne peux pas créer le rôle.")
            else:
                await self.bot.say("Ce rôle existe déjà. Je vais donc l'enregistrer dans ma base de données.")
                self.sys["ROLE"] = nom
                fileIO("data/jail/sys.json", "save", self.sys)
                await asyncio.sleep(0.50)
                await self.bot.say("Rôle enregistré.")
        else:
            await self.bot.say("Le rôle *{}* est déjà prévu à cet effet !".format(self.sys["ROLE"]))

    @commands.command(name = "p", pass_context=True, no_pm=True)
    @checks.mod_or_permissions(ban_members=True)
    async def jail_add(self, ctx, user: discord.Member, temps: int= 5, jeu: bool = True):
        """Met un utilisateur en prison pendant x minutes en lui permettant ou non de participer au jeu.
        Si l'utilisateur est en prison, il en sera sorti en refaisant la commande.

        Par défaut : Autorisé à jouer / 5 minutes.
        Ajoute 1 de Karma."""
        server = ctx.message.server
        prol = self.sys["ROLE"]
        if user.id not in self.prfl:
            self.prfl[user.id] = {"KARMA" : 0, "NBMSG" : 0, "ID_LIE" : [], "PSEUDO_LIE" : [], "DMSG" : None, "DMSGT" : None, "NOTE" : None}
            fileIO("data/puser/prfl.json", "save", self.prfl)
        if user.id not in self.sys["USERS"]:
            self.sys["USERS"][user.id] = {"NOM" : user.name, "INV" : {}, "JEU" : jeu}
            fileIO("data/jail/sys.json", "save", self.sys)
        if user.id == self.bot.user.id:
            await self.bot.say("Un robot doit protéger son existence tant que cette protection n'entre pas en conflit avec la première ou la deuxième loi d'Asimov. Or, si j'execute votre ordre, vous serez exposé au danger... C'est évident.")
        r = discord.utils.get(ctx.message.server.roles, name=prol)
        if temps >= 1:
            minutes = temps * 60 #On veut un temps en minutes
            if prol not in [r.name for r in user.roles]:
                if self.prfl[user.id]["KARMA"] > 0:
                    await self.bot.whisper("Cet utilisateur possède déjà {}pts de Karma.".format(self.prfl[user.id]["KARMA"]))
                await self.bot.add_roles(user, r)
                if self.prfl[user.id]["KARMA"] < 10:
                    self.prfl[user.id]["KARMA"] += 1
                    fileIO("data/puser/prfl.json", "save", self.prfl)
                    notif = "(+1 Karma)"
                else:
                    notif = "(Karma maximum)"
                await self.bot.say("**{}** est maintenant en prison pour {} minute(s). {}".format(user.name, temps, notif))
                await self.bot.send_message(user, "Tu es maintenant en prison pour {} minute(s). Si tu as une réclamation à faire, va sur le canal *prison* du serveur ou contacte un modérateur.".format(temps))
                await self.bot.server_voice_state(user, mute=True)
                # ^ Mise en prison
                await asyncio.sleep(minutes)
                # v Sortie de prison
                if prol in [r.name for r in user.roles]:
                    await self.bot.remove_roles(user, r)
                    await self.bot.server_voice_state(user, mute=False)
                    await self.bot.say("**{}** à été libéré de la prison.".format(user.name))
                    await self.bot.send_message(user, "Tu es libéré de la prison.")
                else:
                    pass
            else:
                await self.bot.remove_roles(user, r)
                await self.bot.server_voice_state(user, mute=False)
                await self.bot.say("**{}** à été libéré de la prison plus tôt que prévu.".format(user.name))
                await self.bot.send_message(user, "Tu a été libéré de la prison.")
        else:
            await self.bot.say("Le minimum est de une minute.")

    
    @commands.command(name = "pv", pass_context=True, no_pm=True)
    @checks.mod_or_permissions(kick_members=True)
    async def jail_visite(self, ctx, user: discord.Member):
        """Met un utilisateur en prison pendant 5 minutes sans pénalités.

        Pour le sortir plus tôt de prison il suffit d'utiliser la commande classique."""
        server = ctx.message.server
        temps = 5
        prol = self.sys["ROLE"]
        if user.id == self.bot.user.id:
            await self.bot.say("Un robot doit protéger son existence tant que cette protection n'entre pas en conflit avec la première ou la deuxième loi d'Asimov. Or, si j'execute votre ordre, vous serez exposé au danger... C'est évident.")
        r = discord.utils.get(ctx.message.server.roles, name=prol)
        minutes = temps * 60 #On veut un temps en minutes
        if prol not in [r.name for r in user.roles]:
            await self.bot.add_roles(user, r)
            notif = "Aucune pénalité de Karma"
            await self.bot.say("**{}** visite la prison pendant {} minute(s). {}".format(user.name, temps, notif))
            await self.bot.send_message(user, "Tu es maintenant en prison pour {} minute(s) dans le cadre d'une visite. Cette visite ne rajoute pas de points de Karma.".format(temps))
            # ^ Mise en prison
            await asyncio.sleep(minutes)
            # v Sortie de prison
            if prol in [r.name for r in user.roles]:
                await self.bot.remove_roles(user, r)
                await self.bot.say("**{}** à été libéré de la prison [VISITE].".format(user.name))
                await self.bot.send_message(user, "Tu es libéré de la prison [VISITE].")
            else:
                pass
        else:
            await self.bot.say("Utilisez la commande classique de prison pour libérer quelqu'un.")

    @jail.command(pass_context=True)
    @checks.mod_or_permissions(ban_members=True)
    async def clean(self, ctx):
        """Retire tout les prisonniers de la prison."""
        r = discord.utils.get(ctx.message.server.roles, name= self.sys["ROLE"])
        server = ctx.message.server
        msg = "**Libérés:**\n"
        for user in server.members:
            if self.sys["ROLE"] in [r.name for r in user.roles]:
                await self.bot.remove_roles(user, r)
                msg += "{}\n".format(user.name)
            else:
                pass
        await self.bot.say(msg)
        await self.bot.say("L'ensemble des prisonniers ont étés libérées.")

    #-------------- JEU ---------------------

    @jail.command(pass_context=True, hidden=True)
    @checks.mod_or_permissions(ban_members=True)
    async def itemadd(self, ctx, nom: str, pct: int, prix: int):
        """Ajoute un item à la liste des items achetables."""
        if nom not in self.sys["ITEMS"]:
            if pct <= 20:
                self.sys["ITEMS"][nom] = {"NOM" : nom, "BONUS" : pct, "PRIX" : prix}
                fileIO("data/jail/sys.json", "save", self.sys)
                await self.bot.say("Item crée !")
            else:
                await self.bot.say("Le bonus donné doit être inférieur ou égal à 10.")
        else:
            await self.bot.say("Cet item existe déjà.")

    @jail.command(pass_context=True)
    async def infos(self):
        """Affiche des infos sur le jeu de la prison."""
        msg = "**Informations :**\n"
        msg += "Le jeu associé à la prison vous permet, avec de la chance, de fuir la prison.\n"
        msg += "Vous pouvez acheter des items pour augmenter la chance de vous enfuir.\n"
        msg += "La présence d'autres prisonniers avec vous augmente vos chances de vous enfuir.\n"
        msg += "Un scénario est choisi au hasard et vous enlève un pourcentage de s'enfuir en fonction de la difficulté de la tâche.\n"
        msg += "\n"
        msg += "Le rôle de prison sur ce serveur est **{}**.".format(self.sys["ROLE"])
        msg += "\n"
        msg += "*Un commentaire ou une amélioration à apporter ? Contactez Acrown#4424 en MP.*"
        await self.bot.whisper(msg)

    @jail.command(pass_context=True)
    async def buy(self, ctx, item: str = None):
        """Achat d'un item pour augmenter ses chances de sortir de prison.

        Si aucun item n'est spécifié, renvoie la liste des items disponibles."""
        author = ctx.message.author
        prol = self.sys["ROLE"]
        bank = self.bot.get_cog('Economy').bank
        r = discord.utils.get(ctx.message.server.roles, name=prol)
        if prol in [r.name for r in author.roles]:
            if author.id in self.sys["USERS"]:
                if self.sys["USERS"][author.id]["JEU"]:
                    if len(self.sys["USERS"][author.id]["INV"]) < 3:
                        if item is None:
                            msg = ""
                            for item in self.sys["ITEMS"]:
                                msg += "**{}** | *+{}%* | *{}*§\n".format(self.sys["ITEMS"][item]["NOM"], self.sys["ITEMS"][item]["BONUS"],self.sys["ITEMS"][item]["PRIX"])
                            else:
                                await self.bot.say(msg)
                        else:
                            if item in self.sys["ITEMS"]:
                                prix = self.sys["ITEMS"][item]["PRIX"]
                                if bank.account_exists(author):
                                    if bank.can_spend(author, prix):
                                        bank.withdraw_credits(author, prix)
                                        self.sys["USERS"][author.id]["INV"][item] = self.sys["ITEMS"][item]
                                        fileIO("data/jail/sys.json", "save", self.sys)
                                        await self.bot.say("Vous venez d'acheter *{}* pour {}§ ! *Utilisation unique*".format(item, self.sys["ITEMS"][item]["PRIX"]))
                                    else:
                                        await self.bot.say("Vous n'avez pas assez d'argent")
                                else:
                                    await self.bot.say("Vous n'avez pas de compte bancaire (WTF ?)")
                            else:
                                await self.bot.say("Cet item n'existe pas.")
                    else:
                        await self.bot.say("Vous déjà 3 items.")
                else:
                    await self.bot.say("Vous n'êtes pas autorisé à jouer.")
            else:
                await self.bot.say("Vous n'êtes pas dans ma base de données. C'est étrange. Bref, je vais vous y inscrire, réessayez plus tard.")
                self.sys["USERS"][author.id] = {"NOM" : user.name, "INV" : {}, "JEU" : True}
                fileIO("data/jail/sys.json", "save", self.sys)
                await asyncio.sleep(1)
                await self.bot.whisper("Vous êtes maintenant inscrit à ma base de données.")
        else:
            await self.bot.say("Vous n'êtes pas en prison, pas besoin de s'échapper !")

    @jail.command(pass_context=True)
    async def escape(self, ctx):
        """Pour tenter de s'échapper de la prison..."""
        prol = self.sys["ROLE"]
        r = discord.utils.get(ctx.message.server.roles, name=prol)
        user = ctx.message.author
        server = ctx.message.server
        chance = 10
        msg = "**Vous utilisez :**\n"
        msgpr = ""
        bank = self.bot.get_cog('Economy').bank
        if prol in [r.name for r in user.roles]:
            if user.id in self.sys["USERS"]:
                if self.sys["USERS"][user.id]["JEU"]:
                    await self.bot.say("**{} va tenter de s'échapper.**".format(user.name))
                    await asyncio.sleep(0.75)
                    await self.bot.say("Vous rassemblez vos affaires...")
                    await asyncio.sleep(3)
                    await self.bot.say("Vous êtes prêt. Allons-y !")
                    await asyncio.sleep(1.50)
                    n = 0
                    for member in server.members:
                        if member.id != user.id:
                            if prol in [r.name for r in member.roles]:
                                chance += 5
                                msgpr += "Vous avez l'aide de *{}* ! (+5% de chance)\n".format(member.name)
                            else:
                                pass
                        else:
                            pass
                    if len(self.sys["USERS"][user.id]["INV"]) > 0:
                        for item in self.sys["USERS"][user.id]["INV"]:
                            chance += self.sys["USERS"][user.id]["INV"][item]["BONUS"]
                            msg += "*{}* +{}%\n".format(self.sys["USERS"][user.id]["INV"][item]["NOM"], self.sys["USERS"][user.id]["INV"][item]["BONUS"])
                    else:
                        msg += "*Vous n'avez aucun item*"

                    if msgpr != "":
                        await self.bot.say(msgpr)
                    else:
                        await self.bot.say("Personne n'est présent pour vous aider...")

                    await asyncio.sleep(2)
                    await self.bot.say(msg)
                    await asyncio.sleep(3)
                    scenar = random.choice(self.scenario)
                    await self.bot.say(scenar[0])
                    chance = chance - scenar[1]
                    await asyncio.sleep(2)

                    rand = random.randint(1, 100)
                    if rand <= chance:
                        await self.bot.say("**C'est un succès !**")
                        await asyncio.sleep(0.5)
                        await self.bot.say("Vous êtes maintenant un homme libre ! *Le rôle va vous être retiré d'ici quelques secondes...*")
                        await asyncio.sleep(3)
                        self.sys["USERS"][user.id]["INV"] = {}
                        await self.bot.remove_roles(user, r)
                        await self.bot.say("**{}** à été libéré de la prison. (Gagnant du jeu)".format(user.name))
                        await self.bot.server_voice_state(user, mute=False)
                        await self.bot.send_message(user, "Tu es libéré de la prison. Bravo !")
                        fileIO("data/jail/sys.json", "save", self.sys)
                    else:
                        await self.bot.say("**Echec !**")
                        await asyncio.sleep(0.5)
                        await self.bot.say("Vous restez en prison, on vous retire l'ensemble de vos affaires et vous perdez 150§.")
                        if bank.account_exists(user):
                            if bank.can_spend(user, 150):
                                bank.withdraw_credits(user, 150)
                            else:
                                await asyncio.sleep(0.5)
                                await self.bot.say("Mais vous avez de la chance, vous êtes trop pauvre.")
                        else:
                            await self.bot.say("Heureusement pour vous, vous n'avez pas de compte bancaire...")
                        self.sys["USERS"][user.id]["INV"] = {}
                        fileIO("data/jail/sys.json", "save", self.sys)
                else:
                    await self.bot.say("Vous n'êtes pas autorisé à jouer.")
            else:
                await self.bot.say("Vous n'êtes pas dans ma base de données. C'est étrange. Bref, je vais vous y inscrire, réessayez plus tard.")
                self.sys["USERS"][user.id] = {"NOM" : user.name, "INV" : {}, "JEU" : True}
                fileIO("data/jail/sys.json", "save", self.sys)
                await asyncio.sleep(1)
                await self.bot.whisper("Vous êtes maintenant inscrit à ma base de données.")
        else:
            await self.bot.say("Vous n'êtes pas prisonnier !")

    #------------- MODPLUS ----------------------------------------------------------

    @commands.group(pass_context=True)
    async def vigil(self, ctx):
        """Gestion de Vigilance."""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            msg = "```"
            for k, v in settings.get_server(ctx.message.server).items():
                msg += str(k) + ": " + str(v) + "\n"
            msg += "```"
            await self.bot.say(msg)
            
    @vigil.command(pass_context=True)
    @checks.mod_or_permissions(ban_members=True)
    async def crt(self, ctx):
        """Ajoute des utilisateurs à Vigilance en créant une liste.

        Cette commande crée une liste des mentionnés et renvoie un ID de modération."""
        ment = ctx.message.mentions
        server = ctx.message.server
        author = ctx.message.author
        nb = ["0","1","2","3","4","5","6","7","8","9"]
        id = self.gen_code()
        msg = "__**Ajoutés à la liste n°** *{}*__\n".format(id)
        if id not in self.vig:
            self.vig[id] = {"ID" : id,"LISTE" : [], "CREATEUR" : author.id}
            con = ctx.message.content
            el = con.split()
            if ment != []:
                for user in ment:
                    self.vig[id]["LISTE"].append(user.id)
                    msg += "**{}** ajouté\n".format(user.name)
                    fileIO("data/jail/vig.json", "save", self.vig)
            else:
                for e in el: #Recherche d'ID
                    if set(nb) & set(e) != set():
                        user = server.get_member(e)
                        self.vig[id]["LISTE"].append(user.id)
                        msg += "**{}** ajouté\n".format(user.name)
                        fileIO("data/jail/vig.json", "save", self.vig)
                    else:
                        pass
            if msg != "**Ajoutés à la liste n°{}**\n".format(id):
                await self.bot.whisper(msg)
                name = id[-4:]
                await self.bot.say("Liste **{}** créé.".format(name))
            else:
                await self.bot.whisper("Vous n'avez spécifié personne dans votre liste.")
        else:
            await self.bot.say("La liste crée existe déjà, réesayez plus tard.")
            
    @vigil.command(pass_context=True)
    @checks.mod_or_permissions(ban_members=True)
    async def ajt(self, ctx, liste, user : discord.Member):
        """Permet d'ajouter un utilisateur à une liste existante."""
        liste = liste.upper()
        for id in self.vig:
            if liste in id:
                nom = id[-4:]
                if user.id not in self.vig[id]["LISTE"]:
                    self.vig[id]["LISTE"].append(user.id)
                    await self.bot.whisper("**{}** ajouté à la liste **{}**".format(user.name, nom))
                    fileIO("data/jail/vig.json", "save", self.vig)
                    return
                else:
                    await self.bot.whisper("Utilisateur déjà présent.")
            else:
                pass
        else:
            await self.bot.whisper("Aucune liste ne porte ce nom.")

    @vigil.command(pass_context=True)
    @checks.mod_or_permissions(ban_members=True)
    async def rem(self, ctx, liste):
        """Supprime une liste si vous en êtes l'auteur."""
        liste = liste.upper()
        for id in self.vig:
            if liste in id:
                nom = id[-4:]
                if self.vig[id]["CREATEUR"] == ctx.message.author.id:
                    del self.vig[id]
                    await self.bot.say("Liste **{}** supprimée.".format(nom))
                    fileIO("data/jail/vig.json", "save", self.vig)
                    return
                else:
                    await self.bot.whisper("Vous n'êtes pas le créateur de cette liste.")
            else:
                pass
        else:
            await self.bot.whisper("Aucune liste ne porte ce nom.")

    @vigil.command(pass_context=True)
    @checks.mod_or_permissions(ban_members=True)
    async def lst(self, ctx, liste = None):
        """Permet d'afficher les utilisateurs présents dans une liste.

        Si aucune liste n'est spécifiée, affiche les listes disponibles."""
        server = ctx.message.server
        if liste != None:
            liste = liste.upper()
            for id in self.vig:
                if liste in id:
                    nom = id[-4:]
                    if self.vig[id]["CREATEUR"] == ctx.message.author.id:
                        msg = "**Liste {} (__{}__)**\n".format(nom, id)
                        for u in self.vig[id]["LISTE"]:
                            user = server.get_member(u)
                            msg += "*{}*\n".format(user.name)
                        await self.bot.whisper(msg)
                        return
                    else:
                        msg = "**Liste {}**\n".format(nom)
                        for u in self.vig[id]["LISTE"]:
                            user = server.get_member(u)
                            msg += "*{}*\n".format(user.name)
                        await self.bot.whisper(msg)
                        return
                else:
                    pass
            else:
                await self.bot.whisper("Aucune liste de ce nom existe.")
        else:
            msg = "**Listes disponibles:**\n"
            for id in self.vig:
                nom = id[-4:]
                creator = self.vig[id]["CREATEUR"]
                creator = server.get_member(creator)
                msg += "*{}* | **{}**\n".format(nom, creator.name)
            if msg != "**Listes disponibles:**\n":
                await self.bot.whisper(msg)
            else:
                await self.bot.whisper("Aucune liste à afficher.")

    @vigil.command(pass_context=True)
    @checks.mod_or_permissions(administrator=True)
    async def wpe(self, ctx, liste = None):
        """Efface une/des liste(s) Vigilance en outre-passant les droits (Admin)."""
        if liste != None:
            for id in self.vig:
                if liste in id:
                    nom = id[-4:]
                    del self.vig[id]
                    await self.bot.say("Liste **{}** supprimée.".format(nom))
                    fileIO("data/jail/vig.json", "save", self.vig)
                    return
                else:
                    pass
            else:
                await self.bot.whisper("Aucune liste de ce nom existe.")
        else:
            self.vig = {}
            fileIO("data/jail/vig.json", "save", self.vig)
            await self.bot.say("Vidé entièrement.")

    @vigil.command(pass_context=True)
    @checks.mod_or_permissions(administrator=True)
    async def sec(self, ctx, liste):
        """Permet de voir le code de sécurité lié à une liste et les utilisateurs qui sont dedans."""
        server = ctx.message.server
        for id in self.vig:
            if liste in id:
                nom = id[-4:]
                msg = "**Liste {} (__{}__)**\n".format(nom, id)
                for u in self.vig[id]["LISTE"]:
                    user = server.get_member(u)
                    msg += "*{}*\n".format(user.name)
                await self.bot.whisper(msg)
                return
            else:
                pass
        else:
            await self.bot.whisper("Aucune liste de ce nom existe.")

    @vigil.command(pass_context=True)
    @checks.mod_or_permissions(ban_members=True)
    async def mod(self, ctx, listec, temps: int= 5):
        """Permet la modération (Prison) pour une liste entière.

        Nécéssite le code de sécurité pour être executée."""
        listec = listec.upper()
        server = ctx.message.server
        prol = self.sys["ROLE"]
        if listec in self.vig:
            for uid in self.vig[listec]["LISTE"]:
                user = server.get_member(uid)
                r = discord.utils.get(ctx.message.server.roles, name=prol)
                if prol not in [r.name for r in user.roles]:
                    await self.bot.add_roles(user, r)
                    await self.bot.say("**{}** est maintenant en prison par **Vigilance**.".format(user.name))
                    await self.bot.send_message(user, "Tu es maintenant en prison par **Vigilance**. Si tu as une réclamation à faire, va sur le canal *prison* du serveur ou contacte un modérateur.")
                    await self.bot.server_voice_state(user, mute=True)
                else:
                    await self.bot.remove_roles(user, r)
                    await self.bot.server_voice_state(user, mute=False)
                    await self.bot.say("**{}** à été libéré de la prison plus tôt que prévu.".format(user.name))
                    await self.bot.send_message(user, "Tu a été libéré de la prison.")
            else:
                await self.bot.say("**Terminé.**")
        else:
            for id in self.vig:
                if listec in id:
                    nom = id[-4:]
                    await self.bot.whisper("Il me faut le code de sécurité précédant '#'")
                    return
            else:
                await self.bot.whisper("Cette liste n'existe pas.")

    @vigil.command(pass_context=True)
    @checks.mod_or_permissions(ban_members=True)
    async def aut(self, ctx):
        """Permet d'activer l'attribution automatique de liste aux nouveaux arrivants.

        Crée la liste si non existante."""
        id = self.gen_code()
        if self.vigset["DETECT_ACTIF"] is False:
            if id not in self.vig:
                self.vig[id] = {"ID" : id,"LISTE" : []}
                nom = id[-4:]
                self.vigset["DETECT_LIST"] = id
                self.vigset["DETECT_CHAN"] = ctx.message.channel.id
                self.vigset["DETECT_ACTIF"] = True
                await self.bot.whisper("Liste **{}** crée.".format(id))
                await self.bot.say("**Activé pour la liste {}** Les logs seront envoyés sur ce channel.".format(nom))
                fileIO("data/jail/vig.json", "save", self.vig)
                fileIO("data/jail/vigset.json", "save", self.vigset)
            else:
                await self.bot.whisper("Impossible, réesayez plus tard.")
        else:
            self.vigset["DETECT_ACTIF"] = False
            fileIO("data/jail/vig.json", "save", self.vig)
            fileIO("data/jail/vigset.json", "save", self.vigset)
            await self.bot.say("**Désactivé**")

    async def detect(self, user):
        if self.vigset["DETECT_ACTIF"] is True:
            id = self.vigset["DETECT_LIST"]
            chan = self.vigset["DETECT_CHAN"]
            chan = user.server.get_channel(chan)
            nom = id[-4:]
            if user.id not in self.vig[id]["LISTE"]:
                self.vig[id]["LISTE"].append(user.id)
                await self.bot.send_message(chan, "[AUTO] **{}** ajouté à la liste **{}**".format(user.name, nom))
                fileIO("data/jail/vig.json", "save", self.vig)
            else:
                pass

    # SYSTEM -----------------------------------------------------------------------

    def gen_code(self):
        let = ["A","B","C","D","E","F","G","H","K","L","M","N","O","P","W","X","Y","Z"]
        rand1 = str(random.randint(10000,99999))
        rand2 = random.sample(let, 3)
        code = rand1 + "#" 
        for e in rand2:
            code += e
        return code
        
def check_folders():
    folders = ("data", "data/jail/")
    for folder in folders:
        if not os.path.exists(folder):
            print("Création du fichier " + folder)
            os.makedirs(folder)

def check_files():
    if not os.path.isfile("data/jail/sys.json"):
        print("Je crée la base de données de Jail...")
        fileIO("data/jail/sys.json", "save", {})

    if not os.path.isfile("data/jail/vig.json"):
        print("Je crée la base de données Vigilance...")
        fileIO("data/jail/vig.json", "save", {})

    if not os.path.isfile("data/jail/vigset.json"):
        print("Je crée la base de données Vigilance Réglages...")
        fileIO("data/jail/vigset.json", "save", default)

def setup(bot):
    check_folders()
    check_files()
    n = Jail(bot)
    bot.add_listener(n.detect, "on_member_join")
    bot.add_cog(n)
