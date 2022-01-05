#!/usr/bin/env python

#
# test settings save
# TODO: write to media - exit if not present
#
import platform
import argparse
import logging

import sys
import subprocess
import threading
import os
import shutil
import dbus
import time
import re
import glob

# add the path to our own packages for import
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusService
from settingsdevice import SettingsDevice

bus = dbus.SystemBus()

settingsListFile = "/data/SetupHelper/settingsList"

if not os.path.exists (settingsListFile):
	logging.error (settingsListFile + " does not exist - can't backup/restore settings")
	exit ()

# backup settings
t0 = time.time()
backupSettings = open ("/data/SetupHelper/settings", 'w') # TODO: change to media
with open (settingsListFile, 'r') as listFile:
	for line in listFile:
		setting = line.strip()
		try:
			value = bus.get_object("com.victronenergy.settings", setting).GetValue()
		except:
			continue
		backupSettings.write ( setting + '=' + str(value) + '\n' )

backupSettings.close ()
listFile.close ()

t1 = time.time()
print ("backup settings time %03f" % (t1 - t0))
