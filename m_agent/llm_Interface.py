from abc import ABC, abstractmethod

class LLMInterface(ABC):
    @abstractmethod
    def chat(self, prompt: str) -> str:
        """Genera una respuesta de texto a partir de un prompt y contexto"""
        pass
