#!/usr/bin/env python
#
#	PackageManager.py
#	Kevin Windrem
#
#
# This program is responsible for
#	downloading, installing and unstalling packages
# 	package monitor also checks SD cards and USB sticks for package archives
#		either automatically or manually via the GUI
#	providing the user with status on installed packages and any updates via the GUI
#
# It runs as /service/PackageManager
#
# Persistent storage for packageManager is stored in dbus Settings:
#
#	com.victronenergy.Settings parameters for each package:
#		/Settings/PackageManager/n/PackageName		can be edited by the GUI only when adding a new package
#		/Settings/PackageManager/n/GitHubUser		can be edited by the GUI
#		/Settings/PackageManager/n/GitHubBranch		can be edited by the GUI
#		/Settings/PackageManager/Count				the number of ACTIVE packages (0 <= n < Count)
#		/Settings/PackageManager/Edit/...			GUI edit package set
#
#		/Settings/PackageManager/GitHubAutoDownload 	set by the GUI to control automatic updates from GitHub
#			0 - no GitHub auto downloads (version checks still occur)
#			1 - normal updates - one download every 10 minutes
#			2 - fast updates - one download update every 10 seconds, then at the normal rate after one pass
#			3 - one update pass at the fast rate, then to no updates
#				changing to one of the fast scans, starts from the first package
#
#		if no download is needed, checks for downloads are fast: every 5 seconds, slow: every 2 minutes

AUTO_DOWNLOADS_OFF = 0
NORMAL_DOWNLOAD = 1
FAST_DOWNLOAD = 2
ONE_DOWNLOAD = 3

#		/Settings/PackageManager/AutoInstall
#			0 - no automatic install
#			1 - automatic install after download from GitHub or SD/USB
#
# Additional (volatile) parameters linking packageManager and the GUI are provided in a separate dbus service:
#
#	com.victronenergy.packageManager parameters
#		/Package/n/GitHubVersion 					from GitHub
#		/Package/n/PackageVersion 					from /data <packageName>/version from the package directory
#		/Package/n/InstalledVersion 				from /etc/venus/isInstalled-<packageName>
#		/Package/n/RebootNeeded						indicates a reboot is needed to activate this package
#		/Package/n/Incompatible						indicates if package is or is not compatible with the system
#													'' if compatible
#													'VERSION' if the system version is outside the package's acceptable range
#													'PLATFORM' package can not run on this platform
#													'CMDLINE' setup must be run from command line
#														currently only for Raspberry PI packages only
#
#		for both Settings and the the dbus service:
#			n is a 0-based section used to reference a specific package
#
#
#		/Default/m/PackageName			a dbus copy of the default package list (/data/SetupHelper/defaultPackageList)
#		/Default/m/GitHubUser
#		/Default/m/GitHubBranch
#		/DefaultCount					the number of default packages
#
#		m is a 0-based section used to referene a specific default paclage
#
#		/GuiEditAction is a text string representing the action
#		  set by the GUI to trigger an action in PackageManager
#			'install' - install package from /data to the Venus working directories
#			'uninstall' - uninstall package from the working directories
#			'download" - download package from GutHub to /data
#			'add' - add package to package list (after GUI sets .../Edit/...
#			'remove' - remove package from list TBD ?????
# 		 	'reboot' - reboot
#
#		the GUI must wait for PackageManager to signal completion of one operation before initiating another
#
#		  set by packageMonitor when the task is complete
#	return codes - set by PackageManager
#			'' - action completed without errors (idle)
#			'ERROR' - error during action - error reported in /GuiEditStatus:
#				unknown error
#				not compatible with this version
#				not compatible with this platform
#				no options present - must install from command line
#				GUI choices: OK - closes "dialog"
#			'RebootNeeded' - reboot needed
#				GUI choices:
#					Do it now
#						GUI sends reboot command to PackageManager
#					Defer
#						GUI sets action to 0
#
# setup script return codes and install states
EXIT_SUCCESS =				0
EXIT_ERROR =				255 # generic error
EXIT_REBOOT =				123
EXIT_INCOMPATIBLE_VERSION =	254
EXIT_INCOMPATIBLE_PLATFOM =	253
EXIT_FILE_SET_ERROR	=		252
EXIT_OPTIONS_NOT_SET =		251
EXIT_RUN_AGAIN = 			250
# install states only
ERROR_NO_SETUP_FILE = 		999
#
#
#		/GuiEditStatus 				a text message to report edit status to the GUI
#
#		/GitHubUpdateStatus			as above for automatic GitHub update
#
#		/InstallStatus				as above for automatic install/uninstall
#
#		/MediaUpdateStatus			as above for SD/USB media transfers
#
#		/Platform					a translated version of the platform (aka machine)
#									machine			Platform
#									ccgx			CCGX
#									einstein		Cerbo GX
#									bealglebone		Venus GX
#									canvu500		CanVu 500
#									nanopi			Multi/Easy Solar GX
#									raspberrypi2	Raspberry Pi 2/3
#									raspberrypi4	Raspberry Pi 4
#
#
# /Settings/PackageVersion/Edit/ is a section for the GUI to provide information about the a new package to be added
#
# /data/SetupHelper/defaultPackageList provides an initial list of packages
#	It contains a row for each package with the following information:
#		packageName gitHubUser gitHubBranch
#	If present, packages listed will be ADDED to the package list in /Settings
#	existing dbus Settings (GitHubUser and GitHubBranch) will not be changed
#
#	this file is read at program start
#
# Package information is stored in the /data/<packageName> directory
#
# A version file within that directory identifies the version of that package stored on disk but not necessarily installed
#
# When a package is installed, the version in the package directory is written to an "installed flag" file
#		/etc/venus/isInstalled-<packageName>
#	the contents of the file populate InstalledVersion (blank if the file doesn't exist or is empty)
#
# InstalledVersion is displayed to the user and used for tests for automatic updates
#
# GitHubVersion is read from the internet if a connection exists.
#	To minimize local network traffic and GitHub server loads one package's GitHub version is
#		read once every 5 seconds until all package versions have been retrieved
#		then one package verison is read every 10 minutes.
#	Addition of a package or change in GitHubUser or GitHubBranch will trigger a fast
#		update of GitHub versions
#	If the package on GitHub can't be accessed, GitHubVersion will be blank
#
#
# PackageManager downloads packages from GitHub based on the GitHub version and package (stored) versions:
#	if the GitHub branch is a specific version, the download occurs if the versions differ
#		otherwise the GitHub version must be newer.
#	the archive file is unpacked to a directory in /data named
# 		 <packageName>-<gitHubBranch>.tar.gz, then moved to /data/<packageName>, replacing the original
#
# PackageManager installs the stored verion if the package (stored) and installed versions differ
#
# Manual downloads and installs triggered from the GUI ignore version checks completely
#
#	In this context, "install" means replacing the working copy of Venus OS files with the modified ones
#		or adding new files and system services
#
#	Uninstalling means replacing the original Venus OS files to their working locations
#
#	All operations that access the global package list must do so surrounded by a lock to avoid accessing changing data
#		this is very important when scanning the package list
#			so that packages within that list don't get moved, added or deleted
#
#	Operations that take signficant time are handled in separate threads, decoupled from the package list
#		Operaitons are placed on a queue with all the information a processing routine needs
#			this is imporant because the package in the list involved in the operaiton
#			may no longer be in the package list or be in a different location
#
#		All operations that scan the package list must do so surrounded by
#			DbusIf.LOCK () and DbusIf.UNLOCK ()
#			and must not consume significant time: no sleeping or actions taking seconds or minutes !!!!
#
#	Operations that take little time can usually be done in-line (without queuing)
#
# PackageManager manages flag files in the package folder:
#	REMOVED 					indicates the package was manually removed and PackageManager should not attempt
#								any automatic operations
#	DO_NOT_AUTO_INSTALL			indicates the package was manually removed and PackageManager should not attempt
#								to automatically install it
#
#	these flags will be removed when a package is downloaded from GitHub or transferred from SD/USB media
#	for removed packages this is totally appropriate since the package is being added anywya
#	for manual removal, this may or may not be desired.
#		But it is the best choice considering the alternative would be a package that appears to silenty fail to install
#
# PackageManager checks removable media (SD cards and USB sticks) for package upgrades or even as a new package
#	File names must be in one of the following forms:
#		<packageName>-<gitHubBranch or version>.tar.gz
#		<packageName>-install.tar.gz
#	The <packageName> portion determines where the package will be stored in /data
#		and will be used as the package name when the package is added to the package list in Settings
#
#	If all criteria are met, the archive is unpacked and the resulting directory replaces /data/<packageName>
#		if not, the unpacked archive directory is deleted
#
#
#	PackageManager scans /data looking for new packages
#		directory names must not appear to be an archive
#			(include a GitHub branch or version number) (see rejectList below for specifics)
#		the directory must contain a valid version
#		the package must not have been manually removed (REMOVED flag file set)
#		the file name must be unique to all existing packages
#
#		A new, verified package will be added to the package list and be ready for
#			manual and automtic updates, installs, uninstalls
#
#		This mechanism handles archives extracted from SD/USB media
#
#
#	Packages may optionally include a file containg GitHub user and branch
#		if the package diretory contains the file: gitHubInfo
#			gitHubUser and gitHubBranch are set from the file's content when it is added to the package list
#			making the new package ready for automatic GitHub updates
#		gitHubInfo should have a single line of the form: gitHubUser:gitHubBranch, e.g, kwindrem:latest
#		if the package is already in the package list, gitHubInfo is ignored
#		if no GitHub information is contained in the package, the user must add it manually via the GUI
#			in so automatic downloads from GitHub can occur
#
# classes/instances/methods:
#	AddRemoveClass
#		AddRemove (thread)
#			StopThread ()
#			run ()
#		PushAction ()
#	DbusIfClass
#		DbusIf
#			SetGuiEditAction ()
#			UpdateStatus ()
#			LocateDefaultPackage ()handleGuiEditAction
#			 ()
#			UpdatePackageCount ()
#			various Gets and Sets for dbus parameters
#			LOCK ()
#			UNLOCK ()
#	PackageClass
#		PackageList [] one per package
#		LocatePackage ()
#		RemoveDbusSettings ()
#		settingChangedHandler ()
#		various Gets and Sets
#		AddPackagesFromDbus ()
#		AddDefaultPackages ()
#		AddStoredPackages ()
#		updateGitHubInfo ()
#		AddPackage ()
#		RemovePackage ()
#		UpdateFileVersions ()
#		UpdateAllFileVersions ()
#		UpdateInstallStateByPackage ()
#		UpdateInstallStateByName ()
#	DownloadGitHubPackagesClass
#		DownloadGitHub (thread)
#			SetDownloadPending ()
#			ClearDownloadPending ()
#			updateGitHubVersion ()
#			updatePriorityGitHubVersion ()
#			SetPriorityGitHubVersion ()
#			GitHubDownload ()
#			downloadNeededCheck ()
#			processDownloadQueue ()
#			refreshGitHubVersion ()
#			run ()
#			StopThread ()
#	InstallPackagesClass
#		InstallPackages (thread)
#			InstallPackage ()
#			autoInstallNeeded ()
#			StopThread ()
#			run ()
#	MediaScanClass
#		MediaScan (thread)
#			transferPackage
#			StopThread ()
#			run ()
#
# global methods:
#	VersionToNumber ()
#	LocatePackagePath ()
#	AutoRebootCheck ()


# for timing sections of code
# t0 = time.time()
# code to be timed
# t1 = time.time()
# logging.info ( "some time %6.3f" % (t1 - t0) )

import platform
import argparse
import logging

# set variables for logging levels:
CRITICAL = 50
ERROR = 40
WARNING = 30
INFO = 20
DEBUG = 10

import sys
import subprocess
import threading
import os
import shutil
import dbus
import time
import re
import glob

# accommodate both Python 2 and 3
try:
	import queue
except ImportError:
	import Queue as queue

# accommodate both Python 2 and 3
# if the Python 3 GLib import fails, import the Python 2 gobject
try:
    from gi.repository import GLib # for Python 3
except ImportError:
    import gobject as GLib # for Python 2
# add the path to our own packages for import
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusService
from settingsdevice import SettingsDevice

global DownloadGitHub
global InstallPackages
global AddRemove
global MediaScan
global DbusIf
global Platform
global VenusVersion
global SystemReboot


#	VersionToNumber
#
# convert a version string in the form of vX.Y~Z-large-W to an integer to make comparisions easier
# the ~Z portion indicates a pre-release version so a version without it is later than a version with it
# the -W portion is like the ~Z for large builds
# 	the -W portion is IGNORED !!!!
#	note part[0] is always null because there is nothing before v which is used as a separator
#
# each section of the version is given 3 decimal digits
#	for example v1.2~3 			would be  1002003
#	for example v11.22   		would be 11022999
#	for example v11.22-large-33	would be 11022999
# an empty file or one that contains "unknown" or does not beging with 'v'
# 	has a version number = 0
#
#	returns the version number

def VersionToNumber (version):
	if version == None or version == "" or version[0] != 'v':
		return 0

	parts = re.split ('v|\.|\~|\-', version)
	versionNumber = 0
	if len(parts) >= 2:
		versionNumber += int ( parts[1] ) * 1000000
	if len(parts) >= 3:
		versionNumber += int ( parts[2] ) * 1000
	if len(parts) >= 4:
		versionNumber += int ( parts[3] )
	else:
		versionNumber += 999
	return versionNumber


#	LocatePackagePath
#
# attempt to locate a package directory
#
# all directories at the current level are checked
#	to see if they contain a file named 'version'
#	indicating a package directory has been found
#
#	further, the version file must begin with 'v'
#
# if so, that path is returned
#
# if a directory NOT containing 'version' is found
#	this method is called again to look inside that directory
#
# if nothing is found, the method returns None
#
# all recursive calls will return with the located package or None
#	so the original caller will have the path to the package or None

def LocatePackagePath (origPath):
	paths = os.listdir (origPath)
	for path in paths:
		newPath = origPath +'/' + path
		if os.path.isdir(newPath):
			# found version file, make sure it is "valid"
			versionFile = newPath + "/version"
			if os.path.isfile( versionFile ):
				fd = open ( versionFile, 'r' )
				version = fd.readline().strip()
				fd.close()
				if version[0] == 'v':
					return newPath
				else:
					logging.error ("version file not a valid version " + versionFile + " = " + version )
			else:
				packageDir = locatePackagePath (newPath)
				# found a package directory
				if packageDir != None:
					return packageDir
				# nothing found - continue looking in this directory
				else:
					continue
	return None


#	AddRemoveClass
#	Instances:
#		AddRemove (a separate thread)
#
#	Methods:
#		PushAction
#		run ( the thread )
#		StopThread ()
#
#	Install and Uninstall actions are processed by
# 		the InstallPackages thread
#	Download actions are processed by
#		the DownloadGitHub thread
#	Add and Remove actions are processed in this thread
#
# a queue isolates the caller from processing time
#	and interactions with the dbus object
#		(can't update the dbus object from it's handler !)
#
# some actions called may take seconds or minutes (based on internet speed) !!!!
#
# the queue entries are: ("action":"packageName")
#	this decouples the action from the current package list which could be changing
#	allowing the operation to proceed without locking the list

class AddRemoveClass (threading.Thread):

	def __init__(self):
		threading.Thread.__init__(self)
		self.AddRemoveQueue = queue.Queue (maxsize = 10)
		self.threadRunning = True

	
	#	PushAction
	#
	# add an action to one of three queues:
	#	InstallPackages.InstallQueue for Install and Uninstall actions
	#	Download.Download for Download actions
	# 	self.AddRemoveQueue
	# commands are added to the queue from the GUI (dbus service change handler)
	# the queue isolates command triggers from processing because processing 
	#		can take seconds or minutes
	#
	#	action is a text string: Install, Uninstall, Download, Add, Remove, etc
	#	packageName is the name of the package to receive the action
	#		for some acitons this may be the null string
	#
	# the 'Reboot' action is handled in line since it just sets a global flag
	#	to be handle in mainLoop
# TODO: need to update GUI status since queue pull is too late for timely ack to request
	def PushAction (self, command=None):
		parts = command.split (":")
		action = parts[0]
		if action == 'download':
			queue = DownloadGitHub.DownloadQueue
			queueText = "Download"
		elif action == 'install' or action == 'uninstall':
			queue = InstallPackages.InstallQueue
			queueText = "Install"
		elif action == 'add' or action == 'remove':
			queue = self.AddRemoveQueue
			queueText = "AddRemove"
		elif action == 'reboot':
			logging.warning ( "received Reboot request from " + 'GUI')
			# set the flag - reboot is done in main_loop
			global SystemReboot
			SystemReboot = True
		# ignore blank action - this occurs when PackageManager changes the action on dBus to 0
		#	which acknowledges a GUI action
		elif action == '':
			return
		else:
			logging.error ("PushAction received unrecognized command: " + command)
			return
	
		try:
			queue.put ( command, block=False )
		except queue.Full:
			logging.error ("command " + command + " lost - " + ququeText + " - queue full")
		except:

			logging.error ("command " + command + " lost - " + ququeText + " - other queue error")
	# end PushAction


	#	AddRemove run (the thread), StopThread
	#
	# run  is a thread that pulls actions from a queue and processes them
	# Note: some processing times can be several seconds to a minute or more
	#	due to newtork activity
	#
	# run () checks the threadRunning flag and returns if it is False,
	#	essentially taking the thread off-line
	#	the main method should catch the tread with join ()
	# StopThread () is called to shut down the thread

	def StopThread (self):
		logging.info ("attempting to stop AddRemove thread")
		self.threadRunning = False

	#	AddRemove run ()
	#
	# process package Add/Remove actions from the GUI
	def run (self):
		while self.threadRunning:
			try:
				command = self.AddRemoveQueue.get (timeout=5)
			except queue.Empty:	# queue empty is OK - just allows some time unblocked
				if self.threadRunning == False:
					return
				time.sleep (5.0)
				continue
			except:
				logging.error ("pull from editActionQueue failed")
				continue
			# got new action from queue - decode and processInstallPackage
			parts = command.split (":")
			if len (parts) >= 1:
				action = parts[0].strip()
			else:
				action = ""
			if len (parts) >= 2:
				packageName = parts[1].strip()
			else:
				packageName = ""
			if action == 'add':
				PackageClass.AddPackage (packageName = packageName, source='GUI' )						

			elif action == 'remove':
				PackageClass.RemovePackage ( packageName )

			else:
				logging.warning ( "received invalid action " + command + " from " + source + " - discarding" )
		# end while True
	# end run ()
# end AddRemoveClass


#	DbusIfClass
#	Instances:
#		DbusIf
#
#	Methods:
#		SetGuiEditAction
#		UpdateStatus
#		LocateDefaultPackage
#		handleGuiEditAction
#		UpdatePackageCount
#		RemoveDbusSettings
#		TransferOldDbusPackageInfo
#		various Gets and Sets for dbus parameters
#		LOCK
#		UNLOCK
#
#	Globals:
#		DbusSettings (for settings that are NOT part of a package)
#		DbusService (for parameters that are NOT part of a package)
#		EditPackage - the dbus Settings used by the GUI to hand off information about
#			a new package
#		DefaultPackages - list of default packages, each a tuple:
#						 ( packageName, gitHubUser, gitHubBranch)
#
# DbusIf manages the dbus Settings and packageManager dbus service parameters
#	that are not associated with any spcific package
#
# unlike those managed in PackageClass which DO have a package association
#	the dbus settings managed here don't have a package association
#	however, the per-package parameters are ADDED to
#	DbusSettings and dBusService created here !!!!
#
# DbusIf manages a lock to prevent data access in one thread
#	while it is being changed in another
#	the same lock is used to protect data in PackageClass also
#	this is more global than it needs to be but simplies the locking
#
#	all methods that access must aquire this lock
#		prior to accessing DbusIf or Package data
#		then must release the lock
#
# default package info is fetched from a file and published to our dbus service
#	for use by the GUI in adding new packages
#	it the default info is also stored in DefaultPackages
#	LocateDefaultPackage is used to retrieve the default from local storage
#		rather than pulling from dbus or reading the file again

class DbusIfClass:


	#		RemoveDbusSettings
	# remove the dbus Settings paths for package
	# package Settings are removed
	# this is called when removing a package
	# settings to be removed are passed as a list (settingsList)
	# this gets reformatted for the call to dbus

	@classmethod
	def RemoveDbusSettings (cls, settingsList):

		# format the list of settings to be removed
		i = 0
		while i < len (settingsList):
			if i == 0:
				settingsToRemove = '%[ "' + settingsList[i]
			else:
				settingsToRemove += '" , "' + settingsList[i]
			i += 1
		settingsToRemove += '" ]'

		# remove the dbus Settings paths - via the command line 
		try:
			proc = subprocess.Popen (['dbus', '-y', 'com.victronenergy.settings', '/', 'RemoveSettings', settingsToRemove  ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		except:
			logging.error ("dbus RemoveSettings call failed")
		else:
			proc.wait()
			# convert from binary to string
			out, err = proc.communicate ()
			stdout = out.decode ().strip ()
			stderr = err.decode ().strip ()
			returnCode = proc.returncode
			if returnCode != 0:
				logging.error ("dbus RemoveSettings failed " + str (returnCode))
				logging.error (stderr)


	#	TransferOldDbusPackageInfo
	# PackageManager dbus storage was moved
	# from ...PackageMonitor... to ...PackageManager...
	# this method moves the info to the new location and deleted the old Settings
	# this assumes the new dbus environment is already set up
	# the transfer is only done if the new location has no packages
	# should only be called from initialization so we don't LOCK while accessing the package list


	@classmethod
	def TransferOldDbusPackageInfo (cls):
		bus = dbus.SystemBus()
		oldPath = "/Settings/PackageMonitor"
		newPath = "/Settings/PackageManager"
		try:
			oldCount = bus.get_object("com.victronenergy.settings", oldPath + "/Count").GetValue()
		# nothing to tranfer/delete
		except:
			return


		try:
			newCount = bus.get_object("com.victronenergy.settings", newPath + "/Count").GetValue()
		except:
			logging.error ("PackageManager dbus Settings has no package count")
			return

		# if the new dbus info has no packages, transfer them from the old location
		if newCount == 0:
			transferPackages = True
		else:
			transferPackages = False

		logging.warning ("moving PackageManager dbus settings from old location")
		
		# remove package-related Settings
		i = 0
		while i < oldCount:
			oldNamePath = oldPath + '/' + str (i) + "/PackageName"
			oldUserPath = oldPath + '/' + str (i) + "/GitHubUser"
			oldBranchPath = oldPath + '/' + str (i) + "/GitHubBranch"

			# create a new package and transfer old info to it
			try:
				name = bus.get_object("com.victronenergy.settings", oldNamePath).GetValue ()
			except:
				name = None
			if transferPackages and name != None:
				logging.warning ("moving " + name + " settings")
				PackageClass.AddPackage (packageName=name, source='INIT')
				package = PackageClass.LocatePackage (name)
				try:
					user = bus.get_object("com.victronenergy.settings", (oldUserPath)).GetValue ()
				except:
					user = "?"
				else:
					package.SetGitHubUser (user)
				try:
					branch = bus.get_object("com.victronenergy.settings", oldBranchPath).GetValue ()
				except:
					branch = "?"
				else:
					package.SetGitHubBranch (branch)

			# remove the old package-related dbus Settings
			cls.RemoveDbusSettings ( [oldNamePath, oldUserPath, oldBranchPath ] )
			i += 1

		# transfer and remove Settings not part of a package
		if transferPackages:
			
			DbusIf.SetAutoInstall ( bus.get_object("com.victronenergy.settings",
							oldPath + "/AutoInstall").GetValue () )
			DbusIf.SetAutoDownload ( bus.get_object("com.victronenergy.settings",
							oldPath + "/GitHubAutoDownload").GetValue () )
		otherSettings = [oldPath + "/AutoInstall",
							oldPath + "/GitHubAutoDownload",
							oldPath + "/Edit/GitHubBranch",
							oldPath + "/Edit/GitHubUser",
							oldPath + "/Edit/PackageName",
							oldPath + "/Count"
						]
		cls.RemoveDbusSettings ( otherSettings )

	
	#	UpdateStatus
	#
	# updates the status when the operation completes
	# the GUI provides three different areas to show status
	# where specifies which of these are updated
	#	'Download'
	#	'Install'
	#	'Editor'
	#	'Media'
	#	which determines where status is sent
	# message is the text displayed
	# if LogLevel is not 0, message is also written to the PackageManager log
	# logging levels: (can use numeric value or these variables set at head of module
	#	CRITICAL = 50
	#	ERROR = 40
	#	WARNING = 30
	#	INFO = 20
	#	DEBUG = 10
	# if where = None, no GUI status areas are updated


	def UpdateStatus ( self, message=None, where=None, logLevel=0 ):

		if logLevel != 0:
			logging.log ( logLevel, message )

		if where == 'Editor':
			DbusIf.SetEditStatus ( message )
		elif where == 'Install':
			DbusIf.SetInstallStatus ( message )
		elif where == 'Download':
			DbusIf.SetGitHubUpdateStatus (message)
		elif where == 'Media':
			DbusIf.SetMediaStatus (message)


	#	handleGuiEditAction (internal use only)
	#
	# the GUI uses packageMonitor service /GuiEditAction
	# to inform PackageManager of an action
	# a command is formed as "action":"packageName"
	#
	#	action is a text string: install, uninstall, download, etc
	#	packageName is the name of the package to receive the action
	#		for some acitons this may be the null string
	# this handler disposes of the request quickly by pushing
	#	the command onto a queue for later processing

	def handleGuiEditAction (self, path, command):

		global AddRemove
		AddRemove.PushAction ( command=command )

		return True	# True acknowledges the dbus change - other wise dbus parameter does not change

	def UpdatePackageCount (self):
		count = len(PackageClass.PackageList)
		self.DbusSettings['packageCount'] = count
	def GetPackageCount (self):
		return self.DbusSettings['packageCount']
	def SetAutoDownload (self, value):
		self.DbusSettings['autoDownload'] = value
	def GetAutoDownload (self):
		return self.DbusSettings['autoDownload']
	def GetAutoInstall (self):
		return self.DbusSettings['autoInstall']
	def SetAutoInstall (self, value):
		self.DbusSettings['autoInstall'] = value
	def SetGitHubUpdateStatus (self, value):
		self.DbusService['/GitHubUpdateStatus'] = value
	def SetInstallStatus (self, value):
		self.DbusService['/InstallStatus'] = value
	def SetMediaStatus (self, value):
		self.DbusService['/MediaUpdateStatus'] = value


	#	SetGuiEditAction
	# is part of the PackageManager to GUI communication
	# the GUI set's an action triggering some processing here
	# 	via the dbus change handler
	# PM updates this dbus value when processing completes 
	#	signaling either success or failure
	
	def SetGuiEditAction (self, value):
		self.DbusService['/GuiEditAction'] = value
	def GetGuiEditAction (self):
		return self.DbusService['/GuiEditAction']
	def SetEditStatus (self, message):
		self.DbusService['/GuiEditStatus'] = message

	# search default package list for packageName
	# and return the pointer if found
	#	otherwise return None
	#
	# Note: this method should be called with LOCK () set
	#	and use the returned value before UNLOCK ()
	#	to avoid unpredictable results
	#
	# DefaultPackages is a list of tuples:
	#	(packageName, gitHubUser, gitHubBranch)
	#
	# if a packageName match is found, the tuple is returned
	#	otherwise None is retuned

	def LocateDefaultPackage (self, packageName):
		
		for default in self.defaultPackages:
			if packageName == default[0]:
				return default
		return None
	

	# LOCK and UNLOCK - capitals used to make it easier to identify in the code
	#
	# these protect the package list from changing while the list is being accessed
	
	def LOCK (self):
		self.lock.acquire ()
	def UNLOCK (self):
		self.lock.release ()


	def __init__(self):
		self.lock = threading.RLock()

		settingsList = {'packageCount': [ '/Settings/PackageManager/Count', 0, 0, 0 ],
						'autoDownload': [ '/Settings/PackageManager/GitHubAutoDownload', 0, 0, 0 ],
						'autoInstall': [ '/Settings/PackageManager/AutoInstall', 0, 0, 0 ],
						}
		self.DbusSettings = SettingsDevice(bus=dbus.SystemBus(), supportedSettings=settingsList,
								timeout = 10, eventCallback=None )


		self.DbusService = VeDbusService ('com.victronenergy.packageManager', bus = dbus.SystemBus())
		self.DbusService.add_mandatory_paths (
							processname = 'PackageManager', processversion = 1.0, connection = 'none',
							deviceinstance = 0, productid = 1, productname = 'Package Monitor',
							firmwareversion = 1, hardwareversion = 0, connected = 1)
		self.DbusService.add_path ( '/GitHubUpdateStatus', "", writeable = True )
		self.DbusService.add_path ( '/InstallStatus', "", writeable = True )
		self.DbusService.add_path ( '/MediaUpdateStatus', "", writeable = True )
		self.DbusService.add_path ( '/GuiEditStatus', "", writeable = True )
		global Platform
		self.DbusService.add_path ( '/Platform', Platform )

		self.DbusService.add_path ( '/GuiEditAction', "", writeable = True,
										onchangecallback = self.handleGuiEditAction )

		# publish the default packages list and store info locally for faster access later
		section = 0
		self.defaultPackages = []
		try:
			listFile = open ("/data/SetupHelper/defaultPackageList", 'r')
		except:
			logging.error ("no defaultPackageList " + listFileName)
		else:
			for line in listFile:
				parts = line.split ()
				if len(parts) < 3 or line[0] == "#":
					continue
				prefix = '/Default/' + str (section) + '/'
				self.DbusService.add_path (prefix + 'PackageName', parts[0] )
				self.DbusService.add_path (prefix + 'GitHubUser', parts[1] )
				self.DbusService.add_path (prefix + 'GitHubBranch', parts[2] )
				
				self.defaultPackages.append ( ( parts[0], parts[1], parts[2] ) )
				section += 1
			listFile.close ()
			self.DbusService.add_path ('/DefaultCount', section )

		# a special package used for editing a package prior to adding it to Package list
		self.EditPackage = PackageClass (section = "Edit")


	#	RemoveDbusService
	#  deletes the dbus service

	def RemoveDbusService (self):
		logging.warning ("shutting down com.victronenergy.packageManager dbus service")
		self.DbusService.__del__()
	
# end DbusIf


#	PackageClass
#	Instances:
#		one per package
#
#	Methods:
#		LocatePackage
#		various Gets and Sets
#		AddPackagesFromDbus (class method)
#		AddDefaultPackages (class method)
#		AddStoredPackages (class method)
#		updateGitHubInfo (class method)
#			called only from AddPackage because behavior depends on who added the package
#		AddPackage (class method)
#		RemovePackage (class method)
#		UpdateFileVersions (class method)
#		UpdateAllFileVersions (class method)
#		UpdateInstallStateByPackage (class method)
#		UpdateInstallStateByName (class method)
#
#	Globals:
#		DbusSettings (for per-package settings)
#		DbusService (for per-package parameters)
#		DownloadPending
#		PackageList - list instances of all packages
#
# a package consits of Settings and version parameters in the package monitor dbus service
# all Settings and parameters are accessible via set... and get... methods
#	so that the caller does not need to understand dbus Settings and service syntax
# the packageName variable maintains a local copy of the dBus parameter for speed in loops
# section passed to init can be either a int or string ('Edit')
#	an int is converted to a string to form the dbus setting paths
#
# the dbus settings and service parameters managed here are on a per-package basis
#	unlike those managed in DbusIf which don't have a package association

class PackageClass:

	# list of instantiated Packages
	PackageList = []

	# search PackageList for packageName
	# and return the package pointer if found
	#	otherwise return None
	#
	# Note: this method should be called with LOCK () set
	#	and use the returned value before UNLOCK ()
	#	to avoid unpredictable results

	@classmethod
	def LocatePackage (cls, packageName):
		for package in PackageClass.PackageList:
			if packageName == package.PackageName:
				return package
		return None

	def SetPackageName (self, newName):
		self.DbusSettings['packageName'] = newName
		self.PackageName = newName

	def SetInstalledVersion (self, version):
		if self.installedVersionPath != "":
			DbusIf.DbusService[self.installedVersionPath] = version	
	def GetInstalledVersion (self):
		if self.installedVersionPath != "":
			return DbusIf.DbusService[self.installedVersionPath]
		else:
			return None
	def SetPackageVersion (self, version):
		if self.packageVersionPath != "":
			DbusIf.DbusService[self.packageVersionPath] = version	
	def GetPackageVersion (self):
		if self.packageVersionPath != "":
			return DbusIf.DbusService[self.packageVersionPath]
		else:
			return None
	def SetGitHubVersion (self, version):
		if self.gitHubVersionPath != "":
			DbusIf.DbusService[self.gitHubVersionPath] = version	
	def GetGitHubVersion (self):
		if self.gitHubVersionPath != "":
			return DbusIf.DbusService[self.gitHubVersionPath]
		else:
			return None

	def SetGitHubUser (self, user):
		self.DbusSettings['gitHubUser'] = user
	def GetGitHubUser (self):
		return self.DbusSettings['gitHubUser']
	def SetGitHubBranch (self, user):
		self.DbusSettings['gitHubBranch'] = user
	def GetGitHubBranch (self):
		return self.DbusSettings['gitHubBranch']

	def SetIncompatible(self, value):
		if self.incompatiblePath != "":
			DbusIf.DbusService[self.incompatiblePath] = value	
	def GetIncompatible (self):
		if self.incompatiblePath != "":
			return DbusIf.DbusService[self.incompatiblePath]
		else:
			return None

	def SetRebootNeeded (self, value):
		if self.rebootNeededPath != "":
			if value == True:
				DbusIf.DbusService[self.rebootNeededPath] = 1
			else:
				DbusIf.DbusService[self.rebootNeededPath] = 0
	def GetRebootNeeded (self):
		if self.rebootNeededPath != "":
			if DbusIf.DbusService[self.rebootNeededPath] == 1:
				return True
			else:
				return False
		else:
			return False

	# when setting GitHub user/branch, invalidate the GitHub version until it can be refreshed
	def SetGitHubUser (self, value):
		self.DbusSettings['gitHubUser'] = value
		if self.gitHubVersionPath != "":
			DbusIf.DbusService[self.gitHubVersionPath] = "?"
	def GetGitHubUser (self):
		return self.DbusSettings['gitHubUser']
	def SetGitHubBranch (self, value):
		self.DbusSettings['gitHubBranch'] = value
		if self.gitHubVersionPath != "":
			DbusIf.DbusService[self.gitHubVersionPath] = "?"
	def GetGitHubBranch (self):
		return self.DbusSettings['gitHubBranch']


	def settingChangedHandler (self, name, old, new):
		# when GitHub information changes, need to refresh GitHub version for this package
		if name == 'packageName':
			self.PackageName = new
		elif name == 'gitHubBranch' or name == 'gitHubUser':
			if self.PackageName != None and self.PackageName != "":
				DownloadGitHub.SetPriorityGitHubVersion (self.PackageName )

	def __init__( self, section, packageName = None ):
		# add package versions if it's a real package (not Edit)
		if section != 'Edit':
			section = str (section)
			self.installedVersionPath = '/Package/' + section + '/InstalledVersion'
			self.packageVersionPath = '/Package/' + section + '/PackageVersion'
			self.gitHubVersionPath = '/Package/' + section + '/GitHubVersion'
			self.rebootNeededPath = '/Package/' + section + '/RebootNeeded'
			self.incompatiblePath = '/Package/' + section + '/Incompatible'

			# create service paths if they don't already exist
			try:
				foo = DbusIf.DbusService[self.installedVersionPath]
			except:
				DbusIf.DbusService.add_path (self.installedVersionPath, "?" )
			try:
				foo = DbusIf.DbusService[self.gitHubVersionPath]
			except:
				DbusIf.DbusService.add_path (self.gitHubVersionPath, "?" )
			try:
				foo = DbusIf.DbusService[self.packageVersionPath]
			except:
				DbusIf.DbusService.add_path (self.packageVersionPath, "?" )
			try:
				foo = DbusIf.DbusService[self.rebootNeededPath]
			except:
				DbusIf.DbusService.add_path (self.rebootNeededPath, False )
			try:
				foo = DbusIf.DbusService[self.incompatiblePath]
			except:
				DbusIf.DbusService.add_path (self.incompatiblePath, "" )


		self.packageNamePath = '/Settings/PackageManager/' + section + '/PackageName'
		self.gitHubUserPath = '/Settings/PackageManager/' + section + '/GitHubUser'
		self.gitHubBranchPath = '/Settings/PackageManager/' + section + '/GitHubBranch'

		settingsList =	{'packageName': [ self.packageNamePath, '', 0, 0 ],
						'gitHubUser': [ self.gitHubUserPath, '', 0, 0 ],
						'gitHubBranch': [ self.gitHubBranchPath, '', 0, 0 ],
						}
		self.DbusSettings = SettingsDevice(bus=dbus.SystemBus(), supportedSettings=settingsList,
				eventCallback=self.settingChangedHandler, timeout = 10)
		# if packageName specified on init, use that name
		if packageName != None:
			self.DbusSettings['packageName'] = packageName
			self.PackageName = packageName
		# otherwise pull name from dBus Settings
		else:
			self.PackageName = self.DbusSettings['packageName']
		
		self.section = section
		# these flags are used to insure multiple actions aren't executed on top of each other
		self.DownloadPending = False
		self.InstallState = EXIT_SUCCESS


	# dbus Settings is the primary non-volatile storage for packageManager
	# upon startup, PackageList [] is empty and we need to populate it
	# from previous dBus Settings in /Settings/PackageManager/...
	# this is a special case that can't use AddPackage below:
	#	we do not want to create any new Settings !!
	#	it should be "safe" to limit the serch to 0 to < packageCount
	#	we also don't specify any parameters other than the section (index)
	#
	# NOTE: this method is called before threads are created so do not LOCK
	#
	# returns False if couldn't get the package count from dbus
	#	otherwise returns True
	# no package count on dbus is an error that would prevent continuing
	# this should never happen since the DbusIf is instantiated before this call
	#	which creates /Count if it does not exist

	@classmethod
	def AddPackagesFromDbus (cls):
		global DbusIf
		packageCount = DbusIf.GetPackageCount()
		if packageCount == None:
			logging.critical ("dbus PackageManager Settings not set up -- can't continue")
			return False
		i = 0
		while i < packageCount:
			cls.PackageList.append(PackageClass (section = i))
			i += 1
		return True


	# default packages are appended to the package list during program initialization
	#
	# a package may already be in the dbus list and will already have been added
	#	so these are skipped
	#
	# the default list is a tuple with packageName as the first element

	@classmethod
	def AddDefaultPackages (cls, initialList=False):
		for default in DbusIf.defaultPackages:
			packageName = default[0]
			DbusIf.LOCK ()
			package = cls.LocatePackage (packageName)
			DbusIf.UNLOCK ()			
			if package == None:
				cls.AddPackage ( packageName=packageName )


	# packaged stored in /data must also be added to the package list
	#	but package name must be unique
	# in order to qualify as a package:
	#	must be a directory
	#	name must not contain strings in the rejectList
	#	name must not include any spaces
	#	diretory must contain a file named version
	#	first character of version file must be 'v'

	rejectList = [ "-current", "-latest", "-main", "-test", "-debug", "-beta", "-backup1", "-backup2",
					"-0", "-1", "-2", "-3", "-4", "-5", "-6", "-7", "-8", "-9", " " ]

	@classmethod
	def AddStoredPackages (cls):

		for path in glob.iglob ("/data/*"):
			file = os.path.basename (path)
			if os.path.isdir (path) == False:
				continue
			rejected = False
			for reject in cls.rejectList:
				if reject in file:
					rejected = True
					break
			if rejected:
				continue
			versionFile = path + "/version"
			if os.path.isfile (versionFile) == False:
				continue
			fd = open (versionFile, 'r')
			version = fd.readline().strip()
			fd.close ()
			if version[0] != 'v':
				logging.warning  (file + " version rejected " + version)
				continue

			# skip if package was manually remove
			if os.path.exists (path + "/REMOVED"):
				continue

			# skip if package is for Raspberry PI only and platform is not
			global Platform
			if os.path.exists (path + "/raspberryPiOnly") and Platform[0:4] != 'Rasp':
				continue

			# continue only if package is unique
			DbusIf.LOCK ()
			package = cls.LocatePackage (file)
			DbusIf.UNLOCK ()			
			if package != None:
				continue
			
			cls.AddPackage ( packageName=file, source='AUTO' )
	
	
	# updateGitHubInfo fetchs the GitHub info and puts it in dbus settings
	#
	# There are three sources for this info:
	#	GUI 'EDIT' section (only used for adds from the GUI)
	#	the stored package (/data/<packageName>)
	#	the default package list
	# 
	# the sources are prioritized in the above order
	
	@classmethod
	def updateGitHubInfo (cls, packageName=None, source=None ):
		# if adding from GUI, get info from EditPackage
		#	check other sources if empty
		if source == 'GUI':
			gitHubUser = DbusIf.EditPackage.GetGitHubUser ()
			gitHubBranch = DbusIf.EditPackage.GetGitHubBranch ()
		# 'AUTO' source
		else:
			gitHubUser = ""
			gitHubBranch = ""

		# attempt to retrieve GitHub user and branch from stored pacakge
		# update only if not already set
		path = "/data/" + packageName + "/gitHubInfo" 
		if os.path.isfile (path):
			fd = open (path, 'r')
			gitHubInfo = fd.readline().strip()
			fd.close ()
			parts = gitHubInfo.split(":")
			if len (parts) >= 2:
				if gitHubUser == "":
					gitHubUser = parts[0]
				if gitHubBranch == "":
					gitHubBranch = parts[1]
			else:
				logging.warning (file + " gitHubInfo not formed properly " + gitHubInfo)

		# finally, pull GitHub info from default package list
		if gitHubUser == "" or gitHubBranch == "":
			default = DbusIf.LocateDefaultPackage (packageName)
			if default != None:
				if gitHubUser == "":
					gitHubUser = default[1]
				if gitHubBranch == "":
					gitHubBranch = default[2]

		# update dbus parameters
		DbusIf.LOCK ()
		package = PackageClass.LocatePackage (packageName)
		if package != None:
			package.SetGitHubUser (gitHubUser)
			package.SetGitHubBranch (gitHubBranch)
		DbusIf.UNLOCK ()

	# InstallState indicates a pending install operaiton
	#	or the returned exit status from the setup script
	# exit codes and other InstallState values are defined
	#	near the top of this file
	# unless the InstalState is EXIT_SUCCESS, additional
	#	install operations on this package are not permitted
	# InstallState is set to PENDING_ when an install/uninstall
	#	begins
	# InstallState is updated again when the install/unintsll
	#	completes (or fails)
	#
	# packageName rather than a package list reference (index, etc)
	# 	must be used because the latter can change when packages are removed
	#
	# UpdateInstallStateByPackage accepts a package  and assumes the list is already locked
	# UpdateInstallStateByName accepts a package NAME and locks the list and searches for
	#	the package name

	@classmethod
	def UpdateInstallStateByPackage (cls, package, state):
		package.InstallState = state

	@classmethod
	def UpdateInstallStateByName (cls, packageName, state):
		DbusIf.LOCK ()
		package = PackageClass.LocatePackage (packageName)
		if package != None:
				cls.UpdateInstallStateByPackage ( state )
		DbusIf.UNLOCK ()

		

	# AddPackage adds one package to the package list
	# packageName must be specified
	# the package names must be unique
	#
	# this method is called from the GUI add package command

	@classmethod
	def AddPackage ( cls, packageName=None, source=None ):
		if source == 'GUI':
			reportStatusTo = 'Editor'
		# AUTO or INIT source
		else:
			reportStatusTo = None

		if packageName == None or packageName == "":
			DbusIf.UpdateStatus ( message="no package name for AddPackage - nothing done",
							where=reportStatusTo, logLevel=ERROR )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
			return False


		# insure packageName is unique before adding this new package
		matchFound = False
		DbusIf.LOCK ()
		package = PackageClass.LocatePackage (packageName)

		# new packageName is unique, OK to add it
		if package == None:
			DbusIf.UpdateStatus ( message="Adding package " + packageName, where='Editor', logLevel=WARNING )

			section = len(cls.PackageList)
			cls.PackageList.append( PackageClass ( section, packageName = packageName ) )
			DbusIf.UpdatePackageCount ()

			cls.updateGitHubInfo (packageName=packageName, source=source)

			if source == 'GUI':
				DbusIf.SetGuiEditAction ( '' )
				# package added from the GUI (aka, manually)
				#	delete the removed flag if the package directory exists
				path = "/data/" + packageName + "/REMOVED"
				if os.path.exists (path):
					os.remove (path)
		else:
			if source == 'GUI':
				DbusIf.UpdateStatus ( message=packageName + " already exists - choose another name", where=reportStatusTo, logLevel=WARNING )
				DbusIf.SetGuiEditAction ( 'ERROR' )
			else:
				DbusIf.UpdateStatus ( message=packageName + " already exists", where=reportStatusTo, logLevel=WARNING )
		
		DbusIf.UNLOCK ()
	# end AddPackage

	# packages are removed as a request from the GUI
	# to remove a package:
	#	1) locate the entry matching package name  (if any)
	#	2) move all packages after that entry the previous slot (if any)
	#	3) erase the last package slot to avoid confusion (by looking at dbus-spy)
	#	3) remove the entry in PackageList (pop)
	#	4) update the package count
	#	5) set REMOVED flag file in the package directory in /data to prevent
	#		package from being re-added to the package list
	#		flag file is deleted when package is manually installed again
	#
	#	returns True if package was removed, False if not
	#
	#	this is all done while the package list is locked !!!!

	@classmethod
	def RemovePackage (cls, packageName ):
		if packageName == "SetupHelper":
			DbusIf.UpdateStatus ( message="REMOVING SetupHelper" + packageName, where='Editor', logLevel=CRITICAL )
		else:
			DbusIf.UpdateStatus ( message="removing " + packageName, where='Editor', logLevel=WARNING )
		DbusIf.LOCK ()
		packages = PackageClass.PackageList

		# locate index of packageName
		toIndex = 0
		listLength = len (packages)
		matchFound = False
		while toIndex < listLength:
			if packageName == packages[toIndex].PackageName:
				matchFound = True
				break
			toIndex += 1

		if matchFound:
			# move packages after the one to be remove down one slot (copy info)
			# each copy overwrites the lower numbered package
			fromIndex = toIndex + 1
			while fromIndex < listLength:
				toPackage = packages[toIndex]
				fromPackage = packages[fromIndex]
				toPackage.SetPackageName (fromPackage.PackageName )
				toPackage.SetGitHubUser (fromPackage.GetGitHubUser() )
				toPackage.SetGitHubBranch (fromPackage.GetGitHubBranch() )
				toPackage.SetGitHubVersion (fromPackage.GetGitHubVersion() )
				toPackage.SetInstalledVersion (fromPackage.GetInstalledVersion() )
				toPackage.SetPackageVersion (fromPackage.GetPackageVersion() )
				toPackage.SetRebootNeeded (fromPackage.GetRebootNeeded() )
				toPackage.SetIncompatible (fromPackage.GetIncompatible() )
				toPackage.DownloadPending = fromPackage.DownloadPending
				toPackage.InstallState = fromPackage.InstallState

				toIndex += 1
				fromIndex += 1

			# here, toIndex points to the last package in the old list
			toPackage = packages[toIndex]

			# can't actually remove service paths cleanly
			#	so just set contents to null/False
			# 	they will disappear after PackageManager is started the next time
			toPackage.SetGitHubVersion ("?")
			toPackage.SetInstalledVersion ("?")
			toPackage.SetPackageVersion ("?")

			# remove the Settings and service paths for the package being removed
			DbusIf.RemoveDbusSettings ( [toPackage.packageNamePath, toPackage.gitHubUserPath, toPackage.gitHubBranchPath] )

			# remove entry from package list
			packages.pop (toIndex)

			# update package count
			DbusIf.UpdatePackageCount ()		

		DbusIf.UNLOCK ()
		# flag this package was manually removed by setting the REMOVED flag file
		#	in the package directory
		if matchFound:
			if os.path.isdir ("/data/" + packageName):
				# equivalent to unix touch command
				open ("/data/" + packageName + "/REMOVED", 'a').close()

			DbusIf.UpdateStatus ( message="", where='Editor' )
			DbusIf.SetGuiEditAction ( '' )
		else:
			DbusIf.UpdateStatus ( message=packageName + " not removed - name not found", where='Editor', logLevel=ERROR )
			DbusIf.SetGuiEditAction ( 'ERROR' )


	#	UpdateFileVersions
	#
	# retrieves packages versions from the file system
	#	each package contains a file named version in it's root directory
	#		that becomes packageVersion
	#	the installedVersion-... file is associated with installed packages
	#		abesense of the file indicates the package is not installed
	#		presense of the file indicates the package is installed
	#		the content of the file is the actual version installed
	#		in prevous versions of the setup scripts, this file could be empty, 
	#		so we show this as "unknown"
	#
	# also sets incompatible parameter
	#
	# clears the InstallState if the PackageVersion version changes
	#
	# the single package variation is broken out so it can be called from other methods
	#	to insure version information is up to date before proceeding with an operaiton
	#
	# must be called while LOCKED !!
	#
	#
	#	UpdateAllFileVersions
	#
	#	loops through all packages and calls UpdateFileVersions for each package

	@classmethod
	def UpdateFileVersions (cls, package):

		packageName = package.PackageName

		# fetch installed version
		installedVersionFile = "/etc/venus/installedVersion-" + packageName
		try:
			versionFile = open (installedVersionFile, 'r')
		except:
			installedVersion = ""
		else:
			installedVersion = versionFile.readline().strip()
			versionFile.close()
			# if file is empty, an unknown version is installed
			if installedVersion ==  "":
				installedVersion = "unknown"
		package.SetInstalledVersion (installedVersion)

		# fetch package version (the one in /data/packageName)
		try:
			versionFile = open ("/data/" + packageName + "/version", 'r')
		except:
			packageVersion = ""
		else:
			packageVersion = versionFile.readline().strip()
			versionFile.close()

		# if packageVersion changed, update it and clear InstallState
		#	if the reason for the script failure might have been resolved by the new stored package
		if packageVersion != package.GetPackageVersion ():
			package.SetPackageVersion (packageVersion)
			state = package.InstallState
			if state == EXIT_FILE_SET_ERROR or state == EXIT_INCOMPATIBLE_VERSION\
						or state == EXIT_OPTIONS_NOT_SET or state == ERROR_NO_SETUP_FILE:
				package.InstallState = EXIT_SUCCESS

		# set the incompatible parameter
		#	to 'PLATFORM' or 'VERSION'
		global Platform
		incompatible = False
		if os.path.exists ("/data/" + packageName + "/raspberryPiOnly" ):
			if Platform[0:4] != 'Rasp':
				package.SetIncompatible ('PLATFORM')
				incompatible = True

		# platform is OK, now check versions
		if incompatible == False:
			# check version compatibility
			try:
				fd = open ("/data/" + packageName + "/firstCompatibleVersion", 'r')
			except:
				firstVersion = "v2.40"
			else:
				firstVersion = fd.readline().strip()
				fd.close ()
			try:
				fd = open ("/data/" + packageName + "/obsoleteVersion", 'r')
			except:
				obsoleteVersion = None
			else:
				obsoleteVersion = fd.readline().strip()
			
			global VersionToNumber
			global VenusVersion
			firstVersionNumber = VersionToNumber (firstVersion)
			obsoleteVersionNumber = VersionToNumber (obsoleteVersion)
			venusVersionNumber = VersionToNumber (VenusVersion)
			if venusVersionNumber < firstVersionNumber:
				self.SetIncompatible ('VERSION')
				incompatible = True
			elif obsoleteVersionNumber != 0 and venusVersionNumber >= obsoleteVersionNumber:
				package.SetIncompatible ('VERSION')
				incompatible = True

		# platform and versions OK, check to see if command line is needed for install
		# the optionsRequired flag in the package directory indicates options must be set before a blind install
		# the optionsSet flag indicates the options HAVE been set already
		# so if optionsRequired == True and optionsSet == False, can't install from GUI
		if incompatible == False:
			if os.path.exists ("/data/" + packageName + "/optionsRequired" ):
				if not os.path.exists ( "/data/setupOptions/" + packageName + "/optionsSet"):
					package.SetIncompatible ('CMDLINE')
					incompatible = True


	@classmethod
	def UpdateAllFileVersions (cls):
		DbusIf.LOCK ()
		for package in cls.PackageList:
			cls.UpdateFileVersions (package)
		DbusIf.UNLOCK ()

# end Package


#	DownloadGitHubPackagesClass
#	Instances:
#		DownloadGitHub (a separate thread)
#
#	Methods:
#		SetDownloadPending
#		ClearDownloadPending
#		updateGitHubVersion
#		updatePriorityGitHubVersion
#		SetPriorityGitHubVersion
#		GitHubDownload
#		downloadNeededCheck
#		processDownloadQueue
#		refreshGitHubVersion
#		run
#		StopThread
#
# downloads packages from GitHub, replacing the existing package
# 	if versions indicate a newer version
#
# the run () thread is only responsible for pacing automatic downloads from the internet
#	commands are pushed onto the processing queue (PushAction)
#
# the actual download (GitHubDownload) is called in the context of AddRemove
#

class DownloadGitHubPackagesClass (threading.Thread):

	def __init__(self):
		threading.Thread.__init__(self)
		self.DownloadQueue = queue.Queue (maxsize = 10)
		self.threadRunning = True
		# package needing immediate update
		self.priorityPackageName = None

	# the ...Pending flag prevents duplicate actions from piling up
	# automatic downloads are not queued if there is one pending
	#	for a specific package
	#
	# packageName rather than a package list reference (index, etc)
	# 	because the latter can change when packages are removed
	#
	# the pending flag is set at the beginning of the operation
	# 	because the GUI can't do that
	#	this doesn't close the window but narrows it a little

	
	def SetDownloadPending (self, packageName):
		package = PackageClass.LocatePackage (packageName)
		if package != None:
			package.downloadPending = True

	
	def ClearDownloadPending (self, packageName):
		package = PackageClass.LocatePackage (packageName)
		if package != None:
			package.downloadPending = False

	# fetches the GitHub version from the internet and stores it in the package
	#
	# this is called from the background thread run () below
	#	prior to checking to see if an automatic download is necessary
	#
	# if the wget fails, the GitHub version is set to ""
	# this will happen if the name, user or branch are not correct or if
	# there is no internet connection
	#
	# the package GitHub version is upated
	# but the version is also returned to the caller
	# TODO: check timeout

	def updateGitHubVersion (self, packageName, gitHubUser, gitHubBranch):

		url = "https://raw.githubusercontent.com/" + gitHubUser + "/" + packageName + "/" + gitHubBranch + "/version"
		try:
			proc = subprocess.Popen (["wget", "-qO", "-", url],
							stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		except:
			logging.error ("wget for version failed " + packageName)
			gitHubVersion = ""
		else:
			proc.wait()
			# convert from binary to string
			out, err = proc.communicate ()
			stdout = out.decode ().strip ()
			stderr = err.decode ().strip ()
			returnCode = proc.returncode
			if proc.returncode == 0:
				gitHubVersion = stdout
			else:
				gitHubVersion = ""

		# locate the package with this name and update it's GitHubVersion
		# if not in the list discard the information
		DbusIf.LOCK ()
		package = PackageClass.LocatePackage (packageName)
		if package != None:
			package.SetGitHubVersion (gitHubVersion)
		DbusIf.UNLOCK ()
		return gitHubVersion


	# handles priority GitHub version updates
	#	needed to show the version ASAP after
	#	gitHubUser or gitHubBranch change
	#
	# it is called from run () below
	#	waits to perform the next task

	def updatePriorityGitHubVersion (self):
		if self.priorityPackageName != None:
			name = self.priorityPackageName
			self.priorityPackageName = None
			DbusIf.LOCK ()
			package = PackageClass.LocatePackage (name)
			if package != None:
				user = package.GetGitHubUser ()
				branch = package.GetGitHubBranch ()
			DbusIf.UNLOCK ()
			if package != None:
				self.updateGitHubVersion (name, user, branch)
				return True
			else:
				logging.error ("can't fetch GitHub version - " + name + " not in list")
		return False


	#	SetPriorityGitHubVersion
	#
	# schedules the refresh of the GitHub version for a specific section
	#	called when the gitHubBranch changes in Settings
	#	so must return immediately
	# the refresh is performed in wait ()

	def SetPriorityGitHubVersion (self, packageName):
		self.priorityPackageName = packageName


	# this method downloads a package from GitHub
	# it is called from the queue command processor AddRemove.run()
	# also, download requests are pushed for automatic downloads from the loop below in run() method
	# and also for a manual download triggered from the GUI
	# statusMethod provides text status to the caller
	# callBack provides notificaiton of completion (or error)
	# automatic downloads that fail are logged but otherwise not reported
		
	def GitHubDownload (self, packageName= None, source=None):
		if source == 'GUI':
			where = 'Editor'
		elif source == 'AUTO':
			where = 'Download'
		else:
			where = None

		# to avoid thread confilcts, create a temp directory that
		# is unque to this program and this method
		# and make sure it is empty
		tempDirectory = "/var/run/packageManager" + str(os.getpid ()) + "GitHubDownload"
		if os.path.exists (tempDirectory):
			shutil.rmtree (tempDirectory)
		os.mkdir (tempDirectory)
		packagePath = "/data/" + packageName

		DbusIf.LOCK ()
		package = PackageClass.LocatePackage (packageName)
		gitHubUser = package.GetGitHubUser ()
		gitHubBranch = package.GetGitHubBranch ()
		DbusIf.UNLOCK ()

		DbusIf.UpdateStatus ( message="downloading " + packageName, where=where, logLevel=WARNING )
		self.SetDownloadPending (packageName)

		# create temp directory specific to this thread
		tempArchiveFile = tempDirectory + "/temp.tar.gz"
		# download archive
		if os.path.exists (tempArchiveFile):
			os.remove ( tempArchiveFile )

		url = "https://github.com/" + gitHubUser + "/" + packageName  + "/archive/" + gitHubBranch  + ".tar.gz"
		try:
			proc = subprocess.Popen ( ['wget', '-qO', tempArchiveFile, url ],\
										stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		except:
			DbusIf.UpdateStatus ( message="could not get archive on GitHub " + packageName,
										where=where, logLevel=ERROR )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
			return False
		else:
			proc.wait()
			stdout, stderr = proc.communicate ()
			# convert from binary to string
			stdout = stdout.decode ().strip ()
			stderr = stderr.decode ().strip ()
			returnCode = proc.returncode
			logging.warning (stderr)
			
		if returnCode != 0:
			DbusIf.UpdateStatus ( message="could not access" + packageName + ' ' + gitHubUser + ' '\
										+ gitHubBranch + " on GitHub", where=where, logLevel=WARNING )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
			self.ClearDownloadPending (packageName)
			shutil.rmtree (tempDirectory)
			return False
		try:
			proc = subprocess.Popen ( ['tar', '-xzf', tempArchiveFile, '-C', tempDirectory ],
										stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		except:
			DbusIf.UpdateStatus ( message="could not unpack " + packageName + ' ' + gitHubUser + ' ' + gitHubBranch,
										where=where, logLevel=ERROR )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
			self.ClearDownloadPending (packageName)
			shutil.rmtree (tempDirectory)
			return False

		proc.wait()
		stdout, stderr = proc.communicate ()
		# convert from binary to string
		stdout = stdout.decode ().strip ()
		stderr = stderr.decode ().strip ()
		returnCode = proc.returncode
		logging.error ("tar unpack from GitHub failed " + packageName)
		logging.error (stderr)

		if returnCode != 0:
			DbusIf.UpdateStatus ( message="could not unpack " + packageName + ' ' + gitHubUser + ' ' + gitHubBranch,
										where=where, logLevel=ERROR )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
			self.ClearDownloadPending (packageName)
			shutil.rmtree (tempDirectory)
			return False

		# attempt to locate a directory that contains a version file
		# the first directory in the tree starting with tempDicrectory
		# is returnd
		unpackedPath = LocatePackagePath (tempDirectory)
		if unpackedPath == None:
			self.ClearDownloadPending (packageName)
			shutil.rmtree (tempDirectory)
			logging.error ( "GitHubDownload: no archive path for " + packageName)
			return False

		# move unpacked archive to package location
		# LOCK this critical section of code to prevent others
		#	from accessing the directory while it's being updated
		packagePath = "/data/" + packageName
		tempPackagePath = packagePath + "-temp"
		DbusIf.LOCK ()
		if os.path.exists (packagePath):
			os.rename (packagePath, tempPackagePath)
		shutil.move (unpackedPath, packagePath)
		if os.path.exists (tempPackagePath):
			shutil.rmtree (tempPackagePath, ignore_errors=True)	# like rm -rf
		DbusIf.UNLOCK ()
		self.ClearDownloadPending (packageName)
		DbusIf.UpdateStatus ( message="", where=where )
		if source == 'GUI':
			DbusIf.SetGuiEditAction ( '' )
		shutil.rmtree (tempDirectory)
		return True
	# end GitHubDownload


	#	downloadNeededCheck
	#
	# compares versions to determine if a download is needed
	# returns: True if a download is needed, False otherwise
	# must be called with package list LOCKED !!
	
	def downloadNeededCheck (self, package):
		gitHubUser = package.GetGitHubUser ()
		gitHubBranch = package.GetGitHubBranch ()
		gitHubVersion = package.GetGitHubVersion ()
		packageVersion = package.GetPackageVersion ()


		# versions not initialized yet - don't allow the download
		if gitHubVersion == None or gitHubVersion == "" or gitHubVersion[0] != 'v' or packageVersion == '?':
			return False

		packageVersionNumber = VersionToNumber( packageVersion )
		gitHubVersionNumber = VersionToNumber( gitHubVersion )
		# if GitHubBranch is a version number, a download is needed if the versions differ
		if gitHubBranch[0] == 'v':
			if gitHubVersionNumber != packageVersionNumber:
				return True
			else:
				return False
		# otherwise the download is needed if the gitHubVersion is newer
		else:
			if gitHubVersionNumber > packageVersionNumber:
				return True
			else:
				return False


	#	processDownloadQueue
	#
	# pulls a command off DownloadQueue and processes it
	#
	# returns True of the download was attempted, False otherwise
	# this tells the caller not to do any auto installs this pass

	def processDownloadQueue (self):
		try:
			command = self.DownloadQueue.get_nowait()
		except queue.Empty:	# queue empty is OK
			return False
		except:
			logging.error ("pull from Install GUI queue failed")
			return False

		# got new action from queue - decode and process
		parts = command.split (":")
		if len (parts) >= 1:
			action = parts[0].strip()
		else:
			action = ""
		if len (parts) >= 2:
			packageName = parts[1].strip()
		else:
			packageName = ""

		if action == 'download':
			self.GitHubDownload (packageName=packageName, source='GUI' )
			return True

		# invalid action for this queue
		else:
			logging.error ("received invalid command from Install queue: ", command )
			return False

	#	refreshGitHubVersion
	#
	# refreshes the GitHub version for one package
	# called from run () below
	#
	# refresh rate is set in run () using the same logic
	#	as the download delay
	#
	# returns True if we reached the end of the package list
	#	implying all versions have been refreshed.

	def refreshGitHubVersion (self):
		timeToGo = self.versionRefreshDelay + self.lastGitHubVersionRefreshTime - time.time()
		# it's not time to download yet - update status message with countdown
		# see if it's time - return if not
		if timeToGo > 0:
			return False

		DbusIf.LOCK ()
		length = len (PackageClass.PackageList)
		endOfList = False
		if self.gitHubVersionPackageIndex >= length:
			self.gitHubVersionPackageIndex = 0
			endOfList = True
		package = PackageClass.PackageList[self.gitHubVersionPackageIndex]
		packageName = package.PackageName
		user = package.GetGitHubUser ()
		branch = package.GetGitHubBranch ()
		self.gitHubVersionPackageIndex += 1
		DbusIf.UNLOCK ()

		self.updateGitHubVersion (packageName, user, branch)
		self.lastGitHubVersionRefreshTime = time.time ()
		return endOfList

	#	DownloadGitHub run (the thread)

	# StopThread () is called to shut down the thread

	def StopThread (self):
		logging.info ("attempting to stop DownloadGitHub thread")
		self.threadRunning = False

	#	DownloadGitHub run ()
	#
	# updates GitHub versions
	#	a priority update triggered when GitHub info changes
	#	a backgroud update
	# downloads packages from
	#	GUI requests
	#	a background loop
	# the background loop always starts at the beginning of PackageList
	#	and stops when a package needing a download is found
	# on the next pass, (hopefully) that package download will have
	#	been satisfied and a new one will be found
	# when no updates are found, the download scan rate slows
	#	but a change in auto download mode will speed it up again
	#
	# run () checks the threadRunning flag and returns if it is False,
	#	essentially taking the thread off-line
	#	the main method should catch the tread with join ()

	def run (self):
		lastMode = AUTO_DOWNLOADS_OFF
		currentMode = AUTO_DOWNLOADS_OFF
		downloadDelay = 10.0	# start with fast scan
		lastAutoDownloadTime = 0.0
		self.gitHubVersionPackageIndex = 0
		self.lastGitHubVersionRefreshTime = 0.0
		self.versionRefreshDelay = 5.0
		allVersionsRefreshed = False
		firstPass = True	# do fast refresh after PackageManager startup

		while self.threadRunning:	# loop forever
			# process priority update if one is set
			priorityVersionProcessd = self.updatePriorityGitHubVersion ()
			if priorityVersionProcessd:
				time.sleep (5.0)
				continue

			# do one GitHub version refresh
			allVersionsRefreshed = self.refreshGitHubVersion ()

			# process one GUI download request
			# if there was one, skip auto downloads until next pass
			guiDownload = self.processDownloadQueue ()
			if guiDownload:
				time.sleep (5.0)
				continue

			# detect download mode changes and switch back to fast scan
			lastMode = currentMode
			currentMode = DbusIf.GetAutoDownload ()
			# all versions have been scanned, switch auto download mode as appropriate
			if allVersionsRefreshed:
				firstPass = False
				if currentMode == ONE_DOWNLOAD:
					DbusIf.SetAutoDownload (AUTO_DOWNLOADS_OFF)
				elif currentMode == FAST_DOWNLOAD:
					DbusIf.SetAutoDownload (NORMAL_DOWNLOAD)

			# set version refresh rate and download delay
			if firstPass or currentMode == ONE_DOWNLOAD or currentMode == FAST_DOWNLOAD:
				downloadDelay = 10.0
				self.versionRefreshDelay = 10.0
			else:
				downloadDelay = 600.0
				self.versionRefreshDelay = 60.0

			if currentMode != lastMode:
				if currentMode == ONE_DOWNLOAD or currentMode == FAST_DOWNLOAD:
					# reset the version list scan to first package
					self.gitHubVersionPackageIndex = 0
					# wait for scan to complete before switching modes
					allVersionsRefreshed = False

			if currentMode == AUTO_DOWNLOADS_OFF:
				# idle message
				DbusIf.UpdateStatus (message="", where='Download')
				time.sleep (5.0)
				continue

			# locate the first package that requires a download
			DbusIf.LOCK ()
			downloadNeeded = False
			for package in PackageClass.PackageList:
				# wait until all pending downloads are complete
				downloadPending = package.DownloadPending
				if downloadPending:
					downloadNeeded = False
					break
				downloadNeeded = self.downloadNeededCheck (package)
				if downloadNeeded:
					packageName = package.PackageName
					break
			DbusIf.UNLOCK ()

			if downloadNeeded:
				# see if it's time
				timeToGo = downloadDelay + lastAutoDownloadTime - time.time()
				# it's not time to download yet - update status message with countdown
				if timeToGo > 0:
					downloadNeeded = False
					if timeToGo > 90:
						statusMessage = packageName + " download begins in " + "%0.1f minutes" % ( timeToGo / 60 )
					elif  timeToGo > 1.0:
						statusMessage = packageName + " download begins in " + "%0.0f seconds" % ( timeToGo )
					DbusIf.UpdateStatus ( message=statusMessage, where='Download' )

					time.sleep (5.0)
					continue


			# do the download here
			if downloadNeeded:
				self.GitHubDownload (packageName=package.PackageName, source='AUTO' )
				lastAutoDownloadTime = time.time()
			time.sleep (5.0)
		# end while True
	# end run
# end DownloadGitHubPackagesClass
					

#	InstallPackagesClass
#	Instances:
#		InstallPackages (a separate thread)
#
#	Methods:
#		InstallPackage
#		run (the thread)
#		autoInstallNeeded
#		StopThread
#		run
#
# install and uninstall packages
# 	if versions indicate a newer version
# runs as a separate thread since the operations can take a long time
# 	and we need to space them to avoid consuming all CPU resources
#
# packages are automatically installed only
#	if the autoInstall Setting is active
#	package version is newer than installed version
#			or if nothing is installed
#
#	a manual install is performed regardless of versions

class InstallPackagesClass (threading.Thread):

	def __init__(self):
		threading.Thread.__init__(self)
		DbusIf.SetInstallStatus ("")
		self.threadRunning = True
		self.InstallQueue = queue.Queue (maxsize = 10)

	
	#	InstallPackage
	#
	# this method either installs or uninstalls a package
	# the choice is the direction value:
	# 		'install' or 'uninstall'
	# the operation can take many seconds
	# 	i.e., the time it takes to run the package's setup script
	#	do not call from a thread that should not block

	def InstallPackage ( self, packageName=None, source=None , direction='install' ):

		doNotInstallFile = "/data/" + packageName + "/DO_NOT_AUTO_INSTALL"

		# refresh versions, then check to see if an install is possible
		DbusIf.LOCK ()
		package = PackageClass.LocatePackage (packageName)
		PackageClass.UpdateFileVersions (package)
		state = package.InstallState

		# set/remove the do not install flag for manual operations
		if source == 'GUI':
			# uninstall sets the flag file
			if direction == 'uninstall':
				open (doNotInstallFile, 'a').close()
				logging.warning (packageName + " was manually uninstalled - auto install for that package will be skipped")
			# manual install removes the flag file
			else:
				if os.path.exists (doNotInstallFile):
					logging.warning (packageName + " was manually installed - allowing auto install for that package")
					os.remove (doNotInstallFile)

		if state != EXIT_SUCCESS:
			logging.error (direction + " blocked - state: " + state)
			return False

		if source == 'GUI':
			sendStatusTo = 'Editor'
		elif source == 'AUTO':
			sendStatusTo = 'Install'
			callBack = None

		setupFile = "/data/" + packageName + "/setup"
		if os.path.isfile(setupFile):
			if os.access(setupFile, os.X_OK) == False:
				DbusIf.UpdateStatus ( message="setup file for " + packageName + " not executable",
												where=sendStatusTo, logLevel=ERROR )
				if source == 'GUI':
					DbusIf.SetGuiEditAction ( 'ERROR' )
				PackageClass.UpdateInstallStateByPackage (package = package, state=ERROR_NO_SETUP_FILE)
				DbusIf.UNLOCK ()
				return
		else:
			DbusIf.UpdateStatus ( message="setup file for " + packageName + " doesn't exist",
											where=sendStatusTo, logLevel=ERROR )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
			PackageClass.UpdateInstallStateByPackage (package = package, state=ERROR_NO_SETUP_FILE)
			DbusIf.UNLOCK ()
			return

		DbusIf.UNLOCK ()

		# check the do not install flag before auto-installing
		if direction == 'install' and source == 'AUTO' and os.path.exists (doNotInstallFile):
			return

		# provide an innitial status message for the action since it takes a while for PackageManager
		#	to fill in EditStatus
		# this provides immediate user feedback that the button press was detected
		DbusIf.UpdateStatus ( message=direction + "ing " + packageName, where=sendStatusTo )
		try:
			proc = subprocess.Popen ( [ setupFile, direction, 'deferReboot' ],
										stdout=subprocess.PIPE, stderr=subprocess.PIPE )
		except:
			DbusIf.UpdateStatus ( message="could not run setup file for " + packageName,
										where=sendStatusTo, logLevel=ERROR )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
			return
		proc.wait()
		stdout, stderr = proc.communicate ()
		# convert from binary to string
		stdout = stdout.decode ().strip ()
		stderr = stderr.decode ().strip ()
		returnCode = proc.returncode

		# manage the result of the setup run while locked just in case
		DbusIf.LOCK ()

		package = PackageClass.LocatePackage (packageName)

		# set the InstallState with the setup script return code which is appropirate except for 
		#	ERROR_NO_SETUP_FILE which is set above
		PackageClass.UpdateInstallStateByPackage (package = package, state=returnCode)

		if returnCode == EXIT_SUCCESS:
			package.SetIncompatible ('')	# this marks the package as compatible
			DbusIf.UpdateStatus ( message="", where=sendStatusTo )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( '' )
		elif returnCode == EXIT_REBOOT:
			# set package RebootNeeded so GUI can show the need - does NOT trigger a reboot
			package.SetRebootNeeded (True)

			DbusIf.UpdateStatus ( message=packageName + " " + direction + " requires REBOOT",
											where=sendStatusTo, logLevel=WARNING )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'RebootNeeded' )
			# auto install triggers a reboot by setting the global flag - reboot handled in main_loop
			else:
				global SystemReboot
				SystemReboot = True
				DbusIf.UNLOCK ()
				return
		elif returnCode == EXIT_RUN_AGAIN:
			DbusIf.UpdateStatus ( message=packageName + " setup must be run from command line",
											where=sendStatusTo, logLevel=WARNING )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
		elif returnCode == EXIT_INCOMPATIBLE_VERSION:
			global VenusVersion
			package.SetIncompatible ('VERSION')
			DbusIf.UpdateStatus ( message=packageName + " not compatible with Venus " + VenusVersion,
											where=sendStatusTo, logLevel=WARNING )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
		elif returnCode == EXIT_INCOMPATIBLE_PLATFOM:
			global Platform
			package.SetIncompatible ('PLATFORM')
			DbusIf.UpdateStatus ( message=packageName + " " + direction + " not compatible with " + Platform,
											where=sendStatusTo, logLevel=WARNING )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
		elif returnCode == EXIT_OPTIONS_NOT_SET:
			DbusIf.UpdateStatus ( message=packageName + " " + direction + " setup must be run from the command line",
											where=sendStatusTo, logLevel=WARNING )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
		elif returnCode == EXIT_FILE_SET_ERROR:
			DbusIf.UpdateStatus ( message=packageName + " file set incomplete",
											where=sendStatusTo, logLevel=ERROR )
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )
		# unknown error
		elif returnCode != 0:
			DbusIf.UpdateStatus ( message=packageName + " " + direction + " unknown error " + str (returnCode),
											where=sendStatusTo, logLevel=ERROR )
			logging.error (stderr)
			if source == 'GUI':
				DbusIf.SetGuiEditAction ( 'ERROR' )

		DbusIf.UNLOCK ()
	# end InstallPackage ()


	#	autoInstallNeeded
	#
	# compares versions to determine if an install is needed
	#	returns True if an update is needed, False of not
	#
	# called from run() below - package list already locked
	
	def autoInstallNeeded (self, package):
		incompatible = package.GetIncompatible ()
		if incompatible != "":
			return False
		packageVersion = package.GetPackageVersion ()
		installedVersion = package.GetInstalledVersion ()
		# skip further checks if package version string isn't filled in
		if packageVersion == "" or packageVersion[0] != 'v':
			return False

		packageVersionNumber = VersionToNumber( packageVersion )
		installedVersionNumber = VersionToNumber( installedVersion )
		# skip install if versions are the same
		if packageVersion == installedVersion:
			return False
		else:
			return True


	#	processInstallQueue
	#
	# pulls a command off InstallQueue and processes it
	#
	# returns True if the install was attempted, False otherwise
	# this tells the caller not to do any auto installs this pass

	def processInstallQueue (self):
		try:
			command = self.InstallQueue.get_nowait ()
		except queue.Empty:	# queue empty is OK
			return False
		except:
			logging.error ("pull from Install GUI queue failed")
			return False

		# got new action from queue - decode and process
		parts = command.split (":")
		if len (parts) >= 1:
			action = parts[0].strip()
		else:
			action = ""
		if len (parts) >= 2:
			packageName = parts[1].strip()
		else:
			packageName = ""

		if action == 'install':
			self.InstallPackage (packageName=packageName, source='GUI' , direction='install' )
			return True
		elif action == 'uninstall':
			self.InstallPackage (packageName=packageName, source='GUI' , direction='uninstall' )
			return True
		# invalid action for this queue
		else:
			logging.error ("received invalid command from Install queue: ", command )
			return False


	#	InstallPackage run (the thread)
	#
	# automatic install packages
	#	pushes request on queue for processing later in another thread
	#		this allows this to run quickly while the package list is locked
	#
	# run () checks the threadRunning flag and returns if it is False,
	#	essentially taking the thread off-line
	#	the main method should catch the tread with join ()
	# StopThread () is called to shut down the thread

	def StopThread (self):
		logging.info ("attempting to stop InstallPackages thread")
		self.threadRunning = False
	def run (self):
		while self.threadRunning:
			# if processed a install/uninstall request from the GUI, skip auto installs until next pass
			if not self.processInstallQueue():
				DbusIf.LOCK ()
				for package in PackageClass.PackageList:
					if DbusIf.GetAutoInstall() == 1 and self.autoInstallNeeded (package):
						if package.InstallState == EXIT_SUCCESS:
	# TODO: makd sure InstallPacakge sets InstallState so this doesn't get called again - need versions updated too !!!!
							self.InstallPackage (packageName=package.PackageName, source='AUTO' , direction='install' )
							break 
				DbusIf.UNLOCK ()
			time.sleep (5.0)

# end InstallPackagesClass



#	MediaScanClass
#	Instances:
#		MediaScan (a separate thread)
#	Methods:
#		transferPackage
#		StopThread
#		run
#
#	scan removable SD and USB media for packages to be installed
#
#	run () is a separate thread that looks for removable
#	SD cards and USB sticks that appear in /media as separate directories
#	these directories come and go with the insertion and removable of the media
#
#	when new media is detected, it is scanned once then ignored
#	when media is removed, then reinserted, the scan begins again
#
#	packages must be located in the root of the media (no subdirecoties are scanned)
#	and must be an archive with a name ending in .tar.gz
#
#	archives are unpacked to a temp directory in /var/run (a ram disk)
#	verified, then moved into position in /data/<packageName>
#	where the name comes from the unpacked directory name
#	of the form <packageName>-<branch or version>
#
#	actual installation is handled in the InstallPackages run() thread

class MediaScanClass (threading.Thread):

	# transferPackage unpacks the archive and moves it into postion in /data
	#
	#	path is the full path to the archive

	def transferPackage (self, path):
		packageName = os.path.basename (path).split ('-', 1)[0]

		# create an empty temp directory in ram disk
		#	for the following operations
		# directory is unique to this process and thread
		tempDirectory = "/var/run/packageManager" + str(os.getpid ()) + "Media"
		if os.path.exists (tempDirectory):
			shutil.rmtree (tempDirectory)
		os.mkdir (tempDirectory)

		# unpack the archive - result is placed in tempDirectory
		try:
			proc = subprocess.Popen ( ['tar', '-xzf', path, '-C', tempDirectory ],
										stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		except:
			DbusIf.UpdateStatus ( message="tar failed for " + packageName,
									where='Media', logLevel=ERROR)
			time.sleep (5.0)
			DbusIf.UpdateStatus ( message="", where='Media')
			return False
		proc.wait()
		stdout, stderr = proc.communicate ()
		# convert from binary to string
		stdout = stdout.decode ().strip ()
		stderr = stderr.decode ().strip ()
		returnCode = proc.returncode
		if returnCode != 0:
			DbusIf.UpdateStatus ( message="could not unpack " + packageName + " from SD/USB media",
									where='Media', logLevel=ERROR)
			shutil.rmtree (tempDirectory)
			time.sleep (5.0)
			DbusIf.UpdateStatus ( message="", where='Media')
			return False

		# attempt to locate a package directory in the tree below tempDirectory
		unpackedPath = LocatePackagePath (tempDirectory)
		if unpackedPath == None:
			logging.warning (packageName + " archive doesn't contain a package directory - rejected" )
			shutil.rmtree (tempDirectory)
			time.sleep (5.0)
			DbusIf.UpdateStatus ( message="", where='Media')
			return False

		# TODO: do we want to compare versions and only replace the stored version if
		# TODO:		the media version is newer or not an exact match ?????

		# move unpacked archive to package location
		# LOCK this critical section of code to prevent others
		#	from accessing the directory while it's being updated
		DbusIf.UpdateStatus ( message="transfering " + packageName + " from SD/USB", where='Media', logLevel=WARNING )
		packagePath = "/data/" + packageName
		tempPackagePath = packagePath + "-temp"
		DbusIf.LOCK () 
		if os.path.exists (tempPackagePath):
			shutil.rmtree (tempPackagePath, ignore_errors=True)	# like rm -rf
		if os.path.exists (packagePath):
			os.rename (packagePath, tempPackagePath)
		shutil.move (unpackedPath, packagePath)
		if os.path.exists (tempPackagePath):
			shutil.rmtree (tempPackagePath, ignore_errors=True)	# like rm -rf
		DbusIf.UNLOCK ()
		shutil.rmtree (tempDirectory, ignore_errors=True)
		time.sleep (5.0)
		DbusIf.UpdateStatus ( message="", where='Media')
		return True
	# end transferPackage


	def __init__(self):
		threading.Thread.__init__(self)
		self.threadRunning = True


	#	Media Scan run (the thread)
	#
	# run () checks the threadRunning flag and returns if it is False,
	#	essentially taking the thread off-line
	#	the main method should catch the tread with join ()
	# StopThread () is called to shut down the thread

	def StopThread (self):
		logging.info ("attempting to stop MediaScan thread")
		self.threadRunning = False

	def run (self):
		separator = '/'
		root = "/media"
		archiveSuffix = ".tar.gz"

		# list of accepted branch/version substrings
		acceptList = [ "-current", "-latest", "-main", "-test", "-debug", "-beta", "-install", 
							"-0", "-1", "-2", "-3", "-4", "-5", "-6", "-7", "-8", "-9" ]

		# keep track of all media that's been scanned so it isn't scanned again
		# media removal removes it from this list
		alreadyScanned = []

		while self.threadRunning:
			try:
				drives = os.listdir (root)
			except:
				drives = []

			# if previously detected media is removed,
			#	allow it to be scanned again when reinserted
			for scannedDrive in alreadyScanned:
				if not scannedDrive in drives:
					alreadyScanned.remove (scannedDrive)

			for drive in drives:
				drivePath = separator.join ( [ root, drive ] )
				if drive in alreadyScanned:
					continue
				# check any file name ending with the achive suffix
				#	all others are skipped
				for path in glob.iglob (drivePath + "/*" + archiveSuffix):
					accepted = False
					if os.path.isdir (path):
						continue
					else:
						accepted = False
						baseName = os.path.basename (path)
						# verify the file name contains one of the accepted branch/version identifiers
						#	if not found in the list, the archive is rejected
						for accept in acceptList:
							if accept in baseName:
								accepted = True
								break
						# discovered what appears to be a valid archive
						# unpack it, do further tests and move it to /data 
						if accepted:
							self.transferPackage (path)
							if self.threadRunning == False:
								return
						else:
							logging.warning (path + " not a valid archive name - rejected")
				# end for path

				# mark this drive so it won't get scanned again
				#	this prevents repeated installs
				alreadyScanned.append (drive)
			#end for drive

			time.sleep (5.0)
			if self.threadRunning == False:
				return
	# end run ()
# end MediaScanClass


#	AutoRebootCheck
#
# packing installation and uninstallation may require
# 	a system reboot to fully activate it's resources
#
# this method scans the avalilable packages looking
#	for any pending operations (install, uninstall, download)
# it then checks the global RebootNeeded flag
# that is set if a setup script returns EXIT_REBOOT
#
# if no actions are pending and a reboot is needed,
#	AutoRebootCheck returns True

mainloop = None

def	AutoRebootCheck ():
	global SystemReboot
	
	actionsPending = False
	for package in PackageClass.PackageList:
		# check for operations pending
		if package.DownloadPending:
			actionsPending = True
	if SystemReboot and actionsPending == False:
		logging.warning ("package install/uninstall requeted a system reboot")
		return True
	else:
		return False


def mainLoop():
	global mainloop
	global rebootNow

	PackageClass.AddStoredPackages ()
	PackageClass.UpdateAllFileVersions ()

	rebootNeeded = AutoRebootCheck ()

	# reboot checks indicates it's time to reboot
	# quit the mainloop which will cause main to continue past mainloop.run () call in main
	if rebootNeeded:
		DbusIf.UpdateStatus ( message="REBOOTING ...", where='Download' )
		DbusIf.UpdateStatus ( message="REBOOTING ...", where='Editor' )

		mainloop.quit()
		return False
	# don't exit
	else:
		return True

#	main
#
# ######## code begins here
# responsible for initialization and starting main loop and threads
# also deals with clean shutdown when main loop exits
#

def main():
	global mainloop
	global SystemReboot
	
	SystemReboot = False

	# set logging level to include info level entries
	# TODO: change to INFO for debug
	logging.basicConfig( format='%(levelname)s:%(message)s', level=logging.WARNING )

	logging.warning (">>>> PackageManager starting")

	from dbus.mainloop.glib import DBusGMainLoop

	# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	DBusGMainLoop(set_as_default=True)

	# get venus version
	global VenusVersion
	versionFile = "/opt/victronenergy/version"
	try:
		file = open (versionFile, 'r')
	except:
		VenusVersion = ""
	else:
		VenusVersion = file.readline().strip()
		file.close()

	# get platform
	global Platform
	platformFile = "/etc/venus/machine"
	try:
		file = open (platformFile, 'r')
	except:
		Platform = "???"
	else:
		machine = file.readline().strip()
		if machine == "einstein":
			Platform = "Cerbo GX"
		elif machine == "bealglebone":
			Platform = "Venus GX"
		elif machine == "ccgx":
			Platform = "CCGX"
		elif machine == "canvu500":
			Platform = "CanVu 500"
		elif machine == "nanopi":
			Platform = "Multi/Easy Solar GX"
		elif machine == "raspberrypi2":
			Platform = "Raspberry Pi 2/3"
		elif machine == "raspberrypi4":
			Platform = "Raspberry Pi 4"
		else:
			Platform = machine
		file.close()

	# initialze dbus Settings and com.victronenergy.packageManager
	global DbusIf
	DbusIf = DbusIfClass ()
	
	PackageClass.AddPackagesFromDbus ()

	DbusIf.TransferOldDbusPackageInfo ()
	
	global DownloadGitHub
	DownloadGitHub = DownloadGitHubPackagesClass ()
	
	global InstallPackages
	InstallPackages = InstallPackagesClass ()

	global AddRemove
	AddRemove = AddRemoveClass ()

	global MediaScan
	MediaScan = MediaScanClass ()

	# initialze package list
	#	and refresh versions before starting threads
	#	and the background loop
	PackageClass.AddDefaultPackages ()
	PackageClass.AddStoredPackages ()
	PackageClass.UpdateAllFileVersions ()

	DownloadGitHub.start()
	InstallPackages.start()
	AddRemove.start()
	MediaScan.start ()

	# set up main loop - every 5 seconds
	GLib.timeout_add(5000, mainLoop)
	mainloop = GLib.MainLoop()
	mainloop.run()




	# this section of code runs only after the mainloop quits
	#	or if the debus Settings could not be set up (AddPackagesFromDbus fails)

	# stop threads, remove service from dbus
	logging.warning ("stopping threads")
	DownloadGitHub.StopThread ()
	InstallPackages.StopThread ()
	AddRemove.StopThread ()
	DbusIf.RemoveDbusService ()
	try:
		DownloadGitHub.join (timeout=30.0)
		InstallPackages.join (timeout=10.0)
		AddRemove.join (timeout=10.0)
	except:
		logging.critical ("attempt to join threads failed - one or more threads failed to exit")
		pass

	# check for reboot
	if SystemReboot:
		logging.warning ("REBOOTING: to complete package installation")

		try:
			proc = subprocess.Popen ( [ 'shutdown', '-r', 'now', 'rebooting to complete package installation' ] )
			# for debug:    proc = subprocess.Popen ( [ 'shutdown', '-k', 'now', 'simulated reboot - system staying up' ] )
		except:
			logging.critical ("shutdown failed")

		# insure the package manager service doesn't restart when we exit
		#	it will start up again after the reboot
		try:
			proc = subprocess.Popen ( [ 'svc', '-o', '/service/PackageManager' ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		except:
			logging.critical ("svc to shutdown PackageManager failed")

	logging.critical (">>>> PackageManager exiting")

	# program exits here

# Always run our main loop so we can process updates
main()





