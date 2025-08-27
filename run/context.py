from m_agent.vertex_llm import VertexAgentEngine
from stt.stt_google import GoogleSTTEngine
from tts.tts_google import GoogleTTSEngine
import env


class ServiceContext:
    """
    Contexto de servicios configurables para el bot.
    Permite intercambiar implementaciones fácilmente.
    """

    def __init__(self, loop=None):
        self.loop = loop

        # Motor de Speech-to-Text
        self.stt_engine = GoogleSTTEngine(language="es-PE")

        # Motor de Text-to-Speech con configuración optimizada para streaming
        self.tts_engine = GoogleTTSEngine(
            language="es-US",
            voice_name="es-US-Journey-F",
            sample_rate_hz=48000,
            speaking_rate=1.2,  # Velocidad ligeramente más rápida
            loop=loop
        )

        # Motor de LLM con soporte para streaming
        self.llm_engine = VertexAgentEngine(
            project_id=env.PROJECT_ID,
            location=env.REGION,
            model_name="gemini-2.0-flash-lite",
            temperature=0.7,
            max_output_tokens=1024,  # Aumentado para respuestas más largas
            system_instruction=self._get_system_instruction(),
        )

    def set_loop(self, loop):
        """Configura el event loop para los servicios que lo requieren"""
        self.loop = loop
        self.stt_engine.loop = loop if hasattr(self.stt_engine, 'loop') else None
        self.tts_engine.loop = loop

    def _get_system_instruction(self) -> str:
        """
        Retorna las instrucciones del sistema para la IA.
        Centralizado aquí para fácil modificación.
        """
        return """Eres una IA conversacional en un canal de Discord. 
        Responde de manera natural, amigable y concisa. 
        Tus respuestas deben ser apropiadas para conversación por voz.
        Evita usar emojis o formato especial ya que será convertido a voz.
        Mantén las respuestas relativamente cortas para mejor fluidez en la conversación."""

    def update_llm_config(
            self,
            temperature: float = None,
            max_output_tokens: int = None,
            system_instruction: str = None
    ):
        """
        Actualiza la configuración del LLM dinámicamente.
        Útil para ajustes en tiempo real.
        """
        if any([temperature is not None, max_output_tokens is not None, system_instruction is not None]):
            # Reinicializar con nueva configuración
            current_config = {
                'project_id': self.llm_engine.project_id,
                'location': self.llm_engine.location,
                'model_name': self.llm_engine.model_name,
                'temperature': temperature if temperature is not None else 0.7,
                'max_output_tokens': max_output_tokens if max_output_tokens is not None else 1024,
                'system_instruction': system_instruction if system_instruction is not None else self._get_system_instruction(),
            }

            self.llm_engine = VertexAgentEngine(**current_config)

    def update_tts_config(
            self,
            language: str = None,
            voice_name: str = None,
            speaking_rate: float = None
    ):
        """
        Actualiza la configuración del TTS dinámicamente.
        """
        if any([language is not None, voice_name is not None, speaking_rate is not None]):
            current_config = {
                'language': language if language is not None else self.tts_engine.default_language,
                'voice_name': voice_name if voice_name is not None else self.tts_engine.default_voice_name,
                'sample_rate_hz': self.tts_engine.sample_rate_hz,
                'speaking_rate': speaking_rate if speaking_rate is not None else self.tts_engine.speaking_rate,
                'loop': self.loop
            }

            self.tts_engine = GoogleTTSEngine(**current_config)

    def get_config_summary(self) -> dict:
        """
        Retorna un resumen de la configuración actual de todos los servicios.
        Útil para debugging y monitoreo.
        """
        return {
            'stt': {
                'engine': type(self.stt_engine).__name__,
                'language': getattr(self.stt_engine, 'language', 'Unknown')
            },
            'tts': {
                'engine': type(self.tts_engine).__name__,
                'language': self.tts_engine.default_language,
                'voice': self.tts_engine.default_voice_name,
                'sample_rate': self.tts_engine.sample_rate_hz,
                'speaking_rate': self.tts_engine.speaking_rate
            },
            'llm': {
                'engine': type(self.llm_engine).__name__,
                'model': self.llm_engine.model_name,
                'project': self.llm_engine.project_id,
                'location': self.llm_engine.location,
                'history_length': self.llm_engine.get_session_history_length()
            }
        }