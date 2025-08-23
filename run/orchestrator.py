import asyncio
from concurrent.futures import CancelledError
import discord
from discord.ext import commands, voice_recv
import speech_recognition as sr

from run.context import ServiceContext
from util.audio import StreamingAudio


def make_recognizer():
	print("[DEBUG] Creando recognizer de SpeechRecognition")
	r = sr.Recognizer()
	r.energy_threshold = 100
	r.dynamic_energy_threshold = True
	r.pause_threshold = 5.0
	r.phrase_threshold = 0.2
	r.non_speaking_duration = 0.8
	print("[DEBUG] Recognizer configurado correctamente")
	return r


class DiscordBotService:
	def __init__(self, token: str, prefix: str = "$"):
		print("[DEBUG] Inicializando DiscordBotService...")
		intents = discord.Intents.default()
		intents.message_content = True
		intents.voice_states = True
		self.commands_bot = commands.Bot(command_prefix=prefix, intents=intents)
		self.bot = self.commands_bot
		self.context = ServiceContext()
		self.token = token
		self.vc = None  # VoiceRecvClient
		self._speech_task = None  # para cancelar si ya hay audio
		print("[DEBUG] Registrando comandos...")
		self._register_commands()
		print("[DEBUG] DiscordBotService inicializado correctamente.")

	def _register_commands(self):
		@self.bot.command()
		async def join(ctx):
			print(f"[DEBUG] join() llamado por {ctx.author}")
			if ctx.author.voice:
				print("[DEBUG] Usuario en canal de voz, intentando conectar...")
				vc: voice_recv.VoiceRecvClient = await ctx.author.voice.channel.connect(
					cls=voice_recv.VoiceRecvClient
				)
				self.vc = vc
				print("[DEBUG] Conectado al canal de voz")

				sink = voice_recv.extras.speechrecognition.SpeechRecognitionSink(
					process_cb=lambda recognizer, audio, user: self._process_audio(recognizer, audio, user),
					text_cb=lambda user, text: self._got_text(user, text),
					default_recognizer="google",
					phrase_time_limit=30,
					recognizer_factory=make_recognizer
				)

				print("[DEBUG] Iniciando escucha con SpeechRecognitionSink...")
				vc.listen(sink)
				await ctx.send("Estoy escuchando y transcribiendo con Google.")
			else:
				print("[DEBUG] join() falló: usuario no está en canal de voz")
				await ctx.send("No estás en un canal de voz.")

		@self.bot.command()
		async def leave(ctx):
			print(f"[DEBUG] leave() llamado por {ctx.author}")
			if ctx.voice_client:
				print("[DEBUG] Desconectando bot del canal de voz...")
				await ctx.voice_client.disconnect()
				await ctx.send("Desconectado.")
			else:
				print("[DEBUG] leave() falló: no hay conexión activa")
				await ctx.send("No estoy en ningún canal de voz.")

	def _process_audio(self, recognizer: sr.Recognizer, audio: sr.AudioData, user):
		print(f"[DEBUG] _process_audio() llamado para usuario {user.display_name}")
		try:
			text = self.context.stt_engine.transcribe(recognizer, audio, user.display_name)
			print(f"[DEBUG] Transcripción obtenida de {user.display_name}: {text}")
			return text
		except Exception as e:
			print(f"[ERROR] Fallo en _process_audio: {e}")
			return ""

	def _got_text(self, user, text: str):
		print(f"[DEBUG] _got_text() → Usuario={user.display_name}, Texto={text}")
		response_text = f"Hola {user.display_name}, dijiste: {text}"

		if self.vc:
			print(f"[DEBUG] Hay conexión de voz. is_playing={self.vc.is_playing()}")
		else:
			print("[DEBUG] No hay conexión de voz (self.vc es None)")

		# Si está reproduciendo audio, detener
		if self.vc and self.vc.is_playing():
			print("[DEBUG] Deteniendo audio en reproducción...")
			self.vc.stop()

		# Si había una tarea previa de TTS, cancelarla correctamente
		if self._speech_task:
			print("[DEBUG] Cancelando tarea previa de TTS...")
			future = self._speech_task
			if not future.done():
				future.cancel()
				try:
					future.result()
				except CancelledError:
					print("[DEBUG] Tarea previa de TTS cancelada con éxito")
				except Exception as e:
					print(f"[ERROR] Error al cancelar tarea previa de TTS: {e}")
			self._speech_task = None
		else:
			print("[DEBUG] No había tarea previa de TTS")

		# Ejecutar en el loop de discord (puede venir desde otro thread)
		print(f"[DEBUG] Enviando _speak_streaming() al loop con texto: {response_text}")
		future = asyncio.run_coroutine_threadsafe(
			self._speak_streaming(response_text),
			self.bot.loop
		)
		self._speech_task = future
		print("[DEBUG] Nueva tarea de TTS lanzada")

	async def _speak_streaming(self, text: str):
		print(f"[DEBUG] _speak_streaming() iniciado con texto: {text}")
		if not self.vc:
			print("[ERROR] No hay conexión de voz, abortando _speak_streaming")
			return

		async def generator():
			async for chunk in self.context.tts_engine.stream(
					text,
					language="es-US",
					voice_name="es-US-Journey-F",
					speaking_rate=1.2,
					sample_rate_hz=48000,
			):
				yield chunk  # Deja que StreamingAudio haga la conversión a stereo

		# Reproducción directa
		source = StreamingAudio(generator(), loop=asyncio.get_event_loop(), gain=2.0)
		self.vc.play(source)

	def run(self):
		print("[DEBUG] Ejecutando bot...")
		self.bot.run(self.token)
