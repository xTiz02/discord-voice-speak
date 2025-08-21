from abc import ABC, abstractmethod

class TTSInterface(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice: str = "es-ES") -> bytes:
        """Convierte texto en audio"""
        pass
