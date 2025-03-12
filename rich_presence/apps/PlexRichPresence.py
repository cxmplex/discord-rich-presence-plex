import datetime
import hashlib
import threading
import time

import plexapi

from util import TextUtil
from .. import RichPresence as discordRichPresence


class PlexRichPresence(discordRichPresence):
    productName = "Plex Media Server"
    stopTimerInterval = 5
    stopTimer2Interval = 35
    checkConnectionTimerInterval = 60
    maximumIgnores = 3
    lock = threading.Semaphore(value=1)

    def __init__(self, plex_config):
        self.plexConfig = plex_config
        self.instanceID = hashlib.md5(str(id(self)).encode("UTF-8")).hexdigest()[:5]
        super().__init__(plex_config.clientID, self)
        self.plexAccount = None
        self.plexServer = None
        self.isServerOwner = False
        self.plexAlertListener = None
        self.lastState = None
        self.lastSessionKey = None
        self.lastRatingKey = None
        self.stopTimer = None
        self.stopTimer2 = None
        self.checkConnectionTimer = None
        self.ignoreCount = 0

    def run(self):
        self.reset()
        connected = False
        while not connected:
            try:
                if self.plexConfig.token:
                    self.plexAccount = plexapi.myplex.MyPlexAccount(self.plexConfig.username,
                                                                    token=self.plexConfig.token)
                else:
                    self.plexAccount = plexapi.myplex.MyPlexAccount(self.plexConfig.username, self.plexConfig.password)
                self.log("Logged in as Plex User \"" + self.plexAccount.username + "\"")
                self.plexServer = None
                for resource in self.plexAccount.resources():
                    if resource.product == self.productName and resource.name == self.plexConfig.serverName:
                        self.plexServer = resource.connect()
                        try:
                            self.plexServer.account()
                            self.isServerOwner = True
                        except:
                            pass
                        self.log("Connected to " + self.productName + " \"" + self.plexConfig.serverName + "\"")
                        self.plexAlertListener = self.plexServer.startAlertListener(self.on_plex_server_alert)
                        self.log(
                            "Listening for PlaySessionStateNotification alerts from user \"" + self.plexConfig.listenForUser + "\"")
                        if self.checkConnectionTimer:
                            self.checkConnectionTimer.cancel()
                            self.checkConnectionTimer = None
                        self.checkConnectionTimer = threading.Timer(self.checkConnectionTimerInterval,
                                                                    self.check_connection)
                        self.checkConnectionTimer.start()
                        connected = True
                        break
                if not self.plexServer:
                    self.log(self.productName + " \"" + self.plexConfig.serverName + "\" not found")
                    break
            except Exception as e:
                self.log("Failed to connect to Plex: " + str(e))
                self.log("Reconnecting in 10 seconds")
                time.sleep(10)

    def reset(self):
        if self.running:
            self.stop()
        self.plexAccount, self.plexServer = None, None
        if self.plexAlertListener:
            try:
                self.plexAlertListener.stop()
            except:
                pass
            self.plexAlertListener = None
        if self.stopTimer:
            self.stopTimer.cancel()
            self.stopTimer = None
        if self.stopTimer2:
            self.stopTimer2.cancel()
            self.stopTimer2 = None
        if self.checkConnectionTimer:
            self.checkConnectionTimer.cancel()
            self.checkConnectionTimer = None

    def check_connection(self):
        try:
            self.log("Request for clients list to check connection: " + str(self.plexServer.clients()), extra=True)
            self.checkConnectionTimer = threading.Timer(self.checkConnectionTimerInterval, self.check_connection)
            self.checkConnectionTimer.start()
        except Exception as e:
            self.log("Connection to Plex lost: " + str(e))
            self.log("Reconnecting")
            self.run()

    def log(self, text, colour="", extra=False):
        timestamp = datetime.datetime.now().strftime("%I:%M:%S %p")
        prefix = "[" + timestamp + "] [" + self.plexConfig.serverName + "/" + self.instanceID + "] "
        self.lock.acquire()
        if extra:
            if self.plexConfig.extraLogging:
                print(prefix + TextUtil.colour_text(str(text), colour))
        else:
            print(prefix + TextUtil.colour_text(str(text), colour))
        self.lock.release()

    def on_plex_server_alert(self, data):
        global session_found
        if not self.plexServer:
            return
        try:
            if data["type"] == "playing" and "PlaySessionStateNotification" in data:
                session_data = data["PlaySessionStateNotification"][0]
                state = session_data["state"]
                session_key = int(session_data["session_key"])
                rating_key = int(session_data["rating_key"])
                view_offset = int(session_data["view_offset"])
                self.log("Received Update: " + TextUtil.colour_text(session_data, "yellow").replace("'", "\""),
                         extra=True)
                metadata = self.plexServer.fetchItem(rating_key)
                library_name = metadata.section().title
                if isinstance(self.plexConfig.blacklistedLibraries, list) and (
                        library_name in self.plexConfig.blacklistedLibraries):
                    self.log("Library \"" + library_name + "\" is blacklisted, ignoring", "yellow", True)
                    return
                if isinstance(self.plexConfig.whitelistedLibraries, list) and (
                        library_name not in self.plexConfig.whitelistedLibraries):
                    self.log("Library \"" + library_name + "\" is not whitelisted, ignoring", "yellow", True)
                    return
                if self.lastSessionKey == session_key and self.lastRatingKey == rating_key:
                    if self.stopTimer2:
                        self.stopTimer2.cancel()
                        self.stopTimer2 = None
                    if self.lastState == state:
                        if self.ignoreCount == self.maximumIgnores:
                            self.ignoreCount = 0
                        else:
                            self.log("Nothing changed, ignoring", "yellow", True)
                            self.ignoreCount += 1
                            self.stopTimer2 = threading.Timer(self.stopTimer2Interval, self.stop_on_no_update)
                            self.stopTimer2.start()
                            return
                    elif state == "stopped":
                        self.lastState, self.lastSessionKey, self.lastRatingKey = None, None, None
                        self.stopTimer = threading.Timer(self.stopTimerInterval, self.stop)
                        self.stopTimer.start()
                        self.log("Started stopTimer", "yellow", True)
                        return
                elif state == "stopped":
                    self.log("\"stopped\" state update from unknown session key, ignoring", "yellow", True)
                    return
                if self.isServerOwner:
                    self.log("Checking Sessions for Session Key " + TextUtil.colour_text(session_key, "yellow"),
                             extra=True)
                    plex_server_sessions = self.plexServer.sessions()
                    if len(plex_server_sessions) < 1:
                        self.log("Empty session list, ignoring", "red", True)
                        return
                    for session in plex_server_sessions:
                        self.log(str(session) + ", Session Key: " + TextUtil.colour_text(session.sessionKey,
                                                                                         "yellow") + ", Users: " + TextUtil.colour_text(
                            session.usernames, "yellow").replace("'", "\""), extra=True)
                        session_found = False
                        if session.sessionKey == session_key:
                            session_found = True
                            self.log("Session found", "green", True)
                            if session.usernames[0].lower() == self.plexConfig.listenForUser:
                                self.log("Username \"" + session.usernames[
                                    0].lower() + "\" matches \"" + self.plexConfig.listenForUser + "\", continuing",
                                         "green", True)
                                break
                            else:
                                self.log("Username \"" + session.usernames[
                                    0].lower() + "\" doesn't match \"" + self.plexConfig.listenForUser + "\", ignoring",
                                         "red", True)
                                return
                    if not session_found:
                        self.log("No matching session found", "red", True)
                        return
                if self.stopTimer:
                    self.stopTimer.cancel()
                    self.stopTimer = None
                if self.stopTimer2:
                    self.stopTimer2.cancel()
                self.stopTimer2 = threading.Timer(self.stopTimer2Interval, self.stop_on_no_update)
                self.stopTimer2.start()
                self.lastState, self.lastSessionKey, self.lastRatingKey = state, session_key, rating_key
                mediaType = metadata.type
                if state != "playing":
                    extra = TextUtil.seconds_to_text(view_offset / 1000, ":") + "/" + TextUtil.seconds_to_text(
                        metadata.duration / 1000, ":")
                else:
                    extra = TextUtil.seconds_to_text(metadata.duration / 1000)
                if mediaType == "movie":
                    title = metadata.title + " (" + str(metadata.year) + ")"
                    extra = extra + " · " + ", ".join([genre.tag for genre in metadata.genres[:3]])
                    largeText = "Watching a Movie"
                elif mediaType == "episode":
                    title = metadata.grandparentTitle
                    extra = extra + " · S" + str(metadata.parentIndex) + " · E" + str(
                        metadata.index) + " - " + metadata.title
                    largeText = "Watching a TV Show"
                elif mediaType == "track":
                    title = metadata.title
                    artist = metadata.originalTitle
                    if not artist:
                        artist = metadata.grandparentTitle
                    extra = artist + " · " + metadata.parentTitle
                    largeText = "Listening to Music"
                else:
                    self.log("Unsupported media type \"" + mediaType + "\", ignoring", "red", True)
                    return
                activity = {
                    "details": title,
                    "state": extra,
                    "assets": {
                        "large_text": largeText,
                        "large_image": "logo",
                        "small_text": state.capitalize(),
                        "small_image": state
                    },
                }
                if state == "playing":
                    current_timestamp = int(time.time())
                    if self.plexConfig.timeRemaining:
                        activity["timestamps"] = {
                            "end": round(current_timestamp + ((metadata.duration - view_offset) / 1000))}
                    else:
                        activity["timestamps"] = {"start": round(current_timestamp - (view_offset / 1000))}
                if not self.running:
                    self.start()
                if self.running:
                    self.send(activity)
                else:
                    self.stop()
        except Exception as e:
            self.log("on_plex_server_alert Error: " + str(e))

    def stop_on_no_update(self):
        self.log("No updates from session key " + str(self.lastSessionKey) + ", stopping", "red", True)
        self.stop()
