import env
from run.orchestrator import ThreadSafeDiscordBotService

if __name__ == "__main__":
    bot = ThreadSafeDiscordBotService(token=env.TOKEN)
    bot.run()