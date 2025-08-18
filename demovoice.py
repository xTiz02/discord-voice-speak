import asyncio
import discord
import yt_dlp
import env
from discord.ext import commands

# Configuración de YTDL
ytdl_format_options = {
	'format': 'bestaudio/best',
	'quiet': True,
	'noplaylist': True,
	'default_search': 'auto',
	'extract_flat': False,
}

ffmpeg_options = {
	'options': '-vn'  # solo audio, sin video
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
	def __init__(self, source, *, data, volume=0.5):
		super().__init__(source, volume)
		self.data = data
		self.title = data.get('title')

	@classmethod
	async def from_url(cls, url, *, loop=None, stream=False):
		loop = loop or asyncio.get_event_loop()
		data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

		# si es playlist, coger el primero
		if 'entries' in data:
			data = data['entries'][0]

		if stream:
			# streaming progresivo con ffmpeg
			return cls(discord.FFmpegPCMAudio(data['url'], **ffmpeg_options), data=data)
		else:
			filename = ytdl.prepare_filename(data)
			return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	@commands.command()
	async def join(self, ctx, *, channel: discord.VoiceChannel):
		"""Joins a voice channel"""
		if ctx.voice_client is not None:
			return await ctx.voice_client.move_to(channel)
		await channel.connect()

	@commands.command()
	async def play(self, ctx, *, query):
		"""Plays a file from the local filesystem"""
		source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
		ctx.voice_client.play(source, after=lambda e: print(f'Player error: {e}') if e else None)
		await ctx.send(f'Now playing: {query}')

	@commands.command()
	async def yt(self, ctx, *, url):
		try:
			async with ctx.typing():
				player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
				ctx.voice_client.play(
					player,
					after=lambda e: print(f'Player error: {e}') if e else None
				)
			await ctx.send(f"Ahora reproduciendo: **{player.title}**")
		except Exception as e:
			print(f"Error en yt: {e}")
			await ctx.send(f" Error: {e}")

	@commands.command()
	async def stream(self, ctx, *, url):
		"""Streams from a URL without pre-downloading"""
		async with ctx.typing():
			player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
			ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)

		await ctx.send(f'Now streaming: **{player.title}**')

	@commands.command()
	async def volume(self, ctx, volume: int):
		"""Changes the player's volume"""
		if ctx.voice_client is None:
			return await ctx.send("Not connected to a voice channel.")
		ctx.voice_client.source.volume = volume / 100
		await ctx.send(f"Changed volume to {volume}%")

	@commands.command()
	async def stop(self, ctx):
		"""Stops and disconnects the bot from voice"""
		await ctx.voice_client.disconnect()

	@play.before_invoke
	@yt.before_invoke
	@stream.before_invoke
	async def ensure_voice(self, ctx):
		if ctx.voice_client is None:
			if ctx.author.voice:
				await ctx.author.voice.channel.connect()
			else:
				await ctx.send("You are not connected to a voice channel.")
				raise commands.CommandError("Author not connected to a voice channel.")
		elif ctx.voice_client.is_playing():
			ctx.voice_client.stop()


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
	command_prefix="$",
	description='Relatively simple music bot example',
	intents=intents,
)

@bot.command()
async def test(ctx, *args):
	if len(args) == 0:
		raise Exception("Error controlado")
	response = ' '.join(args)
	await ctx.send(response)

@bot.event
async def on_ready():
	assert bot.user is not None
	print(f'Logged in as {bot.user} (ID: {bot.user.id})')
	print('------')


async def main():
	async with bot:
		await bot.add_cog(Music(bot))
		await bot.start(env.TOKEN)


asyncio.run(main())
