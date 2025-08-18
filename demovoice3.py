# -*- coding: utf-8 -*-
from typing import Optional, Union

import discord
from discord import VoiceClient, Member, User
from discord.ext import commands, voice_recv
from discord.ext.voice_recv import AudioSink, VoiceData

import env

discord.opus._load_default()

intents = discord.Intents.default()
intents.message_content = True  # NECESARIO para leer comandos de texto
intents.voice_states = True  # NECESARIO para voz

bot = commands.Bot(command_prefix="$", intents=intents)
import discord
from discord.ext import voice_recv
from discord.ext.voice_recv import AudioSink


class LoggingSink(AudioSink):
	"""Un AudioSink que solo escucha eventos y los imprime en consola."""

	def wants_opus(self) -> bool:
		# ¿Quieres recibir los datos en Opus o en PCM?
		# True = opus packets (sin decodificar)
		# False = PCM (decodificado con opuslib)
		return False

	def write(self, user, data: VoiceData):
		# Aquí podrías guardar el audio en archivo o procesarlo
		# Para este sink de logs, lo dejamos vacío
		pass

	def cleanup(self):
		# Libera recursos (archivos, buffers, etc.)
		# Como este sink solo loggea, no hace nada
		pass

	@AudioSink.listener()
	def on_voice_member_connect(self, member: discord.Member):
		print(f"[EVENT CONNECT] {member.name} se conectó al canal de voz")

	@AudioSink.listener()
	def on_voice_member_disconnect(self, member: discord.Member, ssrc: int | None):
		print(f"[EVENT DISCONNECT] {member.name} se desconectó (ssrc={ssrc})")

	@AudioSink.listener()
	def on_voice_member_speaking_start(self, member: discord.Member):
		print(f"[EVENT STAR SPEAK] {member.name} empezó a hablar (círculo verde ON)")

	@AudioSink.listener()
	def on_voice_member_speaking_stop(self, member: discord.Member):
		print(f"[EVENT SPEAK STOP] {member.name} dejó de hablar (círculo verde OFF)")

	@AudioSink.listener()
	def on_voice_member_speaking_state(self, member: discord.Member, ssrc: int, state):
		print(f"[EVENT CHANGE SPEAKING] {member.name} cambió speaking_state={state} (ssrc={ssrc})")

	@AudioSink.listener()
	def on_voice_member_video(self, member: discord.Member, data: voice_recv.VoiceVideoStreams):
		print(f"[EVENT CAMERA] {member.name} cámara {'ON' if data else 'OFF'}")

	@AudioSink.listener()
	def on_voice_member_flags(self, member: discord.Member, flags: voice_recv.VoiceFlags):
		print(f"[EVENT FLAGS] {member.name} flags={flags}")

	@AudioSink.listener()
	def on_voice_member_platform(self, member: discord.Member, platform: voice_recv.VoicePlatform | None):
		print(f"[EVENT PLATFORM] {member.name} conectado desde plataforma={platform}")

	@AudioSink.listener()
	def on_rtcp_packet(self, packet: voice_recv.RTCPPacket, guild: discord.Guild):
		print(f"[EVENT PACKET] RTCP packet recibido en guild {guild.name}: {packet}")


logSink = LoggingSink()


class Testing(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	@commands.command()
	async def test(self, ctx):
		def after_callback(error: Exception | None):
			if error:
				print(f"❌ Error durante la grabación: {error}")
			else:
				print("✅ Grabación finalizada correctamente")

		def callback(user: Optional[Union[Member, User]], data: voice_recv.VoiceData):
			print(f"Got packet from {user}")
			# if data.pcm:  # si trae audio decodificado
			#     self.wav_file.writeframes(data.pcm)

			## voice power level, how loud the user is speaking
			# ext_data = packet.extension_data.get(voice_recv.ExtensionID.audio_power)
			# value = int.from_bytes(ext_data, 'big')
			# power = 127-(value & 127)
			# print('#' * int(power * (79/128)))
			## instead of 79 you can use shutil.get_terminal_size().columns-1

		channel: discord.VoiceChannel = ctx.author.voice.channel
		vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
		# vc.listen(voice_recv.BasicSink(callback), after = after_callback)
		# vc.listen(logSink, after=after_callback)
		vc.listen(voice_recv.WaveSink("audio-output/test.wav"))

	@commands.command()
	async def stop(self, ctx):
		await ctx.voice_client.disconnect()

	@commands.command()
	async def die(self, ctx):
		ctx.voice_client.stop()
		await ctx.bot.close()


@bot.event
async def on_ready():
	print('Logged in as {0.id}/{0}'.format(bot.user))
	print('------')


@bot.event
async def setup_hook():
	await bot.add_cog(Testing(bot))


bot.run(env.TOKEN)

# @commands.command(name='join', description="I'll join you in a voice channel to begin listening for voice commands!")
# async def join(self, ctx):
#     if ctx.author.voice:
#
#         # Runs when voice data is received
#         def voiceInput(user, voicedata: voice_recv.VoiceData):
#             print(f"Got voice packet from {user}")
#             print(type(voicedata.pcm))
#
#         # Check to see if Sophie is already connected to a voice channel
#         if ctx.voice_client is None:
#             await ctx.send(f"Joining {ctx.author.voice.channel.name}")
#             vc = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
#             vc.listen(voice_recv.BasicSink(voiceInput))
