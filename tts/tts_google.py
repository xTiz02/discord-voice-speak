import io
import threading
import asyncio
import logging
from typing import Iterable, Optional, List
from google.cloud import texttospeech

from .tts_interface import TTSInterface

logger = logging.getLogger(__name__)


def _default_chunker(text: str, max_len: int = 200) -> List[str]:
    """
    Divide el texto en fragmentos cortos para mejorar el streaming.
    Intenta cortar en signos de puntuación; si no, trocea por longitud.
    """
    text = text.strip()
    if not text:
        logger.debug("Chunker recibió texto vacío.")
        return []

    parts = []
    current = []
    count = 0
    for ch in text:
        current.append(ch)
        count += 1
        if ch in ".!?;:" and count >= 40:
            parts.append("".join(current).strip())
            current, count = [], 0
        elif count >= max_len:
            parts.append("".join(current).strip())
            current, count = [], 0
    if current:
        parts.append("".join(current).strip())

    parts = [p for p in parts if p]
    logger.debug(f"Chunker generó {len(parts)} fragmentos de texto.")
    return parts


class GoogleTTSEngine(TTSInterface):
    """
    Streaming TTS con Google Cloud Text-to-Speech (bidireccional).
    """
    def __init__(
        self,
        language: str = "es-US",
        voice_name: str = "es-US-Journey-F",
        sample_rate_hz: int = 48000,
        speaking_rate: float = 1.2,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ):
        self.client = texttospeech.TextToSpeechClient()
        self.default_language = language
        self.default_voice_name = voice_name
        self.sample_rate_hz = sample_rate_hz
        self.speaking_rate = speaking_rate
        self.loop = loop
        logger.info(
            f"GoogleTTSEngine inicializado con voz={voice_name}, lang={language}, "
            f"rate={speaking_rate}, sample_rate={sample_rate_hz}"
        )

    def _build_request_iter(
        self,
        text_chunks: Iterable[str],
        language: Optional[str] = None,
        voice_name: Optional[str] = None,
        speaking_rate: Optional[float] = None,
        sample_rate_hz: Optional[int] = None,
    ):
        language = language or self.default_language
        voice_name = voice_name or self.default_voice_name
        speaking_rate = speaking_rate if speaking_rate is not None else self.speaking_rate
        sample_rate_hz = sample_rate_hz or self.sample_rate_hz

        logger.debug(
            f"Construyendo requests para {len(list(text_chunks))} chunks, "
            f"voz={voice_name}, lang={language}, rate={speaking_rate}"
        )

        # ⚠️ Tenemos que volver a convertir text_chunks en iterable (se consumió con list)
        text_chunks = list(text_chunks)

        audio_config = texttospeech.StreamingAudioConfig(
            audio_encoding=texttospeech.AudioEncoding.PCM,
            sample_rate_hertz=sample_rate_hz,
            speaking_rate=speaking_rate,
        )

        streaming_config = texttospeech.StreamingSynthesizeConfig(
            voice=texttospeech.VoiceSelectionParams(
                name=voice_name,
                language_code=language,
            ),
            streaming_audio_config=audio_config
        )

        yield texttospeech.StreamingSynthesizeRequest(
            streaming_config=streaming_config
        )

        for i, chunk in enumerate(text_chunks, start=1):
            if not chunk:
                continue
            logger.debug(f"Enviando chunk {i}/{len(text_chunks)}: {chunk[:50]}...")
            yield texttospeech.StreamingSynthesizeRequest(
                input=texttospeech.StreamingSynthesisInput(text=chunk)
            )

    async def stream(
        self,
        text: str,
        *,
        language: Optional[str] = None,
        voice_name: Optional[str] = None,
        speaking_rate: Optional[float] = None,
        sample_rate_hz: Optional[int] = None,
        chunker=_default_chunker,
    ):
        """
        Async generator que produce bytes PCM (s16le 48k mono) a medida que Google los va generando.
        """
        loop = asyncio.get_running_loop()
        #full q
        queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=240)



        text_chunks = chunker(text)
        request_iter = self._build_request_iter(
            text_chunks,
            language=language,
            voice_name=voice_name,
            speaking_rate=speaking_rate,
            sample_rate_hz=sample_rate_hz,
        )

        def _worker():
            logger.debug("Worker de streaming TTS iniciado.")
            try:
                for resp in self.client.streaming_synthesize(request_iter):
                    if resp.audio_content:
                        logger.debug(f"Recibido chunk de audio de {len(resp.audio_content)} bytes.")
                        loop.call_soon_threadsafe(queue.put_nowait, resp.audio_content)
            except Exception as e:
                logger.exception(f"Error en streaming_synthesize: {e}")
                loop.call_soon_threadsafe(queue.put_nowait, None)
            else:
                logger.debug("Streaming TTS completado con éxito.")
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=_worker, daemon=True).start()

        while True:
            chunk = await queue.get()
            if chunk is None:
                logger.debug("Finalizando stream generator (cola cerrada).")
                break
            yield chunk

    def synthesize(self, text: str, *, language: Optional[str] = None, voice: Optional[str] = None):
        """
        Modo no-streaming: retorna todo el audio en un solo bloque.
        """
        language = language or self.default_language
        voice = voice or self.default_voice_name
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice_params = texttospeech.VoiceSelectionParams(language_code=language, name=voice)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.sample_rate_hz,
            speaking_rate=self.speaking_rate,
        )

        logger.debug(f"Solicitando TTS no-streaming para texto de {len(text)} caracteres.")
        resp = self.client.synthesize_speech(
            input=synthesis_input, voice=voice_params, audio_config=audio_config
        )
        logger.debug(f"Recibido audio no-streaming de {len(resp.audio_content)} bytes.")
        return resp.audio_content
