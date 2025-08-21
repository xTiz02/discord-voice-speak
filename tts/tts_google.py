# from gtts import gTTS
import io
from .tts_interface import TTSInterface

class GoogleTTSEngine(TTSInterface):
    def synthesize(self, text: str, voice: str = "es") -> bytes:
        # tts = gTTS(text=text, lang=voice)
        buffer = io.BytesIO()
        # tts.write_to_fp(buffer)
        buffer.seek(0)
        return buffer.read()
