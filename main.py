import discord
from discord.ext import commands
import requests
import env

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='$', intents=intents)


@bot.command()
async def test(ctx, *args):
	if (len(args) == 0):
		raise Exception("Error controlado")
	response = ' '.join(args)
	await ctx.send(response)


@bot.command()
async def join(ctx):
	if ctx.author.voice:
		channel = ctx.author.voice.channel
		await channel.connect()
		await ctx.send(f"Me uní al canal: {channel.name}")
	else:
		await ctx.send("Debes estar en un canal de voz para usar este comando.")


@bot.command()
async def stop(self, ctx):
	await ctx.voice_client.disconnect()


@test.error
async def test_error(ctx, error):
	if isinstance(error, commands.CommandInvokeError):
		await ctx.send(f'{str(error)}')
	else:
		await ctx.send('An unexpected error occurred: ' + str(error))


@bot.event
async def on_ready():
	print(f'Logged in as {bot.user.name} - {bot.user.id}')
	print('------')


bot.run(env.TOKEN)

# @bot.command()
# async def repeat(ctx, times: int, content='repeating...'):
#     """Repeats a message multiple times."""
#     for i in range(times):
#         await ctx.send(content)
#
#
# @bot.command()
# async def joined(ctx, member: discord.Member):
#     """Says when a member joined."""
#     # Joined at can be None in very bizarre cases so just handle that as well
#     if member.joined_at is None:
#         await ctx.send(f'{member} has no join date.')
#     else:
#         await ctx.send(f'{member} joined {discord.utils.format_dt(member.joined_at)}')
