import asyncio
import discord
import numpy as np
from concurrent.futures import CancelledError

class StreamingAudio(discord.AudioSource):
    """
    AudioSource para Discord que recibe PCM 16-bit mono 48kHz desde un generador async,
    aplica ganancia, convierte a stereo y maneja cancelaciones sin romper VoiceRecvClient.
    """
    BLOCK_SIZE = 960 * 2 * 2  # 960 samples, 2 bytes/sample, 2 canales

    def __init__(self, async_generator, loop=None, gain: float = 2.0):
        self.generator = async_generator.__aiter__()
        self.loop = loop or asyncio.get_event_loop()
        self.buffer = b""
        self.gain = gain

    def read(self):
        # Si ya tenemos buffer pendiente, enviamos primer bloque
        if len(self.buffer) >= self.BLOCK_SIZE:
            chunk, self.buffer = self.buffer[:self.BLOCK_SIZE], self.buffer[self.BLOCK_SIZE:]
            return chunk

        try:
            fut = asyncio.run_coroutine_threadsafe(self.generator.__anext__(), self.loop)
            try:
                chunk_mono = fut.result()
            except CancelledError:
                return b"\x00" * self.BLOCK_SIZE  # silencio si se cancela

            if not chunk_mono:
                return b""

            # Convertir a float para aplicar ganancia
            audio = np.frombuffer(chunk_mono, dtype=np.int16).astype(np.float32)
            audio *= self.gain
            audio = np.clip(audio, -32768, 32767)

            # Mono a stereo
            stereo = np.column_stack((audio, audio)).ravel().astype(np.int16)
            self.buffer += stereo.tobytes()

            # Retornar primer bloque
            if len(self.buffer) >= self.BLOCK_SIZE:
                chunk, self.buffer = self.buffer[:self.BLOCK_SIZE], self.buffer[self.BLOCK_SIZE:]
                return chunk
            else:
                chunk, self.buffer = self.buffer, b""
                return chunk

        except StopAsyncIteration:
            return b""
