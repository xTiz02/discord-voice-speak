import asyncio
from concurrent.futures import CancelledError
import discord
from discord.ext import commands, voice_recv
import speech_recognition as sr
import time
from typing import Dict, List
import threading

from run.context import ServiceContext
from util.audio import StreamingAudio


def make_recognizer():
    print("[DEBUG] Creando recognizer de SpeechRecognition")
    r = sr.Recognizer()
    r.energy_threshold = 200
    r.dynamic_energy_threshold = True
    r.pause_threshold = 4.0
    r.phrase_threshold = 1.2
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
        self.bot.setup_hook = self._setup_hook
        self.context = ServiceContext()
        self.token = token

        # Buffers y timers por usuario para acumular frases
        self._user_buffers = {}
        self._user_timers = {}
        self.SILENCE_TIMEOUT = 0

        # Estado del bot para manejar interrupciones
        self._is_speaking = False
        self._pending_audio = {}  # Audio que llega mientras habla la IA
        self._speaking_lock = asyncio.Lock()
        self._response_queue = asyncio.Queue()  # Cola para procesar respuestas secuencialmente

        self.vc = None
        self._speech_task = None
        self._response_processor_task = None

        print("[DEBUG] Registrando comandos...")
        self._register_commands()
        print("[DEBUG] DiscordBotService inicializado correctamente.")

    async def _setup_hook(self):
        loop = asyncio.get_running_loop()
        self.context.set_loop(loop)
        # Iniciar procesador de respuestas
        self._response_processor_task = asyncio.create_task(self._process_responses())

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
                    default_recognizer="google",
                    phrase_time_limit=60,
                    recognizer_factory=make_recognizer
                )

                print("[DEBUG] Iniciando escucha con SpeechRecognitionSink...")
                vc.listen(sink)
                await ctx.send("Estoy escuchando y transcribiendo con Google.")
            else:
                print("[DEBUG] join() falló: usuario no está en canal de voz")
                await ctx.send("No estás en un canal de voz.")

        @self.bot.command()
        async def reset_ai(ctx):
            """Comando para reiniciar la sesión de IA en caso de problemas"""
            try:
                if hasattr(self.context.llm_engine, 'reset_session'):
                    self.context.llm_engine.reset_session()
                    await ctx.send("Sesión de IA reiniciada correctamente.")
                    print("[DEBUG] Sesión de IA reiniciada por comando")
                else:
                    await ctx.send("No se puede reiniciar la sesión de IA.")
            except Exception as e:
                print(f"[ERROR] Error reiniciando IA: {e}")
                await ctx.send("Error al reiniciar la sesión de IA.")

        @self.bot.command()
        async def status(ctx):
            """Comando para verificar el estado del bot"""
            status_msg = f"🤖 **Estado del Bot:**\n"
            status_msg += f"• Conectado a voz: {'✅' if self.vc else '❌'}\n"
            status_msg += f"• IA hablando: {'✅' if self._is_speaking else '❌'}\n"
            status_msg += f"• Audio pendiente: {len(self._pending_audio)} usuarios\n"
            status_msg += f"• Buffers activos: {len(self._user_buffers)} usuarios\n"

            if hasattr(self.context.llm_engine, 'get_session_history_length'):
                history_len = self.context.llm_engine.get_session_history_length()
                status_msg += f"• Historial de conversación: {history_len} mensajes\n"

            await ctx.send(status_msg)

    def _process_audio(self, recognizer: sr.Recognizer, audio: sr.AudioData, user):
        print(f"[DEBUG] _process_audio() llamado para usuario {user.display_name}, is_speaking={self._is_speaking}")

        try:
            text = self.context.stt_engine.transcribe(recognizer, audio, user.display_name)
            if text:
                print(f"[DEBUG] Fragmento reconocido: {text}")

                # Si la IA está hablando, guardar en buffer pendiente
                if self._is_speaking:
                    print(f"[DEBUG] IA hablando, guardando en buffer pendiente: {text}")
                    user_id = user.id
                    if user_id not in self._pending_audio:
                        self._pending_audio[user_id] = {
                            'user': user,
                            'fragments': []
                        }
                    self._pending_audio[user_id]['fragments'].append(text)
                else:
                    # Procesamiento normal
                    self._add_fragment(user, text)

            return None
        except Exception as e:
            print(f"[ERROR] Fallo en _process_audio: {e}")
            return None

    async def _process_responses(self):
        """Procesa las respuestas de manera secuencial para evitar conflictos"""
        print("[DEBUG] Iniciando procesador de respuestas")
        while True:
            try:
                user, text = await self._response_queue.get()
                print(f"[DEBUG] Procesando respuesta para {user.display_name}: {text}")
                await self._handle_user_message(user, text)
                self._response_queue.task_done()
            except asyncio.CancelledError:
                print("[DEBUG] Procesador de respuestas cancelado")
                break
            except Exception as e:
                print(f"[ERROR] Error en procesador de respuestas: {e}")

    async def _handle_user_message(self, user, text: str):
        """Maneja el mensaje del usuario y genera respuesta"""
        async with self._speaking_lock:
            print(f"[DEBUG] _handle_user_message() → Usuario={user.display_name}, Texto={text}")

            response_text = None

            try:
                # Preparar prompt y obtener respuesta de la IA
                prompt = f"Usuario {user.display_name} dijo: {text}"
                print(f"[DEBUG] Enviando prompt a LLM: {prompt}")

                # Ejecutar la consulta a la IA en un thread separado para no bloquear
                loop = asyncio.get_event_loop()

                # Timeout para evitar bloqueos indefinidos
                response_text = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self.context.llm_engine.chat(prompt)
                    ),
                    timeout=15.0  # 15 segundos máximo
                )

                print(f"[DEBUG] Respuesta del LLM recibida: {response_text}")

                # Validar que tenemos una respuesta válida
                if not response_text or not response_text.strip():
                    print("[WARNING] Respuesta vacía del LLM, usando fallback")
                    response_text = "Disculpa, no pude procesar tu mensaje correctamente. ¿Podrías repetirlo?"

            except asyncio.TimeoutError:
                print("[ERROR] Timeout esperando respuesta del LLM")
                response_text = "Perdón por la demora. ¿En qué más puedo ayudarte?"

            except Exception as e:
                print(f"[ERROR] Error consultando LLM: {e}")
                response_text = "Hubo un pequeño problema técnico. ¿Puedes intentar de nuevo?"

            # Solo proceder con TTS si tenemos una respuesta
            if response_text and response_text.strip():
                try:
                    # Detener audio actual si está reproduciendo
                    if self.vc and self.vc.is_playing():
                        print("[DEBUG] Deteniendo audio en reproducción...")
                        self.vc.stop()

                    # Cancelar tarea TTS previa
                    if self._speech_task and not self._speech_task.done():
                        print("[DEBUG] Cancelando tarea previa de TTS...")
                        self._speech_task.cancel()
                        try:
                            await self._speech_task
                        except CancelledError:
                            print("[DEBUG] Tarea TTS cancelada correctamente")

                    # Marcar que la IA está hablando
                    self._is_speaking = True
                    print("[DEBUG] Marcando _is_speaking = True")

                    # Iniciar nueva respuesta de voz
                    self._speech_task = asyncio.create_task(self._speak_streaming(response_text))
                    await self._speech_task

                except Exception as e:
                    print(f"[ERROR] Error en reproducción de TTS: {e}")
            else:
                print("[ERROR] No hay respuesta válida para reproducir")

            # Siempre marcar que terminó y procesar audio pendiente
            self._is_speaking = False
            print("[DEBUG] Marcando _is_speaking = False")

            # Procesar audio pendiente
            await self._process_pending_audio()

    async def _speak_streaming(self, text: str):
        """Reproduce el texto usando TTS streaming"""
        print(f"[DEBUG] _speak_streaming() iniciado con texto: {text}")
        if not self.vc:
            print("[ERROR] No hay conexión de voz, abortando _speak_streaming")
            return

        try:
            async def generator():
                async for chunk in self.context.tts_engine.stream(
                        text,
                        language="es-US",
                        voice_name="es-US-Journey-F",
                        speaking_rate=1.2,
                        sample_rate_hz=48000,
                ):
                    yield chunk

            source = StreamingAudio(generator(), loop=asyncio.get_event_loop(), gain=2.0)
            self.vc.play(source)

            # Esperar a que termine la reproducción
            while self.vc.is_playing():
                await asyncio.sleep(0.1)

            print("[DEBUG] Reproducción de TTS completada")

        except Exception as e:
            print(f"[ERROR] Error en _speak_streaming: {e}")

    async def _process_pending_audio(self):
        """Procesa el audio que llegó mientras la IA estaba hablando"""
        if not self._pending_audio:
            return

        print(f"[DEBUG] Procesando {len(self._pending_audio)} usuarios con audio pendiente")

        for user_id, data in self._pending_audio.items():
            user = data['user']
            fragments = data['fragments']

            if fragments:
                # Combinar todos los fragmentos pendientes
                combined_text = " ".join(fragments).strip()
                print(f"[DEBUG] Audio pendiente de {user.display_name}: {combined_text}")

                # Agregar a cola para procesamiento
                await self._response_queue.put((user, combined_text))

        # Limpiar buffer pendiente
        self._pending_audio.clear()

    def _add_fragment(self, user, fragment: str):
        """Agrega fragmento al buffer del usuario y maneja el timeout"""
        user_id = user.id

        # Acumular en buffer
        if user_id not in self._user_buffers:
            self._user_buffers[user_id] = []
        self._user_buffers[user_id].append(fragment)

        # Cancelar temporizador previo
        if user_id in self._user_timers:
            self._user_timers[user_id].cancel()

        # Lanzar nuevo temporizador
        loop = self.bot.loop
        self._user_timers[user_id] = loop.call_later(
            self.SILENCE_TIMEOUT,
            lambda: self._finalize_phrase_sync(user)
        )

    def _finalize_phrase_sync(self, user):
        """Versión síncrona para call_later"""
        asyncio.run_coroutine_threadsafe(
            self._finalize_phrase(user),
            self.bot.loop
        )

    async def _finalize_phrase(self, user):
        """Finaliza una frase y la envía para procesamiento"""
        user_id = user.id
        fragments = self._user_buffers.get(user_id, [])

        if not fragments:
            return

        phrase = " ".join(fragments).strip()
        self._user_buffers[user_id] = []  # Limpiar buffer

        print(f"[DEBUG] Frase final detectada de {user.display_name}: {phrase}")

        # Agregar a cola de procesamiento
        await self._response_queue.put((user, phrase))

    def run(self):
        print("[DEBUG] Ejecutando bot...")
        self.bot.run(self.token)