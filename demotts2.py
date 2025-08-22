import simpleaudio as sa  # Para reproducción de audio en tiempo real
from google.cloud import texttospeech
import pyaudio
import itertools  # Para manejar iterables

def run_streaming_tts_quickstart():
    """Synthesizes and plays speech from a stream of input text."""
    client = texttospeech.TextToSpeechClient()

    # Selección del tipo de archivo de audio
    audio_config = texttospeech.StreamingAudioConfig(
        speaking_rate=1.2,  # velocidad de la voz
    )

    streaming_config = texttospeech.StreamingSynthesizeConfig(
        voice=texttospeech.VoiceSelectionParams(
            name="es-US-Journey-F", language_code="es-US"
        ),
        streaming_audio_config=audio_config
    )

    # Configuración inicial de la solicitud
    config_request = texttospeech.StreamingSynthesizeRequest(
        streaming_config=streaming_config,

    )

    # Generador de solicitudes
    def request_generator():
        # yield texttospeech.StreamingSynthesizeRequest(input=texttospeech.StreamingSynthesisInput(text="Hola, soy una prueba de texto a voz en tiempo real. "))
        yield texttospeech.StreamingSynthesizeRequest(input=texttospeech.StreamingSynthesisInput(text="Como parte de esta prueba, estoy generando audio en tiempo real. Recuerda que la calidad del audio puede variar dependiendo de la conexión y otros factores. ¿Todo bien? . Ademas, estoy probando la capacidad de respuesta de este sistema. No obstante , es importante mencionar que la calidad del audio puede variar dependiendo de la conexión y otros factores. ¿Todo bien? . Ademas, estoy probando la capacidad de respuesta de este sistema. No obstante , es importante mencionar que la calidad del audio puede variar dependiendo de la conexión y otros factores. "))
        # yield texttospeech.StreamingSynthesizeRequest(input=texttospeech.StreamingSynthesisInput(text="¿Todo bien? . Ademas, estoy probando la capacidad de respuesta de este sistema. No obstante , es importante mencionar que la calidad del audio puede variar dependiendo de la conexión y otros factores. "))
        # yield texttospeech.StreamingSynthesizeRequest(input=texttospeech.StreamingSynthesisInput(text="Espero que sí. Gracias por tu paciencia mientras realizo esta prueba. "))

    # Llamada a la API de streaming
    streaming_responses = client.streaming_synthesize(
        itertools.chain([config_request], request_generator())
    )

    p = pyaudio.PyAudio()

    # Open a stream
    stream = p.open(format=pyaudio.paInt16,  # Assuming 16-bit audio. Adjust if needed.
                    channels=1,  # Assuming mono audio. Adjust if needed.
                    rate=24000,
                    # Assuming 22050 Hz sample rate.  Adjust if needed.  Get this from your response if possible!
                    output=True)
    # Procesar respuestas y reproducir audio en tiempo real por partes
    for idx, response in enumerate(streaming_responses):
        audio_content = response.audio_content  # Datos de audio
        print(f"Fragmento {idx + 1} - Audio content size in bytes is: {len(audio_content)}")
        if audio_content:
            # Play the audio chunk
            try:
                stream.write(audio_content)
            except Exception as e:
                print(f"Error playing audio chunk {idx + 1}: {e}")

if __name__ == "__main__":
    run_streaming_tts_quickstart()
