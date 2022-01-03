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

testSettingsList = [
"/Settings/GuiMods/AcCurrentLimit/Preset1",
"/Settings/GuiMods/AcCurrentLimit/Preset2",
"/Settings/GuiMods/AcCurrentLimit/Preset3",
"/Settings/GuiMods/AcCurrentLimit/Preset4",
"/Settings/SystemSetup/SystemName",
]

settingsList = [
"/Settings/GuiMods/AcCurrentLimit/Preset1",
"/Settings/GuiMods/AcCurrentLimit/Preset2",
"/Settings/GuiMods/AcCurrentLimit/Preset3",
"/Settings/GuiMods/AcCurrentLimit/Preset4",
"/Settings/GuiMods/EnhancedFlowCombineLoads",
"/Settings/GuiMods/GaugeLimits/AcOutputMaxPower",
"/Settings/GuiMods/GaugeLimits/AcOutputNonCriticalMaxPower",
"/Settings/GuiMods/GaugeLimits/BatteryMaxChargeCurrent",
"/Settings/GuiMods/GaugeLimits/BatteryMaxDischargeCurrent",
"/Settings/GuiMods/GaugeLimits/CautionPower",
"/Settings/GuiMods/GaugeLimits/ContiuousPower",
"/Settings/GuiMods/GaugeLimits/DcSystemMaxCharge",
"/Settings/GuiMods/GaugeLimits/DcSystemMaxLoad",
"/Settings/GuiMods/GaugeLimits/MaxChargerPower",
"/Settings/GuiMods/GaugeLimits/MaxFeedInPower",
"/Settings/GuiMods/GaugeLimits/PeakPower",
"/Settings/GuiMods/GaugeLimits/PvChargerMaxPower",
"/Settings/GuiMods/GaugeLimits/PvOnGridMaxPower",
"/Settings/GuiMods/GaugeLimits/PvOnOutputMaxPower",
"/Settings/GuiMods/MoveSettings",
"/Settings/GuiMods/ShortenTankNames",
"/Settings/GuiMods/ShowEnhancedFlowLoadsOnInput",
"/Settings/GuiMods/ShowEnhancedFlowOverviewTanks",
"/Settings/GuiMods/ShowEnhancedFlowOverviewTemps",
"/Settings/GuiMods/ShowGauges",
"/Settings/GuiMods/ShowInactiveFlowTiles",
"/Settings/GuiMods/ShowRelayOverview",
"/Settings/GuiMods/ShowTileOverview",
"/Settings/GuiMods/TemperatureScale",
"/Settings/GuiMods/TimeFormat",
"/Settings/GuiMods/UseEnhancedFlowOverview",
"/Settings/GuiMods/UseEnhancedGridParallelFlowOverview",
"/Settings/GuiMods/UseEnhancedMobileOverview",
"/Settings/PackageManager/GitHubAutoDownload",
"/Settings/PackageManager/AutoInstall",
"/Settings/Gps/SpeedUnit",
"/Settings/Gui/AutoBrightness",
"/Settings/Gui/Brightness",
"/Settings/Gui/DefaultOverview",
"/Settings/Gui/DisplayOff",
"/Settings/Gui/Language",
"/Settings/Gui/MobileOverview",
"/Settings/Gui/StartWithMenuView",
"/Settings/Gui/TanksOverview",
"/Settings/Relay/0/CustomName",
"/Settings/ShutdownMonitor/ExternalSwitch",
"/Settings/System/TimeZone",
"/Settings/SystemSetup/AcInput1",
"/Settings/SystemSetup/AcInput2",
"/Settings/SystemSetup/HasAcOutSystem",
"/Settings/SystemSetup/HasDcSystem",
"/Settings/SystemSetup/MaxChargeCurrent",
"/Settings/SystemSetup/MaxChargeVoltage",
"/Settings/SystemSetup/SharedTemperatureSense",
"/Settings/SystemSetup/SharedVoltageSense",
"/Settings/SystemSetup/SystemName",
"/Settings/Vrmlogger/LogInterval",
"/Settings/Vrmlogger/Logmode",

]
bus = dbus.SystemBus()

# save settings
t0 = time.time()
fd = open ("/data/SetupHelper/settings", 'w')
for setting in testSettingsList: # TODO: change to settingsList
	try:
		value = bus.get_object("com.victronenergy.settings", setting).GetValue()
	except:
		continue

	fd.write ( setting + ':' + str(value) + '\n' )
fd.close ()
t1 = time.time()
print ("save settings time %03f" % (t1 - t0))
