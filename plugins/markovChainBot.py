import os
import pickle
from cobe import brain
from time import time


crontable = []
outputs = []
loggingOutputs = []

notifyFile = "plugins/notifyTime.pickle"

###
# Cobe brain
###
class brainInterface(object):
    def __init__(self):
        self.brainFile = "plugins/brain.db"
        self.statsFile = "plugins/brainStats.pickle"
        self.brain = brain.Brain(self.brainFile)
        try:
            with open(self.statsFile, 'rb') as statsFile:
                self.stats = pickle.load(statsFile)
        except:
            answer = ""
            while answer.lower() not in ['y', 'n']:
                answer = raw_input("FAILED TO LOAD STATS FILE! CREATE NEW STATS FILE?")
            if answer == 'y':
                self.stats = {}
            else:
                sys.exit(1)
    # Stats
    def saveStats(self):
        with open(self.statsFile, 'wb') as statsFile:
            pickle.dump(self.stats, statsFile)
    def incrementStat(self, key, amt=1):
        self.stats[key] = self.stats.get(key, 0) + amt
        self.saveStats()
    def getSize(self):
        #bytes
        return os.stat(self.brainFile).st_size
    def getStat(self, stat):
        return str(self.stats.get(stat, "Couldn't get stat? Contact bot admin."))
    # Brain
    def learn(self, phrase):
        self.brain.learn(phrase)
        self.incrementStat("numLearned")
    def reply(self, phrase):
        response = self.brain.reply(phrase, 1000)
        self.learn(phrase)
        self.incrementStat("numReplies")
        return response
b = brainInterface()


###
# Command handlers
###
def unknownCommand(data):
    return "Unknown command! Available commands: {}".format(privateCommandDispatch.keys())
privateCommandDispatch = {'brainfilesize': lambda x: "{} KB".format(b.getSize()/1024),
                   'numlearned': lambda x: b.getStat("numLearned"),
                   'numreplies': lambda x: b.getStat("numReplies")}
publicCommandDispatch = {}


###
# DM Message handler
###
def respond(data):
    if data['text'][0] == '!':
        output = privateCommandDispatch.get(data['text'][1:].lower(), unknownCommand)(data)
        outputs.append([data['channel'], output])
        loggingOutputs.append("`{}` commanded with `{}`: result was `{}`".format(slackClient.server.users.find(data['user']).name, data['text'], output))
        return
    reply = b.reply(data['text'])
    outputs.append([data['channel'], reply])
    loggingOutputs.append("`{}` asked `{}`: result was `{}`".format(slackClient.server.users.find(data['user']).name, data['text'], reply))

###
# Channel/Group Message handler
###
def listen(data):
    if data['text'].startswith('!markov '):
        output = publicCommandDispatch.get(data['text'][8:].lower(), unknownCommand)(data)
        if output != None:
            outputs.append([data['channel'], output])
        return
    b.learn(data['text'])
    addChannelNotifier(data['channel'])

###
# Channel-type dispatching
###
messageDispatch = {'D': respond,
                'C': listen,
                'G': listen}
def handleMessage(data):
    messageDispatch.get(data['channel'][0], unknownChannel)(data)
def unknownChannel(data):
    loggingOutputs.append("Got message, but no dispatch found! `{}`".format(data))

###
# Group notification
###
def notifyGroup(channelId, channelName, reason):
    salutation = {'join': 'thanks for inviting me into your channel!',
                  'remind': 'this is a monthly reminder that I\'m here (in case of security concerns)!'}
    joinMessage = "Hello {}, {} I try to \"learn\" English sentence structure through Markov chains. If you don't want me eavesdropping, please kick me (you might need admin help for this). Otherwise, invite me to all your parties so I can learn faster (/invite @markovbot)! DM me to see what I have to say -- I'll start out pretty (really) stupid and get \"smarter\" with time. Caveat lector -- when trained on live tweets, I became enamored with Biebs... oops. DM commands are denoted by '!' prefix. Source/issues: http://git.io/vn4Pd, Slack: noacro"
    outputs.append([channelId, joinMessage.format(channelName, salutation[reason])])

crontable.append([60, "cronNotify"])
notifyTable = {}

def addChannelNotifier(channelId, channelName=None):
    if channelName is None:
        channelName = slackClient.server.channels.find(channelId).name
    notifyTable[channelId] = channelName

def cronNotify():
    try:
        with open(notifyFile, 'rb') as notifyf:
            lastNotifyTime = pickle.load(notifyf)
    except:
        lastNotifyTime = time()
        with open(notifyFile, 'wb') as notifyf:
            pickle.dump(lastNotifyTime, notifyf)
    if lastNotifyTime + (31 * 24 * 60 * 60) > time():
        return
    loggingOuputs.append('Dispatching notifications to {}'.format(str(notifyTable)))
    lastNotifyTime = time()
    with open(notifyFile, 'wb') as notifyf:
        pickle.dump(lastNotifyTime, notifyf)
    for channelId, channelName in notifyTable.iteritems():
        print channelId
        notifyGroup(channelId, channelName, 'remind')

###
# Plugin exports
###
def process_message(data):
    if 'text' not in data:
        print "Ignoring non-content message {}".format(data)
        return
    if data['user'] == me:
        # No sense in reacting to our own messages
        return
    print "GotMessage {}".format(data)
    handleMessage(data)

def process_group_joined(data):
    channelId = data['channel']['id']
    channelName = data['channel']['name']
    notifyGroup(channelId, channelName, 'join')
    addChannelNotifier(channelId, channelName)
    loggingOutputs.append('Invited to {}!'.format(channelName))

def process_group_left(data):
    channelId = data['channel']
    if channelId in notifyTable:
        loggingOutputs.append('Removed from {} :('.format(notifyTable[channelId]))
        del notifyTable[channelId]

def catchAll(data):
    if data['type'] != "pong":
        print "CaughtAll {}".format(data)
