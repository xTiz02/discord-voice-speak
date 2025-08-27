"""
Cliente de ejemplo para recibir eventos del bot via WebSocket.
Muestra cómo otro proyecto Python puede conectarse y procesar los eventos en tiempo real.
"""

import asyncio
import websockets
import json
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DiscordBotWebSocketClient:
    """
    Cliente WebSocket para recibir eventos del bot de Discord.
    """

    def __init__(self, uri: str = "ws://localhost:8765"):
        self.uri = uri
        self.websocket = None
        self.running = False

        # Handlers para diferentes tipos de eventos
        self.event_handlers = {
            'connection': self._handle_connection,
            'conversation_start': self._handle_conversation_start,
            'text_block': self._handle_text_block,
            'conversation_end': self._handle_conversation_end,
            'audio_start': self._handle_audio_start,
            'audio_end': self._handle_audio_end,
            'system_test': self._handle_system_event,
            'stats': self._handle_stats,
            'pong': self._handle_pong,
        }

        # Estado del cliente
        self.current_conversations: Dict[int, dict] = {}
        self.stats = {
            'messages_received': 0,
            'conversations_processed': 0,
            'text_blocks_received': 0,
        }

    async def connect(self):
        """Conecta al servidor WebSocket"""
        try:
            logger.info(f"Conectando a {self.uri}...")
            self.websocket = await websockets.connect(self.uri)
            self.running = True
            logger.info("Conectado exitosamente")

            # Iniciar bucle de recepción
            await self._listen()

        except websockets.exceptions.ConnectionClosed:
            logger.info("Conexión cerrada")
        except Exception as e:
            logger.exception(f"Error en conexión: {e}")
        finally:
            self.running = False

    async def disconnect(self):
        """Desconecta del servidor WebSocket"""
        if self.websocket:
            await self.websocket.close()
            self.running = False
            logger.info("Desconectado")

    async def _listen(self):
        """Escucha mensajes del servidor"""
        try:
            async for message in self.websocket:
                await self._process_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Conexión cerrada por el servidor")
        except Exception as e:
            logger.exception(f"Error escuchando mensajes: {e}")

    async def _process_message(self, message: str):
        """Procesa un mensaje recibido"""
        try:
            data = json.loads(message)
            self.stats['messages_received'] += 1

            msg_type = data.get('type')
            user_id = data.get('user_id')
            user_name = data.get('user_name')
            content = data.get('content')
            timestamp = data.get('timestamp')
            metadata = data.get('metadata', {})

            logger.debug(f"Mensaje recibido - Tipo: {msg_type}, Usuario: {user_name}, Content: {content[:50]}...")

            # Llamar handler específico
            handler = self.event_handlers.get(msg_type, self._handle_unknown)
            await handler(data)

        except json.JSONDecodeError as e:
            logger.error(f"Error decodificando JSON: {e}")
        except Exception as e:
            logger.exception(f"Error procesando mensaje: {e}")

    # Event Handlers

    async def _handle_connection(self, data: dict):
        """Maneja evento de conexión"""
        logger.info(f"Conectado al bot: {data.get('content')}")
        if 'metadata' in data:
            logger.info(f"Estadísticas del servidor: {data['metadata'].get('stats', {})}")

    async def _handle_conversation_start(self, data: dict):
        """Maneja inicio de conversación"""
        user_id = data['user_id']
        user_name = data['user_name']
        initial_message = data['content']

        logger.info(f"🗣️  CONVERSACIÓN INICIADA - {user_name}: {initial_message}")

        # Guardar estado de conversación
        self.current_conversations[user_id] = {
            'user_name': user_name,
            'start_time': data['timestamp'],
            'text_blocks': [],
            'initial_message': initial_message
        }

        self.stats['conversations_processed'] += 1

    async def _handle_text_block(self, data: dict):
        """Maneja bloque de texto de la IA"""
        user_id = data['user_id']
        user_name = data['user_name']
        text_block = data['content']
        metadata = data.get('metadata', {})

        logger.info(f"🤖 TEXTO IA ({user_name}): {text_block}")

        # Actualizar conversación
        if user_id in self.current_conversations:
            self.current_conversations[user_id]['text_blocks'].append({
                'text': text_block,
                'timestamp': data['timestamp'],
                'metadata': metadata
            })

        self.stats['text_blocks_received'] += 1

        # Aquí podrías procesar el texto, enviarlo a otro sistema, etc.
        await self._process_ai_text(user_id, user_name, text_block, metadata)

    async def _handle_conversation_end(self, data: dict):
        """Maneja fin de conversación"""
        user_id = data['user_id']
        user_name = data['user_name']

        logger.info(f"✅ CONVERSACIÓN TERMINADA - {user_name}")

        # Procesar conversación completa
        if user_id in self.current_conversations:
            conversation = self.current_conversations.pop(user_id)
            await self._process_complete_conversation(user_id, conversation)

    async def _handle_audio_start(self, data: dict):
        """Maneja inicio de audio"""
        user_name = data['user_name']
        logger.info(f"🔊 AUDIO INICIADO para {user_name}")

    async def _handle_audio_end(self, data: dict):
        """Maneja fin de audio"""
        user_name = data['user_name']
        logger.info(f"🔇 AUDIO TERMINADO para {user_name}")

    async def _handle_system_event(self, data: dict):
        """Maneja eventos del sistema"""
        content = data['content']
        metadata = data.get('metadata', {})
        logger.info(f"⚙️  SISTEMA: {content}")
        if metadata:
            logger.debug(f"Metadata: {metadata}")

    async def _handle_stats(self, data: dict):
        """Maneja respuesta de estadísticas"""
        metadata = data.get('metadata', {})
        logger.info(f"📊 ESTADÍSTICAS DEL SERVIDOR: {metadata}")

    async def _handle_pong(self, data: dict):
        """Maneja respuesta pong"""
        logger.debug("🏓 Pong recibido")

    async def _handle_unknown(self, data: dict):
        """Maneja eventos desconocidos"""
        msg_type = data.get('type', 'unknown')
        logger.warning(f"❓ Evento desconocido: {msg_type}")

    # Métodos de procesamiento personalizable

    async def _process_ai_text(self, user_id: int, user_name: str, text_block: str, metadata: dict):
        """
        Procesa un bloque de texto de la IA.
        Sobrescribe este método para implementar lógica personalizada.
        """
        # Ejemplo: analizar sentimiento, guardar en base de datos, etc.
        block_length = len(text_block)

        if block_length > 100:
            logger.debug(f"Bloque largo detectado ({block_length} caracteres)")

        # Aquí podrías:
        # - Enviar a un sistema de análisis de sentimientos
        # - Guardar en una base de datos
        # - Procesar con NLP
        # - Enviar a otro webhook
        pass

    async def _process_complete_conversation(self, user_id: int, conversation: dict):
        """
        Procesa una conversación completa.
        Sobrescribe este método para implementar lógica personalizada.
        """
        user_name = conversation['user_name']
        total_blocks = len(conversation['text_blocks'])
        duration = conversation.get('end_time', 0) - conversation['start_time']

        logger.info(f"📝 Conversación completa procesada:")
        logger.info(f"   Usuario: {user_name}")
        logger.info(f"   Mensaje inicial: {conversation['initial_message']}")
        logger.info(f"   Bloques de respuesta: {total_blocks}")
        logger.info(f"   Duración: {duration:.2f}s")

        # Aquí podrías:
        # - Generar resumen de la conversación
        # - Guardar transcripción completa
        # - Enviar métricas a analytics
        # - Procesar con modelos de ML
        pass

    # Métodos utilitarios

    async def send_ping(self):
        """Envía ping al servidor"""
        if self.websocket:
            ping_msg = {"type": "ping", "timestamp": asyncio.get_event_loop().time()}
            await self.websocket.send(json.dumps(ping_msg))
            logger.debug("🏓 Ping enviado")

    async def request_stats(self):
        """Solicita estadísticas del servidor"""
        if self.websocket:
            stats_msg = {"type": "get_stats"}
            await self.websocket.send(json.dumps(stats_msg))
            logger.debug("📊 Estadísticas solicitadas")

    def get_client_stats(self) -> dict:
        """Retorna estadísticas del cliente"""
        return {
            **self.stats,
            'active_conversations': len(self.current_conversations),
            'connected': self.running
        }


# Ejemplo de uso
async def main():
    client = DiscordBotWebSocketClient("ws://localhost:8765")

    try:
        # Conectar y mantener conexión
        await client.connect()
    except KeyboardInterrupt:
        logger.info("Interrupción del usuario")
    finally:
        await client.disconnect()

        # Mostrar estadísticas finales
        stats = client.get_client_stats()
        logger.info(f"Estadísticas finales del cliente: {stats}")


if __name__ == "__main__":
    asyncio.run(main())