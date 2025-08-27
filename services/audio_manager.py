import logging
import asyncio
import time
from typing import Dict, Optional, Callable, Iterator
from concurrent.futures import CancelledError
from dataclasses import dataclass

from tts.tts_interface import TTSInterface
from util.audio import StreamingAudio

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@dataclass
class AudioContext:
    """Contexto de audio para un usuario"""
    user_id: int
    user_display_name: str
    timestamp: float


class AudioManager:
    """
    Gestiona la reproducción de audio y el manejo de interrupciones de voz.
    """

    def __init__(self, tts_engine: TTSInterface):
        self.tts_engine = tts_engine

        # Estado de reproducción
        self._is_speaking = False
        self._speaking_lock = asyncio.Lock()
        self._current_speech_task: Optional[asyncio.Task] = None

        # Audio pendiente mientras la IA habla
        self._pending_audio: Dict[int, dict] = {}

        # Referencia al cliente de voz de Discord
        self._voice_client = None

        # Callbacks
        self._on_speech_start: Optional[Callable] = None
        self._on_speech_end: Optional[Callable] = None
        self._on_pending_audio: Optional[Callable] = None

        logger.info("AudioManager inicializado")

    def set_voice_client(self, voice_client):
        """Configura el cliente de voz de Discord"""
        self._voice_client = voice_client
        logger.debug("Cliente de voz configurado")

    def set_callbacks(
            self,
            on_speech_start: Optional[Callable] = None,
            on_speech_end: Optional[Callable] = None,
            on_pending_audio: Optional[Callable] = None
    ):
        """Configura los callbacks para eventos de audio"""
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._on_pending_audio = on_pending_audio

    @property
    def is_speaking(self) -> bool:
        """Indica si la IA está hablando actualmente"""
        return self._is_speaking

    def add_pending_audio(self, user_id: int, user_display_name: str, fragment: str):
        """
        Agrega audio que llegó mientras la IA estaba hablando.
        Thread-safe: puede ser llamado desde cualquier thread.
        """
        logger.debug(f"Audio pendiente de {user_display_name}: {fragment}")

        # Esta operación es thread-safe porque solo modifica estructuras de datos simples
        # y no interactúa con el event loop
        if user_id not in self._pending_audio:
            self._pending_audio[user_id] = {
                'user_display_name': user_display_name,
                'fragments': [],
                'timestamp': time.time()
            }

        self._pending_audio[user_id]['fragments'].append(fragment)
        self._pending_audio[user_id]['timestamp'] = time.time()

    async def get_pending_audio(self) -> Dict[int, dict]:
        """
        Obtiene y limpia el audio pendiente.
        """
        if not self._pending_audio:
            return {}

        pending = self._pending_audio.copy()
        self._pending_audio.clear()

        logger.debug(f"Recuperando audio pendiente de {len(pending)} usuarios")
        return pending

    async def speak_streaming(self, text_blocks: Iterator[str], audio_context: AudioContext):
        """
        Reproduce texto usando TTS streaming desde bloques de texto.
        """
        if not self._voice_client:
            logger.error("No hay cliente de voz disponible")
            return

        async with self._speaking_lock:
            try:
                # Detener audio actual si está reproduciendo
                if self._voice_client.is_playing():
                    logger.debug("Deteniendo audio en reproducción...")
                    self._voice_client.stop()

                # Cancelar tarea TTS previa
                if self._current_speech_task and not self._current_speech_task.done():
                    logger.debug("Cancelando tarea previa de TTS...")
                    self._current_speech_task.cancel()
                    try:
                        await self._current_speech_task
                    except CancelledError:
                        logger.debug("Tarea TTS cancelada correctamente")

                # Marcar que la IA está hablando
                self._is_speaking = True
                logger.debug("Marcando _is_speaking = True")

                if self._on_speech_start:
                    await self._execute_callback(self._on_speech_start, audio_context)

                # Iniciar nueva respuesta de voz
                self._current_speech_task = asyncio.create_task(
                    self._stream_tts_audio(text_blocks, audio_context)
                )
                await self._current_speech_task

            except Exception as e:
                logger.exception(f"Error en speak_streaming: {e}")
            finally:
                # Siempre marcar que terminó
                self._is_speaking = False
                logger.debug("Marcando _is_speaking = False")

                if self._on_speech_end:
                    await self._execute_callback(self._on_speech_end, audio_context)

    async def _stream_tts_audio(self, text_blocks: Iterator[str], audio_context: AudioContext):
        """Reproduce audio TTS desde bloques de texto en streaming"""
        logger.debug(f"Iniciando streaming TTS para {audio_context.user_display_name}")

        try:
            # Crear generador de audio desde bloques de texto
            async def audio_generator():
                async for chunk in self.tts_engine.stream_from_blocks(
                        text_blocks,
                        language="es-US",
                        voice_name="es-US-Journey-F",
                        speaking_rate=1.2,
                        sample_rate_hz=48000,
                ):
                    yield chunk

            # Crear fuente de audio streaming
            source = StreamingAudio(
                audio_generator(),
                loop=asyncio.get_event_loop(),
                gain=2.0
            )

            # Reproducir audio
            self._voice_client.play(source)

            # Esperar a que termine la reproducción
            while self._voice_client.is_playing():
                await asyncio.sleep(0.1)

            logger.debug("Reproducción de TTS completada")

        except Exception as e:
            logger.exception(f"Error en _stream_tts_audio: {e}")

    async def interrupt_and_clear(self):
        """
        Interrumpe el audio actual y limpia el estado.
        """
        logger.debug("Interrumpiendo audio actual")

        if self._voice_client and self._voice_client.is_playing():
            self._voice_client.stop()

        if self._current_speech_task and not self._current_speech_task.done():
            self._current_speech_task.cancel()
            try:
                await self._current_speech_task
            except CancelledError:
                pass

        self._is_speaking = False
        logger.debug("Audio interrumpido y estado limpiado")

    async def _execute_callback(self, callback: Callable, *args, **kwargs):
        """Ejecuta un callback de manera segura"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Error ejecutando callback de audio: {e}")