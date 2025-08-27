import logging
import asyncio
from concurrent.futures import CancelledError
import discord
from discord.ext import commands, voice_recv
import speech_recognition as sr
import time
from typing import Dict, List, Iterator, Optional
import threading
from queue import Queue

from run.context import ServiceContext
from util.audio import StreamingAudio
from services.conversation_manager import ConversationManager, ConversationContext
from services.audio_manager import AudioManager, AudioContext

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def make_recognizer():
    """Crea y configura un recognizer de SpeechRecognition"""
    logger.debug("Creando recognizer de SpeechRecognition")
    r = sr.Recognizer()
    r.energy_threshold = 200
    r.dynamic_energy_threshold = True
    r.pause_threshold = 2.0
    r.phrase_threshold = 1.2
    r.non_speaking_duration = 0.8
    logger.debug("Recognizer configurado correctamente")
    return r


class ThreadSafeDiscordBotService:
    """
    Versión thread-safe del bot de Discord que maneja correctamente
    la comunicación entre el thread de audio y el loop principal.
    """

    def __init__(self, token: str, prefix: str = "$"):
        logger.info("Inicializando ThreadSafeDiscordBotService...")

        # Configurar bot de Discord
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        self.commands_bot = commands.Bot(command_prefix=prefix, intents=intents)
        self.bot = self.commands_bot
        self.bot.setup_hook = self._setup_hook
        self.token = token

        # Contexto de servicios
        self.context = ServiceContext()

        # Gestores especializados
        self.conversation_manager: Optional[ConversationManager] = None
        self.audio_manager: Optional[AudioManager] = None

        # Cliente de voz
        self.vc = None

        # Cola thread-safe para comunicación entre threads
        self._audio_queue = Queue()
        self._audio_processor_task: Optional[asyncio.Task] = None

        # Buffer para bloques de texto streaming
        self._current_text_blocks: Dict[int, Iterator[str]] = {}

        logger.debug("Registrando comandos...")
        self._register_commands()
        logger.info("ThreadSafeDiscordBotService inicializado correctamente.")

    async def _setup_hook(self):
        """Configuración inicial del bot"""
        loop = asyncio.get_event_loop()
        self.context.set_loop(loop)

        # Inicializar gestores
        self.conversation_manager = ConversationManager(
            llm_engine=self.context.llm_engine,
            silence_timeout=2
        )

        self.audio_manager = AudioManager(
            tts_engine=self.context.tts_engine
        )

        # Configurar callbacks
        self._setup_callbacks()

        # Inicializar gestores
        await self.conversation_manager.initialize()

        # Iniciar procesador de cola de audio
        self._audio_processor_task = asyncio.create_task(self._process_audio_queue())

        logger.info("Setup hook completado")

    def _setup_callbacks(self):
        """Configura los callbacks entre gestores"""

        # Callbacks del conversation manager
        self.conversation_manager.set_callbacks(
            on_response_start=self._on_response_start,
            on_response_block=self._on_response_block,
            on_response_complete=self._on_response_complete
        )

        # Callbacks del audio manager
        self.audio_manager.set_callbacks(
            on_speech_start=self._on_speech_start,
            on_speech_end=self._on_speech_end
        )

    async def _process_audio_queue(self):
        """Procesa la cola de audio de manera asíncrona"""
        logger.debug("Iniciando procesador de cola de audio")

        while True:
            try:
                # Esperar por nuevos elementos en la cola (non-blocking check)
                await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning

                if not self._audio_queue.empty():
                    try:
                        audio_data = self._audio_queue.get_nowait()
                        user_id = audio_data['user_id']
                        user_display_name = audio_data['user_display_name']
                        text = audio_data['text']

                        logger.debug(f"Procesando audio desde cola: {user_display_name} -> {text}")

                        # Procesar según el estado del audio manager
                        if self.audio_manager.is_speaking:
                            logger.debug(f"IA hablando, guardando en buffer pendiente: {text}")
                            self.audio_manager.add_pending_audio(user_id, user_display_name, text)
                        else:
                            # Procesamiento normal
                            self.conversation_manager.add_fragment(user_id, user_display_name, text)

                        self._audio_queue.task_done()

                    except Exception as e:
                        logger.exception(f"Error procesando elemento de cola de audio: {e}")

            except asyncio.CancelledError:
                logger.debug("Procesador de cola de audio cancelado")
                break
            except Exception as e:
                logger.exception(f"Error en procesador de cola de audio: {e}")

    async def _on_response_start(self, context: ConversationContext):
        """Callback cuando inicia la generación de respuesta"""
        logger.debug(f"Iniciando respuesta para {context.user_display_name}")

        # Inicializar iterador de bloques para este usuario
        self._current_text_blocks[context.user_id] = iter([])

    async def _on_response_block(self, context: ConversationContext, text_block: str):
        """Callback cuando llega un bloque de texto de la respuesta"""
        logger.debug(f"Bloque de respuesta para {context.user_display_name}: {text_block}")

        # Crear iterador con el nuevo bloque
        def block_generator():
            yield text_block

        # Crear contexto de audio
        audio_context = AudioContext(
            user_id=context.user_id,
            user_display_name=context.user_display_name,
            timestamp=time.time()
        )

        # Enviar inmediatamente a TTS streaming
        await self.audio_manager.speak_streaming(
            block_generator(),
            audio_context
        )

    async def _on_response_complete(self, context: ConversationContext):
        """Callback cuando termina la generación de respuesta"""
        logger.debug(f"Respuesta completa para {context.user_display_name}")

        # Limpiar bloques de texto
        if context.user_id in self._current_text_blocks:
            del self._current_text_blocks[context.user_id]

        # Procesar audio pendiente
        await self._process_pending_audio()

    async def _on_speech_start(self, audio_context: AudioContext):
        """Callback cuando inicia la síntesis de voz"""
        logger.debug(f"Iniciando síntesis para {audio_context.user_display_name}")

    async def _on_speech_end(self, audio_context: AudioContext):
        """Callback cuando termina la síntesis de voz"""
        logger.debug(f"Síntesis completada para {audio_context.user_display_name}")

    def _register_commands(self):
        """Registra los comandos del bot"""

        @self.bot.command()
        async def join(ctx):
            """Conecta el bot al canal de voz del usuario"""
            logger.debug(f"join() llamado por {ctx.author}")

            if ctx.author.voice:
                logger.debug("Usuario en canal de voz, intentando conectar...")
                vc: voice_recv.VoiceRecvClient = await ctx.author.voice.channel.connect(
                    cls=voice_recv.VoiceRecvClient
                )
                self.vc = vc
                self.audio_manager.set_voice_client(vc)
                logger.debug("Conectado al canal de voz")

                sink = voice_recv.extras.speechrecognition.SpeechRecognitionSink(
                    process_cb=lambda recognizer, audio, user: self._process_audio(recognizer, audio, user),
                    default_recognizer="google",
                    phrase_time_limit=60,
                    recognizer_factory=make_recognizer
                )

                logger.debug("Iniciando escucha con SpeechRecognitionSink...")
                vc.listen(sink)
                await ctx.send("🎤 Estoy escuchando y listo para conversar!")
            else:
                logger.debug("join() falló: usuario no está en canal de voz")
                await ctx.send("❌ No estás en un canal de voz.")

        @self.bot.command()
        async def leave(ctx):
            """Desconecta el bot del canal de voz"""
            if self.vc:
                await self.audio_manager.interrupt_and_clear()
                await self.vc.disconnect()
                self.vc = None
                await ctx.send("👋 Me desconecté del canal de voz.")
            else:
                await ctx.send("❌ No estoy conectado a ningún canal de voz.")

        @self.bot.command()
        async def reset_ai(ctx):
            """Reinicia la sesión de IA en caso de problemas"""
            try:
                if hasattr(self.context.llm_engine, 'reset_session'):
                    self.context.llm_engine.reset_session()
                    await ctx.send("🔄 Sesión de IA reiniciada correctamente.")
                    logger.debug("Sesión de IA reiniciada por comando")
                else:
                    await ctx.send("❌ No se puede reiniciar la sesión de IA.")
            except Exception as e:
                logger.exception(f"Error reiniciando IA: {e}")
                await ctx.send("❌ Error al reiniciar la sesión de IA.")

        @self.bot.command()
        async def status(ctx):
            """Muestra el estado actual del bot"""
            status_msg = "🤖 **Estado del Bot:**\n"
            status_msg += f"• Conectado a voz: {'✅' if self.vc else '❌'}\n"
            status_msg += f"• IA hablando: {'✅' if self.audio_manager.is_speaking else '❌'}\n"
            status_msg += f"• Cola de audio: {self._audio_queue.qsize()} elementos\n"

            pending_audio = await self.audio_manager.get_pending_audio()
            # Restaurar audio pendiente ya que get_pending_audio() lo limpia
            for user_id, data in pending_audio.items():
                self.audio_manager._pending_audio[user_id] = data

            status_msg += f"• Audio pendiente: {len(pending_audio)} usuarios\n"

            if hasattr(self.context.llm_engine, 'get_session_history_length'):
                history_len = self.context.llm_engine.get_session_history_length()
                status_msg += f"• Historial de conversación: {history_len} mensajes\n"

            await ctx.send(status_msg)

        @self.bot.command()
        async def interrupt(ctx):
            """Interrumpe la conversación actual"""
            await self.audio_manager.interrupt_and_clear()
            # Limpiar cola de audio
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                    self._audio_queue.task_done()
                except:
                    break
            await ctx.send("⏹️ Conversación interrumpida.")

    def _process_audio(self, recognizer: sr.Recognizer, audio: sr.AudioData, user):
        """
        Procesa el audio capturado y lo convierte en texto.
        Se ejecuta en el thread de voice_recv, por lo que debe ser thread-safe.
        """
        logger.debug(f"_process_audio() llamado para usuario {user.display_name}")

        try:
            text = self.context.stt_engine.transcribe(recognizer, audio, user.display_name)
            if text:
                logger.debug(f"Fragmento reconocido: {text}")

                # Agregar a cola thread-safe para procesamiento asíncrono
                audio_data = {
                    'user_id': user.id,
                    'user_display_name': user.display_name,
                    'text': text,
                    'timestamp': time.time()
                }

                self._audio_queue.put(audio_data)
                logger.debug(f"Audio agregado a cola para procesamiento")

            return None
        except Exception as e:
            logger.exception(f"Error en _process_audio: {e}")
            return None

    async def _process_pending_audio(self):
        """Procesa el audio que llegó mientras la IA estaba hablando"""
        pending_audio = await self.audio_manager.get_pending_audio()

        if not pending_audio:
            return

        logger.debug(f"Procesando audio pendiente de {len(pending_audio)} usuarios")

        for user_id, data in pending_audio.items():
            user_display_name = data['user_display_name']
            fragments = data['fragments']

            if fragments:
                # Combinar todos los fragmentos pendientes
                combined_text = " ".join(fragments).strip()
                logger.debug(f"Audio pendiente de {user_display_name}: {combined_text}")

                # Agregar al gestor de conversación
                self.conversation_manager.add_fragment(user_id, user_display_name, combined_text)

    async def cleanup(self):
        """Limpieza al cerrar el bot"""
        if self._audio_processor_task:
            self._audio_processor_task.cancel()
            try:
                await self._audio_processor_task
            except asyncio.CancelledError:
                pass

        if self.conversation_manager:
            await self.conversation_manager.shutdown()

        if self.audio_manager:
            await self.audio_manager.interrupt_and_clear()

    def run(self):
        """Ejecuta el bot"""
        logger.info("Ejecutando bot...")
        try:
            self.bot.run(self.token)
        except KeyboardInterrupt:
            logger.info("Bot detenido por usuario")
        finally:
            # Ejecutar limpieza
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.cleanup())
            loop.close()