import env
from orchestrator import DiscordBotService

if __name__ == "__main__":
    bot = DiscordBotService(token=env.TOKEN)
    bot.run()
