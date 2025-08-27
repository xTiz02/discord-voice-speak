import logging
import asyncio
from typing import Dict, Iterator, Callable, Optional
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from m_agent.llm_Interface import LLMInterface

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Contexto de una conversación con un usuario"""
    user_id: int
    user_display_name: str
    fragments: list[str]
    last_activity: float


class ConversationManager:
    """
    Gestiona las conversaciones con múltiples usuarios y el flujo de streaming de respuestas.
    """

    def __init__(
            self,
            llm_engine: LLMInterface,
            silence_timeout: float = 4.5,
            max_workers: int = 3
    ):
        self.llm_engine = llm_engine
        self.silence_timeout = silence_timeout

        # Buffers y timers por usuario para acumular frases
        self._user_buffers: Dict[int, list] = {}
        self._user_timers: Dict[int, asyncio.Handle] = {}

        # Cola para procesar respuestas secuencialmente
        self._response_queue: asyncio.Queue = asyncio.Queue()
        self._response_processor_task: Optional[asyncio.Task] = None

        # Estado para manejar interrupciones
        self._is_processing = False
        self._processing_lock = asyncio.Lock()

        # Executor para tareas bloqueantes
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        # Callbacks para diferentes eventos
        self._on_response_start: Optional[Callable] = None
        self._on_response_block: Optional[Callable] = None
        self._on_response_complete: Optional[Callable] = None

        # Referencia al loop principal (se configura en initialize)
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        logger.info("ConversationManager inicializado")

    async def initialize(self):
        """Inicializa el gestor de conversaciones"""
        # Guardar referencia al loop principal
        self._main_loop = asyncio.get_running_loop()

        if self._response_processor_task is None:
            self._response_processor_task = asyncio.create_task(self._process_responses())
            logger.debug("Procesador de respuestas iniciado")

    async def shutdown(self):
        """Cierra el gestor de conversaciones"""
        if self._response_processor_task:
            self._response_processor_task.cancel()
            try:
                await self._response_processor_task
            except asyncio.CancelledError:
                pass

        self._executor.shutdown(wait=True)
        logger.info("ConversationManager cerrado")

    def set_callbacks(
            self,
            on_response_start: Optional[Callable] = None,
            on_response_block: Optional[Callable] = None,
            on_response_complete: Optional[Callable] = None
    ):
        """Configura los callbacks para eventos de respuesta"""
        self._on_response_start = on_response_start
        self._on_response_block = on_response_block
        self._on_response_complete = on_response_complete

    def add_fragment(self, user_id: int, user_display_name: str, fragment: str):
        """
        Agrega un fragmento de texto del usuario y maneja el timeout de silencio.
        Thread-safe: puede ser llamado desde cualquier thread.
        """
        if not fragment or not fragment.strip():
            return

        logger.debug(f"Agregando fragmento de {user_display_name}: {fragment}")

        # Acumular en buffer
        if user_id not in self._user_buffers:
            self._user_buffers[user_id] = []
        self._user_buffers[user_id].append(fragment.strip())

        # Cancelar temporizador previo
        if user_id in self._user_timers:
            self._user_timers[user_id].cancel()

        # Obtener el loop de manera thread-safe
        try:
            # Si estamos en el thread principal con loop activo
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Si estamos en otro thread, usar el loop principal guardado
            loop = self._main_loop if hasattr(self, '_main_loop') else None

        if loop is None:
            logger.error("No se pudo obtener el event loop para temporizador")
            return

        # Lanzar nuevo temporizador usando call_soon_threadsafe si es necesario
        if loop.is_running():
            if asyncio.current_task() is None:
                # Estamos en otro thread, usar thread-safe
                loop.call_soon_threadsafe(
                    lambda: self._schedule_timer(user_id, user_display_name, loop)
                )
            else:
                # Estamos en el thread del loop
                self._schedule_timer(user_id, user_display_name, loop)
        else:
            logger.error("El event loop no está corriendo")

    def _schedule_timer(self, user_id: int, user_display_name: str, loop):
        """Programa el temporizador de manera segura"""
        self._user_timers[user_id] = loop.call_later(
            self.silence_timeout,
            lambda: self._finalize_phrase_sync(user_id, user_display_name, loop)
        )

    def _finalize_phrase_sync(self, user_id: int, user_display_name: str, loop: asyncio.AbstractEventLoop):
        """Versión síncrona para call_later - thread safe"""
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._finalize_phrase(user_id, user_display_name),
                loop
            )
        else:
            logger.error("No se pudo programar _finalize_phrase - loop no disponible")

    async def _finalize_phrase(self, user_id: int, user_display_name: str):
        """Finaliza una frase y la envía para procesamiento"""
        fragments = self._user_buffers.get(user_id, [])

        if not fragments:
            return

        phrase = " ".join(fragments).strip()
        self._user_buffers[user_id] = []  # Limpiar buffer

        logger.debug(f"Frase final detectada de {user_display_name}: {phrase}")

        # Agregar a cola de procesamiento
        context = ConversationContext(
            user_id=user_id,
            user_display_name=user_display_name,
            fragments=[phrase],
            last_activity=asyncio.get_event_loop().time()
        )
        await self._response_queue.put(context)

    async def _process_responses(self):
        """Procesa las respuestas de manera secuencial para evitar conflictos"""
        logger.debug("Iniciando procesador de respuestas")

        while True:
            try:
                context = await self._response_queue.get()
                logger.debug(f"Procesando respuesta para {context.user_display_name}")

                await self._handle_conversation(context)
                self._response_queue.task_done()

            except asyncio.CancelledError:
                logger.debug("Procesador de respuestas cancelado")
                break
            except Exception as e:
                logger.exception(f"Error en procesador de respuestas: {e}")

    async def _handle_conversation(self, context: ConversationContext):
        """Maneja la conversación con streaming completo"""
        async with self._processing_lock:
            self._is_processing = True

            try:
                if self._on_response_start:
                    await self._execute_callback(self._on_response_start, context)

                # Preparar prompt
                phrase = " ".join(context.fragments)
                prompt = f"Usuario {context.user_display_name} dijo: {phrase}"

                logger.debug(f"Enviando prompt a LLM: {prompt}")

                # Generar respuesta en streaming
                await self._process_streaming_response(context, prompt)

            except Exception as e:
                logger.exception(f"Error en conversación con {context.user_display_name}: {e}")
                # Enviar respuesta de fallback
                if self._on_response_block:
                    await self._execute_callback(
                        self._on_response_block,
                        context,
                        "Disculpa, hubo un problema técnico. ¿Puedes intentar de nuevo?"
                    )
            finally:
                self._is_processing = False
                if self._on_response_complete:
                    await self._execute_callback(self._on_response_complete, context)

    async def _process_streaming_response(self, context: ConversationContext, prompt: str):
        """Procesa la respuesta streaming del LLM"""
        try:
            # Ejecutar streaming en executor para evitar bloquear el loop
            stream_iterator = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                lambda: self.llm_engine.chat_stream(prompt)
            )

            # Procesar bloques conforme llegan
            for block in stream_iterator:
                if block and block.strip():
                    logger.debug(f"Bloque recibido: {block}")

                    if self._on_response_block:
                        await self._execute_callback(self._on_response_block, context, block)

        except Exception as e:
            logger.exception(f"Error en streaming de respuesta: {e}")
            raise

    async def _execute_callback(self, callback: Callable, *args, **kwargs):
        """Ejecuta un callback de manera segura"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Error ejecutando callback: {e}")