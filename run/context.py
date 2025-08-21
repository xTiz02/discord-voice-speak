from stt.stt_google import GoogleSTTEngine
from tts.tts_google import GoogleTTSEngine


class ServiceContext:
    def __init__(self):
        self.stt_engine = GoogleSTTEngine(language="es-PE")
        self.tts_engine = GoogleTTSEngine()
