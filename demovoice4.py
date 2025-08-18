import discord
from discord.ext import commands, voice_recv
import speech_recognition as sr
import env

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True	# Necesario para recibir eventos de voz
bot = commands.Bot(command_prefix="$", intents=intents)



def make_recognizer():
    r = sr.Recognizer()
    r.energy_threshold = 100 # Nivel mínimo de volumen para detectar voz (ajusta según pruebas)
    r.dynamic_energy_threshold = True  # Se adapta al ruido de fondo
    r.pause_threshold = 5.0 # Tiempo de silencio antes de cortar frase
    r.phrase_threshold = 0.2 # Tiempo mínimo de voz para considerarlo frase
    r.non_speaking_duration = 0.8 # Silencios muy cortos los ignora
    return r

# ----------- Callbacks -----------
def process_audio(recognizer: sr.Recognizer, audio: sr.AudioData, user):
    """Convierte audio -> texto usando el motor configurado"""
    try:
        # puedes usar recognize_google, recognize_whisper, recognize_azure, etc.
        text = recognizer.recognize_google(audio, language='es-PE', show_all=False) # Whisper (necesita openai-whisper)
        # text = recognizer.recognize_google(audio) # Google gratis
        return text
    except sr.UnknownValueError:
        print(f"[DEBUG] No entendí lo que dijo {user.display_name}")
    except Exception as e:
        print(f"[ERROR] en reconocimiento de {user.display_name}: {e}")
    return None

def got_text(user, text: str):
    """Qué hacer con el texto ya reconocido"""
    print(f"[TRANSCRIPCIÓN] {user.display_name}: {text}")

# ----------- Comandos -----------
@bot.command()
async def join(ctx):
    """Hace que el bot entre al canal de voz y empiece a escuchar"""
    if ctx.author.voice:
        vc: voice_recv.VoiceRecvClient = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)

        sink = voice_recv.extras.speechrecognition.SpeechRecognitionSink(
            process_cb=process_audio,
            text_cb=got_text,
            default_recognizer="google",  # "google", "azure", etc.
            phrase_time_limit=30,
			recognizer_factory=make_recognizer
        )

        vc.listen(sink)
        await ctx.send("Estoy escuchando y transcribiendo con Whisper.")
    else:
        await ctx.send("No estás en un canal de voz.")

@bot.command()
async def leave(ctx):
    """Hace que el bot salga del canal de voz"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Me salí del canal de voz.")
    else:
        await ctx.send("No estoy en ningún canal de voz.")

# ----------- Run -----------
bot.run(env.TOKEN)
