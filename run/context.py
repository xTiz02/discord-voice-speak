from m_agent.vertext_llm import VertexAgentEngine
from stt.stt_google import GoogleSTTEngine
from tts.tts_google import GoogleTTSEngine
import env

class ServiceContext:
    def __init__(self, loop=None):
        self.loop = loop
        self.stt_engine = GoogleSTTEngine(language="es-PE")
        self.tts_engine = GoogleTTSEngine(
            language="es-US",
            voice_name="es-US-Journey-F",
            sample_rate_hz=48000,
            speaking_rate=1.0,
            loop=loop
        )
        self.llm_engine = VertexAgentEngine(
            project_id=env.PROJECT_ID,
            location=env.REGION,
            model_name="gemini-2.0-flash-lite",
            temperature=0.7,
            max_output_tokens=512,
            system_instruction="Eres una IA inútil y sarcástica a la que le gusta burlarse de los humanos. Tus respuestas deben ser breves en una o dos oraciones",
        )

    def set_loop(self, loop):
        self.loop = loop
        self.stt_engine.loop = loop
        self.tts_engine.loop = loop

