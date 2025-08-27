import asyncio
import websockets
import json
import logging
from typing import Optional, Set, Dict, Any, Callable
from dataclasses import dataclass, asdict
import time

logger = logging.getLogger(__name__)


@dataclass
class StreamMessage:
    """Mensaje para streaming via websocket"""
    type: str  # 'text_block', 'conversation_start', 'conversation_end', 'audio_start', 'audio_end'
    user_id: int
    user_name: str
    content: str
    timestamp: float
    metadata: Dict[str, Any] = None

    def to_dict(self) -> dict:
        """Convierte el mensaje a diccionario para JSON"""
        return asdict(self)


class WebSocketService:
    """
    Servicio de WebSocket para streaming de conversaciones a otros proyectos Python.
    Permite que otros sistemas se conecten y reciban en tiempo real los bloques de texto
    generados por la IA y otros eventos del bot.
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port

        # Conjunto de clientes conectados
        self.clients: Set[websockets.WebSocketServerProtocol] = set()

        # Servidor WebSocket
        self.server = None
        self._server_task: Optional[asyncio.Task] = None

        # Callbacks para diferentes eventos
        self._event_handlers: Dict[str, Callable] = {}

        # Estadísticas
        self.stats = {
            'clients_connected': 0,
            'total_connections': 0,
            'messages_sent': 0,
            'errors': 0
        }

        logger.info(f"WebSocketService configurado en {host}:{port}")

    async def start_server(self):
        """Inicia el servidor WebSocket"""
        try:
            self.server = await websockets.serve(
                self._handle_client,
                self.host,
                self.port
            )
            logger.info(f"Servidor WebSocket iniciado en ws://{self.host}:{self.port}")

            # Mantener servidor corriendo
            self._server_task = asyncio.create_task(self.server.wait_closed())

        except Exception as e:
            logger.exception(f"Error iniciando servidor WebSocket: {e}")
            raise

    async def stop_server(self):
        """Detiene el servidor WebSocket"""
        if self.server:
            # Cerrar conexiones existentes
            if self.clients:
                await asyncio.gather(
                    *[client.close() for client in self.clients],
                    return_exceptions=True
                )

            # Cerrar servidor
            self.server.close()
            await self.server.wait_closed()

            if self._server_task:
                self._server_task.cancel()
                try:
                    await self._server_task
                except asyncio.CancelledError:
                    pass

            logger.info("Servidor WebSocket detenido")

    async def _handle_client(self, websocket, path):
        """Maneja una nueva conexión de cliente"""
        client_addr = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"Cliente conectado desde {client_addr}")

        self.clients.add(websocket)
        self.stats['clients_connected'] += 1
        self.stats['total_connections'] += 1

        try:
            # Enviar mensaje de bienvenida
            welcome_msg = StreamMessage(
                type="connection",
                user_id=0,
                user_name="system",
                content="Conectado al bot de Discord",
                timestamp=time.time(),
                metadata={"client_addr": client_addr, "stats": self.stats}
            )
            await self._send_to_client(websocket, welcome_msg)

            # Escuchar mensajes del cliente (aunque por ahora es principalmente unidireccional)
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.debug(f"Mensaje recibido de {client_addr}: {data}")

                    # Procesar comandos del cliente si es necesario
                    await self._process_client_message(websocket, data)

                except json.JSONDecodeError:
                    logger.warning(f"Mensaje JSON inválido de {client_addr}: {message}")

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Cliente {client_addr} desconectado")
        except Exception as e:
            logger.exception(f"Error manejando cliente {client_addr}: {e}")
            self.stats['errors'] += 1
        finally:
            self.clients.discard(websocket)
            self.stats['clients_connected'] -= 1

    async def _process_client_message(self, websocket, data: dict):
        """Procesa mensajes enviados por el cliente"""
        msg_type = data.get('type')

        if msg_type == 'ping':
            # Responder a ping con pong
            pong_msg = StreamMessage(
                type="pong",
                user_id=0,
                user_name="system",
                content="pong",
                timestamp=time.time()
            )
            await self._send_to_client(websocket, pong_msg)

        elif msg_type == 'get_stats':
            # Enviar estadísticas
            stats_msg = StreamMessage(
                type="stats",
                user_id=0,
                user_name="system",
                content="Estadísticas del servidor",
                timestamp=time.time(),
                metadata=self.stats
            )
            await self._send_to_client(websocket, stats_msg)

        else:
            logger.debug(f"Tipo de mensaje desconocido: {msg_type}")

    async def _send_to_client(self, websocket, message: StreamMessage):
        """Envía un mensaje a un cliente específico"""
        try:
            json_data = json.dumps(message.to_dict())
            await websocket.send(json_data)
            self.stats['messages_sent'] += 1
        except Exception as e:
            logger.error(f"Error enviando mensaje a cliente: {e}")
            self.stats['errors'] += 1

    async def broadcast_message(self, message: StreamMessage):
        """Envía un mensaje a todos los clientes conectados"""
        if not self.clients:
            return

        # Crear lista de tareas para envío concurrente
        tasks = []
        for client in self.clients.copy():  # Copia para evitar modificación durante iteración
            tasks.append(self._send_to_client(client, message))

        # Ejecutar todos los envíos concurrentemente
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # Métodos de conveniencia para diferentes tipos de eventos

    async def send_conversation_start(self, user_id: int, user_name: str, initial_message: str):
        """Notifica el inicio de una conversación"""
        msg = StreamMessage(
            type="conversation_start",
            user_id=user_id,
            user_name=user_name,
            content=initial_message,
            timestamp=time.time()
        )
        await self.broadcast_message(msg)

    async def send_text_block(self, user_id: int, user_name: str, text_block: str, metadata: dict = None):
        """Envía un bloque de texto generado por la IA"""
        msg = StreamMessage(
            type="text_block",
            user_id=user_id,
            user_name=user_name,
            content=text_block,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        await self.broadcast_message(msg)

    async def send_conversation_end(self, user_id: int, user_name: str):
        """Notifica el fin de una conversación"""
        msg = StreamMessage(
            type="conversation_end",
            user_id=user_id,
            user_name=user_name,
            content="",
            timestamp=time.time()
        )
        await self.broadcast_message(msg)

    async def send_audio_start(self, user_id: int, user_name: str):
        """Notifica el inicio de síntesis de audio"""
        msg = StreamMessage(
            type="audio_start",
            user_id=user_id,
            user_name=user_name,
            content="Iniciando síntesis de voz",
            timestamp=time.time()
        )
        await self.broadcast_message(msg)

    async def send_audio_end(self, user_id: int, user_name: str):
        """Notifica el fin de síntesis de audio"""
        msg = StreamMessage(
            type="audio_end",
            user_id=user_id,
            user_name=user_name,
            content="Síntesis de voz completada",
            timestamp=time.time()
        )
        await self.broadcast_message(msg)

    async def send_system_event(self, event_type: str, content: str, metadata: dict = None):
        """Envía un evento del sistema"""
        msg = StreamMessage(
            type=f"system_{event_type}",
            user_id=0,
            user_name="system",
            content=content,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        await self.broadcast_message(msg)

    def get_stats(self) -> dict:
        """Retorna estadísticas del servidor"""
        return {
            **self.stats,
            'server_running': self.server is not None,
            'clients_list': [f"{ws.remote_address[0]}:{ws.remote_address[1]}" for ws in self.clients]
        }