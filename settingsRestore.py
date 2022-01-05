#!/usr/bin/env python

#
# test settings save and restore
# TODO: read to media - exit if not present
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

# restore settings
t0 = time.time()
with open ("/data/SetupHelper/settings", 'r') as fd:
	for line in fd:
		parts = line.strip().split ('=')

		try:
			bus.get_object("com.victronenergy.settings", parts[0]).SetValue(parts[1])
		except:
			pass

t1 = time.time()
print ("restore settings time %03f" % (t1 - t0))
