from stt.stt_google import GoogleSTTEngine
from tts.tts_google import GoogleTTSEngine


class ServiceContext:
    def __init__(self):
        self.stt_engine = GoogleSTTEngine(language="es-PE")
        self.tts_engine = GoogleTTSEngine(
            language="es-US",
            voice_name="es-US-Journey-F",
            sample_rate_hz=48000,
            speaking_rate=1.2
        )
