import time

from config import ConfigReader
from rich_presence.apps.PlexRichPresence import PlexRichPresence


class PlexConfig:
    extraLogging = True
    timeRemaining = False

    def __init__(self, server_name="", username="", password="", token="", listen_for_user="",
                 blacklisted_libraries=None, whitelisted_libraries=None, client_id=""):
        self.serverName = server_name
        self.username = username
        self.password = password
        self.token = token
        self.listenForUser = (username if listen_for_user == "" else listen_for_user).lower()
        self.blacklistedLibraries = blacklisted_libraries
        self.whitelistedLibraries = whitelisted_libraries
        self.clientID = client_id


discordRichPresencePlexInstances = []
for config in ConfigReader.get_configs():
    discordRichPresencePlexInstances.append(PlexRichPresence(config))
try:
    for discordRichPresencePlexInstance in discordRichPresencePlexInstances:
        discordRichPresencePlexInstance.run()
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    for discordRichPresencePlexInstance in discordRichPresencePlexInstances:
        discordRichPresencePlexInstance.reset()
except Exception as e:
    print("Error: " + str(e))
