"""Synthesizes speech from a stream of input text."""
from google.cloud import texttospeech

client = texttospeech.TextToSpeechClient()

streaming_config = texttospeech.StreamingSynthesizeConfig(
    voice=texttospeech.VoiceSelectionParams(
        name="en-US-Chirp3-HD-Charon",
        language_code="en-US",
    )
)

config_request = texttospeech.StreamingSynthesizeRequest(
    streaming_config=streaming_config
)

text_iterator = [
    "Hello there. ",
    "How are you ",
    "today? It's ",
    "such nice weather outside.",
]

# Request generator. Consider using Gemini or another LLM with output streaming as a generator.
def request_generator():
    yield config_request
    for text in text_iterator:
        yield texttospeech.StreamingSynthesizeRequest(
            input=texttospeech.StreamingSynthesisInput(text=text)
        )

streaming_responses = client.streaming_synthesize(request_generator())

for response in streaming_responses:
    print(f"Audio content size in bytes is: {len(response.audio_content)}")




#pip install google-cloud-texttospeech