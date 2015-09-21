#!/usr/bin/env python

import sys
sys.dont_write_bytecode = True

import os
import yaml
import json
import logging
import time
import glob

from slackclient import SlackClient

def dbg(debugString):
    if debug:
        logging.info(debugString)

class RtmBot(object):
    def __init__(self, token):
        self.lastPing = 0
        self.token = token
        self.botPlugins = []
        self.slackClient = None
        self.me = None
    def connect(self):
        self.slackClient = SlackClient(self.token)
        if not self.slackClient.rtm_connect():
            logging.error("Connection to Slack failed!")
    def start(self):
        self.connect()
        # Get our user id
        users = json.loads(self.slackClient.api_call("users.list"))
        self.me = [x['id'] for x in users['members'] if x['name'] == config['ME']][0]
        # Load plugins and run loop
        self.loadPlugins()
        while True:
            for reply in self.slackClient.rtm_read():
                self.input(reply)
            self.crons()
            self.output()
            self.loggingOutput()
            self.autoPing()
            time.sleep(0.5)
    def autoPing(self):
        now = int(time.time())
        if now > self.lastPing + 3:
            self.slackClient.server.ping()
            self.lastPing = now
    def input(self, data):
        if "type" in data:
            functionName = "process_" + data["type"]
            dbg("Got {}".format(functionName))
            for plugin in self.botPlugins:
                plugin.registerJobs()
                plugin.do(functionName, data)
    def output(self):
        for plugin in self.botPlugins:
            limiter = False
            for output in plugin.doOutput():
                channel = self.slackClient.server.channels.find(output[0])
                if channel != None and output[1] != None:
                    if limiter == True:
                        time.sleep(0.1)
                        limiter = False
                    message = output[1].encode('ascii', 'ignore')
                    channel.send_message("{}".format(message))
                    limiter = True
    def loggingOutput(self):
        channel = self.slackClient.server.channels.find('markovbottesting')
        for plugin in self.botPlugins:
            limiter = False
            for output in plugin.doLoggingOutput():
                if channel != None and output != None:
                    if limiter == True:
                        time.sleep(0.1)
                        limiter = False
                    message = output.encode('ascii', 'ignore')
                    channel.send_message("{}".format(message))
                    limiter = True
    def crons(self):
        for plugin in self.botPlugins:
            plugin.doJobs()
    def loadPlugins(self):
        for plugin in glob.glob(directory+'/plugins/*'):
            sys.path.insert(0, plugin)
            sys.path.insert(0, directory+'/plugins/')
        for plugin in glob.glob(directory+'/plugins/*.py') + glob.glob(directory+'/plugins/*/*.py'):
            logging.info(plugin)
            name = plugin.split('/')[-1][:-3]
            self.botPlugins.append(Plugin(name, self.me, self.slackClient))

class Plugin(object):
    def __init__(self, name, me, slackClient, pluginConfig={}):
        self.name = name
        self.jobs = []
        self.module = __import__(name)
        self.registerJobs()
        self.outputs = []
        self.module.me = me
        self.module.slackClient = slackClient
        if name in config:
            logging.info("config found for: " + name)
            self.module.config = config[name]
        if 'setup' in dir(self.module):
            self.module.setup()
    def registerJobs(self):
        if 'crontable' in dir(self.module):
            for interval, function in self.module.crontable:
                self.jobs.append(Job(interval, eval("self.module."+function)))
            if len(self.module.crontable) > 0:
                logging.info("Module ({}) added cronjobs: {}".format(self.name, self.module.crontable))
        self.module.crontable = []
    def do(self, functionName, data):
        if functionName in dir(self.module):
            # make plugin file with a trace if debugging, otherwise just log generic error message
            if not debug:
                try:
                    eval("self.module."+functionName)(data)
                except:
                    dbg("problem in module {} {}".format(functionName, data))
            else:
                eval("self.module."+functionName)(data)
        if "catchAll" in dir(self.module):
            try:
                self.module.catchAll(data)
            except:
                dbg("problem in module catchAll {}".format(data))
    def doJobs(self):
        for job in self.jobs:
            job.check()
    def doOutput(self):
        output = []
        while True:
            if 'outputs' in dir(self.module):
                if len(self.module.outputs) > 0:
                    # logging.info("output from {}".format(self.module))
                    output.append(self.module.outputs.pop(0))
                else:
                    break
            else:
                self.module.outputs = []
        return output
    def doLoggingOutput(self):
        loggingOutputs = []
        while True:
            if 'outputs' in dir(self.module):
                if len(self.module.loggingOutputs) > 0:
                    output = self.module.loggingOutputs.pop(0)
                    logging.info("logging output from {}: {}".format(self.module, output))
                    loggingOutputs.append(output)
                else:
                    break
            else:
                self.module.loggingOutputs = []
        return loggingOutputs

class Job(object):
    def __init__(self, interval, function):
        self.function = function
        self.interval = interval
        self.lastrun = 0
    def __str__(self):
        return "{} {} {}".format(self.function, self.interval, self.lastrun)
    def __rep__(self):
        return self.__str__()
    def check(self):
        if self.lastrun + self.interval < time.time():
            if not debug:
                try:
                    self.function()
                except:
                    dbg("problem running job {}".format(self))
            else:
                self.function()
            self.lastrun = time.time()

class UnknownChannel(Exception):
    pass


def main():
    if "LOGFILE" in config:
        logging.basicConfig(filename = config["LOGFILE"], level=logging.INFO, format='%(asctime)s %(message)s')
    logging.info(directory)
    try:
        bot.start()
    except KeyboardInterrupt:
        print "[+] Shutting down bot!"
        sys.exit(0)
    except Exception, e:
        logging.exception(e)
    except:
        logging.exception("Caught non-exception type!")


if __name__ == "__main__":
    directory = os.path.dirname(sys.argv[0])
    if not directory.startswith('/'):
        directory = os.path.abspath("{}/{}".format(os.getcwd(),
                                directory
                                ))

    config = yaml.load(file('rtmbot.conf', 'r'))
    debug = config["DEBUG"]
    bot = RtmBot(config["SLACK_TOKEN"])
    sitePlugins = []
    filesCurrentlyDownloading = []
    jobHash = {}

    if config.has_key("DAEMON"):
        if config["DAEMON"]:
            import daemon
            with daemon.DaemonContext():
                main()
    main()
