import logging
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, ChatSession, HarmCategory, HarmBlockThreshold
from typing import Iterator

from m_agent.llm_Interface import LLMInterface

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class VertexAgentEngine(LLMInterface):
    def __init__(
            self,
            project_id: str,
            location: str,
            model_name: str,
            system_instruction: str = None,
            temperature: float = 0.7,
            max_output_tokens: int = 128,
    ):
        """
        Inicializa un agente con sesión persistente en VertexAI.

        Args:
            project_id (str): Google Cloud project ID
            location (str): región (ej. "us-central1")
            model_name (str): nombre del modelo (ej. "gemini-1.5-pro-001")
            system_instruction (str): prompt de sistema opcional
            temperature (float): creatividad de la respuesta
            max_output_tokens (int): longitud máxima de salida
        """
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        self.system_instruction = system_instruction

        # Inicializa Vertex
        vertexai.init(project=project_id, location=location)

        # Configuración de seguridad más permisiva
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }

        # Configura modelo y sesión de chat
        self.model = GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
            generation_config=GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
            safety_settings=self.safety_settings
        )

        # Sesión persistente (recuerda contexto) con validación deshabilitada
        self.chatSession: ChatSession = self.model.start_chat(
            response_validation=False
        )

        # Respuestas por defecto para diferentes tipos de errores
        self.fallback_responses = [
            "Entiendo, ¿en qué más puedo ayudarte?",
            "Interesante, cuéntame más al respecto.",
            "Perfecto, ¿hay algo específico que te gustaría saber?",
            "Muy bien, ¿cómo puedo asistirte hoy?",
            "Entendido, ¿tienes alguna pregunta para mí?"
        ]
        self.fallback_index = 0

    def chat_stream(self, prompt: str) -> Iterator[str]:
        """
        Envía un mensaje al modelo y obtiene respuesta en streaming.

        Args:
            prompt (str): mensaje del usuario

        Yields:
            str: bloques de texto conforme se van generando
        """
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                print(f"[DEBUG] VertexAgentEngine.chat_stream() Intento {attempt + 1} → Prompt: {prompt}")

                # Generar respuesta en streaming
                responses = self.chatSession.send_message(prompt, stream=True)

                has_content = False
                for response in responses:
                    if hasattr(response, 'text') and response.text and response.text.strip():
                        has_content = True
                        text_block = response.text.strip()
                        print(f"[DEBUG] VertexAgentEngine.chat_stream() → Bloque recibido: {text_block}")
                        yield text_block

                if has_content:
                    return  # Éxito, salir del bucle de reintentos
                else:
                    print(f"[WARNING] Respuesta vacía en intento {attempt + 1}")
                    if attempt == max_retries:
                        yield self._get_fallback_response(prompt)
                        return

            except Exception as e:
                error_msg = str(e).lower()
                print(f"[ERROR] VertexAgentEngine.chat_stream() intento {attempt + 1} falló: {e}")

                # Manejo específico de errores
                if "finish reason: 2" in error_msg or "safety" in error_msg:
                    print("[DEBUG] Error de filtro de seguridad detectado")
                    if attempt < max_retries:
                        # Intentar con un prompt reformulado
                        prompt = self._rephrase_prompt(prompt)
                        print(f"[DEBUG] Reformulando prompt: {prompt}")
                        continue
                    else:
                        yield self._get_safety_fallback_response()
                        return

                elif "model response did not complete" in error_msg:
                    print("[DEBUG] Respuesta incompleta del modelo")
                    if attempt < max_retries:
                        continue
                    else:
                        yield self._get_fallback_response(prompt)
                        return

                elif attempt == max_retries:
                    # Último intento fallido
                    print("[ERROR] Todos los intentos fallaron, usando respuesta de fallback")
                    yield self._get_generic_fallback_response()
                    return

        # Si llegamos aquí, algo salió muy mal
        yield self._get_generic_fallback_response()

    def chat(self, prompt: str) -> str:
        """
        Envía un mensaje al modelo y obtiene respuesta en texto plano.
        Maneja errores de filtros de seguridad y otros problemas de Vertex AI.

        Args:
            prompt (str): mensaje del usuario

        Returns:
            str: respuesta generada por el modelo o respuesta de fallback
        """
        # Recopilar todos los bloques del stream
        blocks = list(self.chat_stream(prompt))
        return " ".join(blocks) if blocks else self._get_generic_fallback_response()

    def _rephrase_prompt(self, original_prompt: str) -> str:
        """
        Reformula el prompt para evitar filtros de seguridad
        """
        # Extraer solo el contenido del usuario
        if "Usuario" in original_prompt and "dijo:" in original_prompt:
            try:
                user_content = original_prompt.split("dijo:", 1)[1].strip()
                return f"El usuario mencionó: {user_content}. Responde de manera amigable."
            except:
                pass

        return f"Responde de manera conversacional a: {original_prompt}"

    def _get_fallback_response(self, prompt: str) -> str:
        """
        Genera una respuesta contextual de fallback basada en el prompt
        """
        prompt_lower = prompt.lower()

        if any(word in prompt_lower for word in ["hola", "saludos", "buenos", "hi", "hello"]):
            return "¡Hola! Es un gusto conversar contigo. ¿En qué puedo ayudarte hoy?"

        elif any(word in prompt_lower for word in ["cómo", "como", "qué", "que", "cuál", "cual"]):
            return "Es una buena pregunta. Me gustaría ayudarte con más información. ¿Podrías ser más específico?"

        elif any(word in prompt_lower for word in ["gracias", "thanks", "thank"]):
            return "¡De nada! Estoy aquí para ayudarte cuando lo necesites."

        elif any(word in prompt_lower for word in ["adiós", "chao", "bye", "hasta"]):
            return "¡Hasta pronto! Ha sido un placer conversar contigo."

        else:
            return self._get_generic_fallback_response()

    def _get_safety_fallback_response(self) -> str:
        """
        Respuesta específica para filtros de seguridad
        """
        responses = [
            "Entiendo tu mensaje. ¿Hay algo más en lo que pueda ayudarte?",
            "Perfecto, ¿qué más te gustaría saber?",
            "Muy bien, estoy aquí para asistirte con lo que necesites.",
        ]
        response = responses[self.fallback_index % len(responses)]
        self.fallback_index += 1
        return response

    def _get_generic_fallback_response(self) -> str:
        """
        Respuesta genérica cuando otros métodos fallan
        """
        response = self.fallback_responses[self.fallback_index % len(self.fallback_responses)]
        self.fallback_index += 1
        print(f"[DEBUG] Usando respuesta de fallback: {response}")
        return response

    def reset_session(self):
        """
        Reinicia la sesión de chat en caso de problemas persistentes
        """
        try:
            print("[DEBUG] Reiniciando sesión de chat de VertexAI")
            self.chatSession = self.model.start_chat(response_validation=False)
            print("[DEBUG] Sesión reiniciada correctamente")
        except Exception as e:
            print(f"[ERROR] Error al reiniciar sesión: {e}")

    def get_session_history_length(self) -> int:
        """
        Obtiene la longitud del historial de la sesión actual
        """
        try:
            return len(self.chatSession.history)
        except:
            return 0