from abc import ABC, abstractmethod
from typing import AsyncGenerator, Iterator


class LLMInterface(ABC):
    @abstractmethod
    def chat(self, prompt: str) -> str:
        """Genera una respuesta de texto a partir de un prompt y contexto"""
        pass

    @abstractmethod
    def chat_stream(self, prompt: str) -> Iterator[str]:
        """Genera una respuesta de texto en streaming a partir de un prompt y contexto"""
        pass