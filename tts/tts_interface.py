from abc import ABC, abstractmethod
from typing import Iterator, AsyncGenerator, Optional


class TTSInterface(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice: str = "es-ES") -> bytes:
        """Convierte texto en audio"""
        pass

    @abstractmethod
    async def stream(
            self,
            text: str,
            *,
            language: Optional[str] = None,
            voice_name: Optional[str] = None,
            speaking_rate: Optional[float] = None,
            sample_rate_hz: Optional[int] = None,
            chunker=None,
    ) -> AsyncGenerator[bytes, None]:
        """Convierte texto en audio streaming"""
        pass

    @abstractmethod
    async def stream_from_blocks(
            self,
            text_blocks: Iterator[str],
            *,
            language: Optional[str] = None,
            voice_name: Optional[str] = None,
            speaking_rate: Optional[float] = None,
            sample_rate_hz: Optional[int] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Convierte bloques de texto en audio streaming"""
        pass