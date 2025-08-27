import logging
import re
from typing import Iterator, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class BlockType(Enum):
    TINY = "tiny"  # 1-3 caracteres
    SMALL = "small"  # 4-15 caracteres
    MEDIUM = "medium"  # 16-50 caracteres
    LARGE = "large"  # 50+ caracteres
    PUNCTUATION = "punct"  # Solo signos de puntuación
    WHITESPACE = "space"  # Solo espacios/saltos


class SmartTTSChunker:
    """
    Chunker inteligente que analiza y agrupa bloques de texto streaming
    para formar oraciones coherentes antes de enviarlas al TTS.
    """

    def __init__(
            self,
            min_chunk_size: int = 30,  # Incrementado de 25 a 30 para ser más conservador
            max_chunk_size: int = 200,
            sentence_timeout: float = 0.5  # segundos para esperar más texto
    ):
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.sentence_timeout = sentence_timeout

        # Buffer principal para acumular texto
        self.buffer = ""

        # Patrones para detectar finales de oración
        self.sentence_endings = re.compile(r'[.!?]+\s*$')
        self.strong_endings = re.compile(r'[.!?]+\s*$')
        self.weak_endings = re.compile(r'[,;:]+\s*$')

        # Palabras que indican continuación de oración
        self.continuation_words = {
            'y', 'o', 'pero', 'sin', 'con', 'de', 'en', 'a', 'por', 'para',
            'que', 'como', 'cuando', 'donde', 'mientras', 'aunque', 'si',
            'and', 'or', 'but', 'with', 'without', 'of', 'in', 'at', 'by', 'for',
            'that', 'which', 'when', 'where', 'while', 'although', 'if'
        }

    def _classify_block(self, block: str) -> BlockType:
        """Clasifica un bloque de texto según su contenido y tamaño."""
        if not block:
            return BlockType.WHITESPACE

        clean_block = block.strip()
        if not clean_block:
            return BlockType.WHITESPACE

        # Solo puntuación
        if re.match(r'^[.!?;:,\s]*$', clean_block):
            return BlockType.PUNCTUATION

        length = len(clean_block)
        if length <= 3:
            return BlockType.TINY
        elif length <= 15:
            return BlockType.SMALL
        elif length <= 50:
            return BlockType.MEDIUM
        else:
            return BlockType.LARGE

    def _should_send_chunk(self, text: str) -> bool:
        """
        Determina si un chunk debería enviarse al TTS basado en reglas estrictas.
        """
        text = text.strip()

        # REGLA 1: Si tiene menos de 5 caracteres, NUNCA enviar
        if len(text) < 5:
            logger.debug(f"Chunk muy pequeño ({len(text)} chars), no enviando")
            return False

        # REGLA 2: Si termina con espacio, dejarlo pasar
        if text.endswith(' '):
            logger.debug("Chunk termina con espacio, enviando")
            return True

        # REGLA 3: Analizar la última palabra
        # Encontrar el último espacio para separar la última palabra
        last_space_index = text.rfind(' ')

        if last_space_index == -1:
            # No hay espacios, es una sola palabra
            last_word = text
        else:
            # Hay espacios, obtener la última palabra
            last_word = text[last_space_index + 1:]

        # REGLA 4: Si la última palabra tiene menos de 4 caracteres, concatenar con el siguiente
        if len(last_word) < 4:
            logger.debug(f"Última palabra muy corta ('{last_word}'), esperando más contenido")
            return False

        # REGLA 5: Si la última palabra tiene 4+ caracteres, considerarlo completo
        logger.debug(f"Última palabra suficientemente larga ('{last_word}'), enviando chunk")
        return True

    def _has_strong_sentence_ending(self, text: str) -> bool:
        """
        Verifica si el texto tiene un final de oración fuerte que justifique enviarlo.
        """
        return bool(self.strong_endings.search(text.strip()))

    def _should_wait_for_more(self, text: str) -> bool:
        """
        Determina si debemos esperar más texto antes de enviar al TTS.
        """
        text = text.strip()

        # REGLA PRINCIPAL: Si es muy corto, SIEMPRE esperar más
        if len(text) < self.min_chunk_size:
            return True

        # Si termina con puntuación débil, esperar
        if self.weak_endings.search(text):
            return True

        # Si la última palabra es de continuación, esperar
        words = text.lower().split()
        if words:
            last_word = re.sub(r'[^\w]', '', words[-1])
            if last_word in self.continuation_words:
                return True

        # Si no hay signos de puntuación fuerte, es probable que siga
        if not self.strong_endings.search(text) and len(text) < self.min_chunk_size * 1.5:
            return True

        return False

    def _force_chunk_if_too_long(self) -> Optional[str]:
        """
        Fuerza un chunk si el buffer es demasiado largo.
        Intenta cortar en un punto natural usando las nuevas reglas.
        """
        if len(self.buffer) <= self.max_chunk_size:
            return None

        # Buscar punto de corte natural (después de puntuación fuerte)
        text = self.buffer[:self.max_chunk_size]

        # Buscar último punto de puntuación fuerte
        for i in range(len(text) - 1, max(0, len(text) - 50), -1):
            if text[i] in '.!?':
                potential_chunk = self.buffer[:i + 1].strip()
                if self._should_send_chunk(potential_chunk):
                    self.buffer = self.buffer[i + 1:].strip()
                    logger.debug(f"Chunk forzado por puntuación fuerte: {potential_chunk[:50]}...")
                    return potential_chunk

        # Si no hay puntuación fuerte, buscar punto de corte por palabras completas
        words = text.split()
        if len(words) > 1:
            # Intentar diferentes puntos de corte desde el final hacia atrás
            for i in range(len(words) - 1, 0, -1):
                potential_text = ' '.join(words[:i])
                if self._should_send_chunk(potential_text):
                    cut_point = len(potential_text)
                    chunk = self.buffer[:cut_point].strip()
                    self.buffer = self.buffer[cut_point:].strip()
                    logger.debug(f"Chunk forzado por palabra completa: {chunk[:50]}...")
                    return chunk

        # Último recurso: cortar a la mitad pero asegurar que no sea demasiado pequeño
        mid_point = len(text) // 2
        chunk = self.buffer[:mid_point].strip()
        self.buffer = self.buffer[mid_point:].strip()

        if len(chunk) >= 5:  # Aplicar regla mínima
            logger.debug(f"Chunk forzado por longitud (último recurso): {chunk[:50]}...")
            return chunk

        return None

    def process_blocks(self, text_blocks: Iterator[str]) -> Iterator[str]:
        """
        Procesa bloques de texto streaming y produce chunks inteligentes.
        """
        logger.debug("Iniciando procesamiento inteligente de bloques TTS")

        for block in text_blocks:
            if not block:
                continue

            block_type = self._classify_block(block)
            logger.debug(f"Bloque recibido ({block_type.value}): '{block[:30]}{'...' if len(block) > 30 else ''}'")

            # Agregar al buffer
            if block_type == BlockType.WHITESPACE:
                if self.buffer and not self.buffer.endswith(' '):
                    self.buffer += " "
                continue

            # Para bloques de puntuación, agregar directamente
            if block_type == BlockType.PUNCTUATION:
                self.buffer += block.strip()
            else:
                # Agregar espacio si es necesario
                if self.buffer and not self.buffer.endswith(' ') and not block.startswith(' '):
                    self.buffer += " "
                self.buffer += block.strip()

            current_buffer = self.buffer.strip()
            current_buffer_size = len(current_buffer)

            logger.debug(
                f"Buffer actual ({current_buffer_size} chars): '{current_buffer[:50]}{'...' if len(current_buffer) > 50 else ''}'")

            # NUEVA LÓGICA: Aplicar reglas estrictas para envío
            chunk_to_send = None

            # 1. Si el buffer es demasiado largo, forzar chunk (con corte inteligente)
            if current_buffer_size > self.max_chunk_size:
                chunk_to_send = self._force_chunk_if_too_long()

            # 2. Si tenemos un final de oración fuerte Y cumple las reglas de envío
            elif (current_buffer_size >= 10 and  # Mínimo absoluto más bajo para oraciones completas
                  self._has_strong_sentence_ending(current_buffer) and
                  self._should_send_chunk(current_buffer)):

                chunk_to_send = current_buffer
                self.buffer = ""

            # 3. Si el buffer es suficientemente grande y cumple las reglas de palabra completa
            elif (current_buffer_size >= self.min_chunk_size and
                  self._should_send_chunk(current_buffer)):

                chunk_to_send = current_buffer
                self.buffer = ""

            # Enviar chunk si cumple todas las validaciones
            if chunk_to_send:
                # Validación final: asegurar que no sea demasiado pequeño
                if len(chunk_to_send.strip()) >= 5:
                    logger.debug(f"✓ Enviando chunk ({len(chunk_to_send)} chars): {chunk_to_send[:50]}...")
                    yield chunk_to_send
                else:
                    # Chunk muy pequeño, regresarlo al buffer
                    logger.debug(f"✗ Chunk demasiado pequeño ({len(chunk_to_send)} chars), regresando al buffer")
                    if self.buffer:
                        self.buffer = chunk_to_send + " " + self.buffer
                    else:
                        self.buffer = chunk_to_send

        # Al final, enviar lo que queda SOLO si no es demasiado pequeño
        if self.buffer.strip():
            final_chunk = self.buffer.strip()
            # Para el chunk final, ser menos estricto (mínimo 3 chars)
            if len(final_chunk) >= 3:
                logger.debug(f"✓ Enviando chunk final ({len(final_chunk)} chars): {final_chunk[:50]}...")
                yield final_chunk
            else:
                logger.debug(f"✗ Descartando chunk final muy pequeño ({len(final_chunk)} chars): '{final_chunk}'")
                # No enviar chunks finales demasiado pequeños como "¡" o "."


def smart_streaming_chunker(text_blocks: Iterator[str], min_chunk_size: int = 25) -> Iterator[str]:
    """
    Función helper que usa el SmartTTSChunker.
    Compatible con tu interfaz actual.
    """
    chunker = SmartTTSChunker(min_chunk_size=min_chunk_size)
    yield from chunker.process_blocks(text_blocks)


# Ejemplo de uso y tests
if __name__ == "__main__":
    # Simular bloques fragmentados como los que recibes del streaming
    test_blocks = [
        "Hola",
        ",",
        " como",
        " estás",
        "?",
        " Espero",
        " que",
        " tengas",
        " un",
        " buen",
        " día",
        ".",
        " Este",
        " es",
        " un",
        " mensaje",
        " más",
        " largo",
        " que",
        " debería",
        " ser",
        " procesado",
        " correctamente",
        ".",
        " ¡",
        "Adiós",
        "!"
    ]

    print("Bloques originales:", test_blocks)
    print("\nChunks generados:")

    for i, chunk in enumerate(smart_streaming_chunker(iter(test_blocks)), 1):
        print(f"{i}: '{chunk}'")