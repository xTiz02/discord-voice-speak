"""
Ejemplo de integración del WebSocketService con el bot de Discord.
Muestra cómo modificar el orchestrator para enviar eventos via WebSocket.
"""

import asyncio
from run.orchestrator import DiscordBotService
from services.websocket.websocket_service import WebSocketService
from services.conversation_manager import ConversationContext
from services.audio_manager import AudioContext
import env


class WebSocketEnabledDiscordBot(DiscordBotService):
    """
    Extensión del bot de Discord con capacidades de WebSocket.
    """

    def __init__(self, token: str, websocket_host: str = "localhost", websocket_port: int = 8765, prefix: str = "$"):
        super().__init__(token, prefix)

        # Servicio de WebSocket
        self.websocket_service = WebSocketService(websocket_host, websocket_port)

    async def _setup_hook(self):
        """Configuración inicial incluyendo WebSocket"""
        await super()._setup_hook()

        # Iniciar servidor WebSocket
        await self.websocket_service.start_server()

        # Reconfigurar callbacks para incluir WebSocket
        self._setup_websocket_callbacks()

    def _setup_websocket_callbacks(self):
        """Reconfigura los callbacks para incluir eventos WebSocket"""

        # Llamar setup original
        super()._setup_callbacks()

        # Agregar funcionalidad WebSocket a los callbacks existentes
        original_response_start = self.conversation_manager._on_response_start
        original_response_block = self.conversation_manager._on_response_block
        original_response_complete = self.conversation_manager._on_response_complete
        original_speech_start = self.audio_manager._on_speech_start
        original_speech_end = self.audio_manager._on_speech_end

        # Wrapper para callbacks con WebSocket
        async def enhanced_response_start(context: ConversationContext):
            if original_response_start:
                await original_response_start(context)

            await self.websocket_service.send_conversation_start(
                context.user_id,
                context.user_display_name,
                " ".join(context.fragments)
            )

        async def enhanced_response_block(context: ConversationContext, text_block: str):
            if original_response_block:
                await original_response_block(context, text_block)

            await self.websocket_service.send_text_block(
                context.user_id,
                context.user_display_name,
                text_block,
                metadata={
                    'block_length': len(text_block),
                    'timestamp': context.last_activity
                }
            )

        async def enhanced_response_complete(context: ConversationContext):
            if original_response_complete:
                await original_response_complete(context)

            await self.websocket_service.send_conversation_end(
                context.user_id,
                context.user_display_name
            )

        async def enhanced_speech_start(audio_context: AudioContext):
            if original_speech_start:
                await original_speech_start(audio_context)

            await self.websocket_service.send_audio_start(
                audio_context.user_id,
                audio_context.user_display_name
            )

        async def enhanced_speech_end(audio_context: AudioContext):
            if original_speech_end:
                await original_speech_end(audio_context)

            await self.websocket_service.send_audio_end(
                audio_context.user_id,
                audio_context.user_display_name
            )

        # Actualizar callbacks
        self.conversation_manager.set_callbacks(
            on_response_start=enhanced_response_start,
            on_response_block=enhanced_response_block,
            on_response_complete=enhanced_response_complete
        )

        self.audio_manager.set_callbacks(
            on_speech_start=enhanced_speech_start,
            on_speech_end=enhanced_speech_end
        )

    async def cleanup(self):
        """Limpieza incluyendo WebSocket"""
        # Cerrar WebSocket primero
        if self.websocket_service:
            await self.websocket_service.stop_server()

        # Luego limpieza normal
        await super().cleanup()

    # Comandos adicionales para WebSocket
    def _register_websocket_commands(self):
        """Registra comandos específicos para WebSocket"""

        @self.bot.command()
        async def ws_stats(ctx):
            """Muestra estadísticas del WebSocket"""
            stats = self.websocket_service.get_stats()

            stats_msg = "📡 **Estadísticas WebSocket:**\n"
            stats_msg += f"• Servidor activo: {'✅' if stats['server_running'] else '❌'}\n"
            stats_msg += f"• Clientes conectados: {stats['clients_connected']}\n"
            stats_msg += f"• Total conexiones: {stats['total_connections']}\n"
            stats_msg += f"• Mensajes enviados: {stats['messages_sent']}\n"
            stats_msg += f"• Errores: {stats['errors']}\n"

            if stats['clients_list']:
                stats_msg += f"• Clientes: {', '.join(stats['clients_list'])}"

            await ctx.send(stats_msg)

        @self.bot.command()
        async def ws_test(ctx):
            """Envía un mensaje de prueba via WebSocket"""
            await self.websocket_service.send_system_event(
                "test",
                f"Mensaje de prueba enviado por {ctx.author.display_name}",
                metadata={"command_channel": str(ctx.channel), "guild": str(ctx.guild)}
            )
            await ctx.send("📡 Mensaje de prueba enviado via WebSocket")


# Ejemplo de uso
if __name__ == "__main__":
    bot = WebSocketEnabledDiscordBot(
        token=env.TOKEN,
        websocket_host="localhost",
        websocket_port=8765
    )
    bot.run()