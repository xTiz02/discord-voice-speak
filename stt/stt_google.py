import speech_recognition as sr
from .stt_interface import STTInterface

class GoogleSTTEngine(STTInterface):
    def __init__(self, language="es-PE"):
        self.language = language

    def transcribe(self,reconocizer, audio: sr.AudioData, user_id: str) -> str:
        try:
            # audio = sr.AudioData(audio_bytes, sample_rate=16000, sample_width=2)
            text = reconocizer.recognize_google(audio, language=self.language)
            return text
        except sr.UnknownValueError:
            print("Google Speech Recognition could not understand audio")
        except Exception as e:
            print(f"[STT ERROR] {user_id}: {e}")
        return None
