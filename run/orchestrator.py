import functools
import io

import discord
from discord.ext import commands, voice_recv
import asyncio
import numpy as np

import speech_recognition as sr

from run.context import ServiceContext


def make_recognizer():
	r = sr.Recognizer()
	r.energy_threshold = 100  # Nivel mínimo de volumen para detectar voz (ajusta según pruebas)
	r.dynamic_energy_threshold = True  # Se adapta al ruido de fondo
	r.pause_threshold = 5.0  # Tiempo de silencio antes de cortar frase
	r.phrase_threshold = 0.2  # Tiempo mínimo de voz para considerarlo frase
	r.non_speaking_duration = 0.8  # Silencios muy cortos los ignora
	return r


class DiscordBotService:
	def __init__(self, token: str, prefix: str = "$"):
		intents = discord.Intents.default()
		intents.message_content = True
		intents.voice_states = True
		self.commands_bot = commands.Bot(command_prefix=prefix, intents=intents)
		self.bot = self.commands_bot
		self.context = ServiceContext()
		self.token = token
		self.vc = None  # Para almacenar el cliente de voz
		self._register_commands()

	def _register_commands(self):
		@self.bot.command()
		async def join(ctx):
				if ctx.author.voice:
					vc: voice_recv.VoiceRecvClient = await ctx.author.voice.channel.connect(
							cls=voice_recv.VoiceRecvClient)
					self.vc = vc
					sink = voice_recv.extras.speechrecognition.SpeechRecognitionSink(
						process_cb=lambda recognizer, audio, user: self._process_audio(recognizer, audio, user),
						text_cb=lambda user, text: self._got_text(user, text),
						default_recognizer="google",  # "google", "azure", etc.
						phrase_time_limit=30,
						recognizer_factory=make_recognizer
					)

					vc.listen(sink)
					await ctx.send("Estoy escuchando y transcribiendo con Google.")
				else:
					await ctx.send("No estás en un canal de voz.")

		@self.bot.command()
		async def leave(ctx):
			if ctx.voice_client:
				await ctx.voice_client.disconnect()
				await ctx.send("Desconectado.")
			else:
				await ctx.send("No estoy en ningún canal de voz.")


	def _process_audio(self, recognizer: sr.Recognizer, audio: sr.AudioData, user):
		text = self.context.stt_engine.transcribe(recognizer, audio, user.display_name)
		return text

	def _got_text(self, user, text: str):
		print(f"[{user.display_name}] dijo: {text}")
		# Responder con voz
		response_text = f"Hola {user.display_name}, dijiste: {text}"
		audio_out = self.context.tts_engine.synthesize(response_text, voice="es")
		self.vc.play(discord.FFmpegPCMAudio(io.BytesIO(audio_out), pipe=True))

	def run(self):
			self.bot.run(self.token)
