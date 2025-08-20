import discord
from discord.ext import commands, voice_recv
import env

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True  # Necesario para acceder a miembros del canal
bot = commands.Bot(command_prefix="$", intents=intents)


# -------- Métodos --------
async def join_channel(guild_id: int, channel_id: int):
    """Hace que el bot entre a un canal de voz específico"""
    guild = bot.get_guild(guild_id)
    channel = guild.get_channel(channel_id)

    if channel and isinstance(channel, discord.VoiceChannel):
        vc: voice_recv.VoiceRecvClient = await channel.connect(cls=voice_recv.VoiceRecvClient)
        return f"Entré al canal {channel.name}"
    return "No se encontró el canal o no es de voz."


async def leave_channel(guild_id: int):
    """Hace que el bot salga del canal de voz en el servidor"""
    guild = bot.get_guild(guild_id)
    if guild and guild.voice_client:
        await guild.voice_client.disconnect()
        return "Me salí del canal de voz."
    return "No estaba en ningún canal de voz."


async def send_channel_message(guild_id: int, channel_id: int, text: str):
    """Envía un mensaje de texto a un canal"""
    guild = bot.get_guild(guild_id)
    channel = guild.get_channel(channel_id)

    if channel and isinstance(channel, discord.TextChannel):
        await channel.send(text)
        return f"Mensaje enviado a #{channel.name}"
    return "No se encontró el canal o no es de texto."


async def send_private_message(guild_id: int, member_id: int, text: str):
    """Envía un mensaje privado (DM) a un usuario del servidor"""
    guild = bot.get_guild(guild_id)
    member = guild.get_member(member_id)

    if member:
        try:
            await member.send(text)
            return f"Mensaje privado enviado a {member.display_name}"
        except discord.Forbidden:
            return f"No pude enviar mensaje a {member.display_name} (DMs cerrados)."
    return "No se encontró al usuario."


# -------- Run --------
bot.run(env.TOKEN)
