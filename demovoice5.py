import asyncio
from collections import defaultdict

import discord
from discord.ext import commands, voice_recv
import speech_recognition as sr
import env

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="$", intents=intents)

# Buffer de transcripciones por usuario
user_buffers: dict[int, list[str]] = {}
silence_timers = {}
loop = asyncio.get_event_loop()
def make_recognizer():
    r = sr.Recognizer()
    r.energy_threshold = 100
    r.dynamic_energy_threshold = True
    r.pause_threshold = 5.0
    r.phrase_threshold = 0.2
    r.non_speaking_duration = 0.8
    return r


# ----------- Callbacks -----------
def process_audio(recognizer: sr.Recognizer, audio: sr.AudioData, user):
    """Convierte audio -> texto y acumula en el buffer del usuario"""
    try:
        text = recognizer.recognize_google(audio, language="es-PE", show_all=False)
        if text:
            uid = user.id
            if uid not in user_buffers:
                user_buffers[uid] = []
            user_buffers[uid].append(text)
        return None  # no mandamos al bot todavía
    except sr.UnknownValueError:
        return None
    except Exception as e:
        print(f"[ERROR] en reconocimiento de {user.display_name}: {e}")
    return None


def flush_user_buffer(user: discord.Member):
    """Concatena y limpia el buffer de un usuario"""
    uid = user.id
    if uid in user_buffers and user_buffers[uid]:
        full_text = " ".join(user_buffers[uid])
        del user_buffers[uid]
        return full_text
    return None


# ----------- Sink personalizado con logs -----------
class LoggingSpeechRecognitionSink(voice_recv.extras.speechrecognition.SpeechRecognitionSink):
    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member):
        print(f"🎤 {member.display_name} empezó a hablar")

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member):
      print(f"🔇 {member.display_name} dejó de hablar")

      # Si ya había un timer corriendo, cancelarlo
      if member in silence_timers and not silence_timers[member].done():
        silence_timers[member].cancel()

      # Nuevo timer para cerrar buffer después de silencio prolongado
      async def silence_wait():
        try:
          await asyncio.sleep(1.5)  # tiempo de silencio para confirmar fin de frase
          full_text = flush_user_buffer(member)
          if full_text:
            got_text(member, full_text)
        except asyncio.CancelledError:
          pass

      silence_timers[member] = loop.create_task(silence_wait())

    @voice_recv.AudioSink.listener()
    def on_voice_member_disconnect(self, member: discord.Member, ssrc: int | None):
        print(f"❌ {member.display_name} se desconectó del canal (ssrc={ssrc})")


# ----------- Acción al tener el texto completo -----------
def got_text(user, text: str):
    """Acción cuando ya tenemos un turno completo del usuario"""
    print(f"[DIÁLOGO COMPLETO] {user.display_name}: {text}")
    # Aquí llamas a tu agente/IA y generas la respuesta
    # Ej: enviar al canal de texto o responder por voz


# ----------- Comandos -----------
@bot.command()
async def join(ctx):
    if ctx.author.voice:
        vc: voice_recv.VoiceRecvClient = await ctx.author.voice.channel.connect(
            cls=voice_recv.VoiceRecvClient
        )
        sink = LoggingSpeechRecognitionSink(
            process_cb=process_audio,
            text_cb=lambda u, t: None,  # desactivamos text_cb directo
            default_recognizer="google",
            phrase_time_limit=30,
            recognizer_factory=make_recognizer,
        )
        vc.listen(sink)
        await ctx.send("Estoy escuchando de forma optimizada 🎧")
    else:
        await ctx.send("No estás en un canal de voz.")


@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Me salí del canal de voz.")
    else:
        await ctx.send("No estoy en ningún canal de voz.")


bot.run(env.TOKEN)
