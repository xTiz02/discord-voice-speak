from abc import ABC, abstractmethod
import numpy as np
import speech_recognition as sr

class STTInterface(ABC):
    @abstractmethod
    def transcribe(self,reconocizer: sr.Recognizer, audio: sr.AudioData, user_id: str) -> str:
        """Convierte audio en texto"""
        pass
