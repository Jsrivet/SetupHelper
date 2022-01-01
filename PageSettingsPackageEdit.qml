/////// new menu for package version edit

import QtQuick 1.1
import "utils.js" as Utils
import com.victron.velib 1.0

MbPage {
	id: root
	title: platform.valid ? qsTr("Package editor") : qsTr ("Package manager not running")
    property string settingsPrefix: "com.victronenergy.settings/Settings/PackageManager"
    property string servicePrefix: "com.victronenergy.packageManager"
    property int packageIndex: 0
    property int defaultIndex:0
    property VBusItem defaultCount: VBusItem { bind: Utils.path(servicePrefix, "/DefaultCount") }
    property VBusItem packageCount: VBusItem { bind: Utils.path(settingsPrefix, "/Count") }
    property VBusItem editAction: VBusItem { bind: Utils.path(servicePrefix, "/GuiEditAction") }
    property VBusItem editStatus: VBusItem { bind: Utils.path(servicePrefix, "/GuiEditStatus") }
    property string packageName: packageNameBox.item.valid ? packageNameBox.item.value : ""
    property bool isSetupHelper: packageName == "SetupHelper"

    property VBusItem rebootNeeded: VBusItem { bind: getServiceBind ( "RebootNeeded") }
    property VBusItem guiRestartNeeded: VBusItem { bind: getServiceBind ( "GuiRestartNeeded") }
    property VBusItem incompatibleReason: VBusItem { bind: getServiceBind ( "Incompatible") }
    property VBusItem platform: VBusItem { bind: Utils.path(servicePrefix, "/Platform") }

    property bool addPackage: requestedAction == 'add' && showControls    
    property bool showControls: editAction.valid
    property bool gitHubValid: gitHubVersion.item.valid && gitHubVersion.item.value.substring (0,1) === "v"
    property bool packageValid: packageVersion.item.valid && packageVersion.item.value.substring (0,1) === "v"
    property bool installedValid: installedVersion.item.valid && installedVersion.item.value.substring (0,1) === "v"
    property bool downloadOk: gitHubValid && gitHubVersion.item.value != ""
    property bool installOk: packageValid && packageVersion.item.value  != "" && incompatibleReason.value == ""
    property string requestedAction: ''
    property bool actionPending: requestedAction != ''
    property bool navigate: ! actionPending && ! waitForAction && showControls
    property bool waitForAction: showControls && editAction.value != ''
    property bool moreActions: showControls && (editAction.value == 'RebootNeeded' || editAction.value == 'GuiRestartNeeded')

    property VBusItem defaultPackageName: VBusItem { bind: Utils.path ( servicePrefix, "/Default/", defaultIndex, "/", "PackageName" ) }
    property VBusItem defaultGitHubUser: VBusItem { bind: Utils.path ( servicePrefix, "/Default/", defaultIndex, "/", "GitHubUser" ) }
    property VBusItem defaultGitHubBranch: VBusItem { bind: Utils.path ( servicePrefix, "/Default/", defaultIndex, "/", "GitHubBranch" ) }
    property VBusItem editPackageName: VBusItem { bind: Utils.path ( settingsPrefix, "/Edit/", "PackageName" ) }
    property VBusItem editGitHubUser: VBusItem { bind: Utils.path ( settingsPrefix, "/Edit/", "GitHubUser" ) }
    property VBusItem editGitHubBranch: VBusItem { bind: Utils.path ( settingsPrefix, "/Edit/", "GitHubBranch" ) }


	Component.onCompleted:
	{
		resetPackageIndex ()
		resetDefaultIndex ()
	}
	
	function resetPackageIndex ()
	{
		if (packageIndex < 0)
			packageIndex = 0
		else if (packageIndex >= packageCount.value)
			packageIndex = packageCount.value - 1
	}
	
	function resetDefaultIndex ()
	{
		if (defaultIndex < 0)
			defaultIndex = 0
		else if (defaultIndex >= defaultCount.value)
			defaultIndex = defaultCount.value - 1
	}
	
	function getSettingsBind(param)
	{
		if (addPackage)
			return Utils.path(settingsPrefix, "/Edit/", param)
		else
		{
			resetPackageIndex ()
			return Utils.path(settingsPrefix, "/", packageIndex, "/", param)
		}
	}
	function getServiceBind(param)
	{
		if (addPackage)
			return Utils.path(servicePrefix, "/Default/", defaultIndex, "/", param)
		else
		{
			resetPackageIndex ()
			return Utils.path(servicePrefix, "/Package/", packageIndex, "/", param)
		}
	}
    
	// copy a set of default package values to Edit area when changing indexes
	function updateEdit ()
	{
		bindPrefix = Utils.path(servicePrefix, "/Default/", defaultIndex )
		editPackageName.setValue ( defaultPackageName.valid ? defaultPackageName.value : "??" )
		editGitHubUser.setValue ( defaultGitHubUser.valid ? defaultGitHubUser.value : "??" )
		editGitHubBranch.setValue ( defaultGitHubBranch.valid ? defaultGitHubBranch.value : "??" )
	}

    function nextIndex ()
    {
		if (addPackage)
		{
			defaultIndex += 1
			if (defaultIndex >= defaultCount.value)
				defaultIndex = defaultCount.value - 1
			updateEdit ()
		}
		else
			packageIndex += 1
			if (packageIndex >= packageCount.value)
 							packageIndex = packageCount.value - 1
   }
    function previousIndex ()
    {
		if (addPackage)
		{
			defaultIndex -= 1
			if (defaultIndex < 0)
				defaultIndex = 0
			updateEdit ()
		}
		else
			packageIndex -= 1
			if (packageIndex < 0)
				packageIndex = 0
    }
    function cancelEdit ()
    {
		requestedAction = ''
		editAction.setValue ( '' )
		editStatus.setValue ( '' )
    }
    function confirm ()
    {
        if (actionPending)
        {
			// provide local confirmation of action - takes PackageManager too long
			editStatus.setValue ( (requestedAction == 'remove' ? "removing " : requestedAction + "ing ") + packageName)
            editAction.setValue (requestedAction + ':' + packageName)
			requestedAction = ''
        }
    }
    function install ()
    {
		requestedAction = 'install'
    }
    function uninstall ()
    {
		requestedAction = 'uninstall'
    }
    function gitHubDownload ()
    {
		requestedAction = 'download'
    }
    function add ()
    {
		requestedAction = 'add'
    }
    function remove ()
    {
		requestedAction = 'remove'
    }
    function signalAdditionalAction ()
    {
		if (editAction.value == 'RebootNeeded')
		{
			// provide local confirmation of action - takes PackageManager too long
			editStatus.setValue ( "rebootng")
			editAction.setValue ( 'reboot' )
		}
		else if (editAction.value == 'GuiRestartNeeded')
		{
			// provide local confirmation of action - takes PackageManager too long
			editStatus.setValue ( "restarting GUI")
			editAction.setValue ( 'restartGui' )
		}
		requestedAction = ''
	}

	model: VisualItemModel
    {
        MbEditBox
        {
            id: packageNameBox
            description: qsTr ("Package name")
            maximumLength: 30
            item.bind: getSettingsBind ("PackageName")
            overwriteMode: false
            writeAccessLevel: User.AccessInstaller
            readonly: ! addPackage
            show: showControls
        }
        MbRowSmall
        {
            description: qsTr ("Versions")
            height: 25
            opacity: addPackage ? .0001 : 1
            Text
            {
                text: "GitHub:"
                font.pixelSize: 10
				show: showControls
            }
			show: showControls
            MbTextBlock
            {
                id: gitHubVersion
                item { bind: getServiceBind("GitHubVersion") }
                height: 25; width: 80
				show: showControls
            }
            Text
            {
                text: qsTr ("stored:")
                font.pixelSize: 10
				show: showControls
            }
            MbTextBlock
            {
                id: packageVersion
                item { bind: getServiceBind("PackageVersion") }
                height: 25; width: 80
				show: showControls
            }
            Text
            {
                text:
                {
					if (rebootNeeded.value == 1)
						return qsTr ("REBOOT:")
					else if (guiRestartNeeded.value == 1)
						return qsTr ("GUI\nRestart:")
					else
						return qsTr ("installed:")
				}
				horizontalAlignment: Text.AlignRight
				width: 50
                font.pixelSize: 10
				show: showControls && incompatibleReason.value == ""
            }
            MbTextBlock
            {
                id: installedVersion
                item { bind: getServiceBind("InstalledVersion") }
                height: 25; width: 80
				show: showControls && incompatibleReason.value == ""
            }
            Text
            {
				id: incompatibleText
				text:
				{
					if (incompatibleReason.value == 'PLATFORM')
						return ( qsTr ("not compatible with\n") + platformItem.value )
					else if (incompatibleReason.value == 'VERSION')
						return ( qsTr ("not compatible with\n") + vePlatform.version )
					else if (incompatibleReason.value == 'CMDLINE')
						return qsTr ("must install\nfrom command line" )
					else
						return qsTr ("compatible ???" ) // compatible for unknown reason
				}
				horizontalAlignment: Text.AlignHCenter
				width: 50 + 80 + 3
                font.pixelSize: 10
				show: showControls && ! incompatibleReason.value == ""
			}
        }
        MbEditBox
        {
            id: gitHubUser
            description: qsTr ("GitHub user")
            maximumLength: 20
            item.bind: getSettingsBind ("GitHubUser")
            overwriteMode: false
            writeAccessLevel: User.AccessInstaller
			show: showControls
        }
        MbEditBox
        {
            id: gitHubBranch
            description: qsTr ("GitHub branch or tag")
            maximumLength: 20
            item.bind: getSettingsBind ("GitHubBranch")
            overwriteMode: false
            writeAccessLevel: User.AccessInstaller
			show: showControls
        }

        // top row of buttons
        MbOK
        {
            id: addButton
            width: 140
            anchors { right: removeButton.left }
            description: ""
            value: qsTr("New package")
            onClicked: add ()
            writeAccessLevel: User.AccessInstaller
            show: navigate
        }
        MbOK
        {
            id: removeButton
            width: 170
            anchors { right: parent.right; bottom: addButton.bottom }
            description: ""
            value: qsTr("Remove package")
            onClicked: remove ()
            writeAccessLevel: User.AccessInstaller
            show: navigate && ! installedValid
        }
        MbOK
        {
            id: cancelButton
            width: 90
            anchors { right: parent.right; bottom: addButton.bottom }
            description: ""
            value: qsTr("Cancel")
            onClicked: cancelEdit ()
            show: showControls && ! navigate && ! waitForAction
        }
        MbOK
        {
            id: dismissErrorButton
            width: 90
            anchors { right: parent.right; bottom: addButton.bottom }
            description: ""
            value: qsTr("OK")
            onClicked: cancelEdit ()
            show: showControls && editAction.value == 'ERROR'
        }
        MbOK
        {
            id: laterButton
            width: 90
            anchors { right: parent.right; bottom: addButton.bottom }
            description: ""
            value: qsTr("Later")
            onClicked: cancelEdit ()
            show: moreActions
        }
        MbOK
        {
            id: nowButton
            width: 90
            anchors { right: laterButton.left; bottom: addButton.bottom }
            description: ""
            value: qsTr("Now")
            onClicked: signalAdditionalAction ()
            show: moreActions
        }
        MbOK
        {
            id: confirmButton
            width: 375
            anchors { left: parent.left; bottom: addButton.bottom }
            description: ""
            value: qsTr ("Proceed")
            onClicked: confirm ()
            show: showControls && ! navigate && actionPending
            writeAccessLevel: User.AccessInstaller
        }
        Text
        {
            id: statusMessage
            width: 250
            wrapMode: Text.WordWrap
            anchors { left: parent.left; leftMargin: 10; bottom: addButton.bottom; bottomMargin: 5 }
            font.pixelSize: 12
            color: actionPending && isSetupHelper && ! addPackage ? "red" : "black"
            text:
            {
				if (actionPending)
				{
					if (isSetupHelper && requestedAction == 'uninstall')
						return qsTr ("WARNING: SetupHelper is required for these menus - uninstall anyway ?")
					else
						return (requestedAction + " " + packageName + " ?")
				}
				else if (editStatus.valid && editStatus.value != "")
					return editStatus.value
				else
					return ""
			}
            show: waitForAction || actionPending
        }

        // bottom row of buttons
        MbOK
        {
            id: previousButton
            width: addPackage ? 230 : 100
            anchors { left: parent.left ; top:addButton.bottom }
            description: addPackage ? qsTr ("Import default") : ""
            value:
            {
				if (addPackage)
				{
					if (defaultIndex == 0)
						return qsTr ("First")
					else
						return qsTr ("Previous")
				}
				else
					return qsTr("Previous")
			}
            onClicked: previousIndex ()
            show:
            {
				if (! showControls)
					return false
				else if (addPackage)
					return true
				else
				{
					if (packageIndex > 0)
						return true
					else
						return false
				}
			}
        }
        MbOK
        {
            id: nextButton
            width: 75
            anchors { left: previousButton.right; bottom: previousButton.bottom }
            description: ""
            value:
            {
				if (addPackage)
				{
					if (defaultIndex == defaultCount.value - 1)
						return qsTr ("Last")
					else
						return qsTr ("Next")
				}
				else
					return qsTr("Next")
			}
            onClicked: nextIndex ()
            show:
            {
				if (! showControls)
					return false
				else if (addPackage)
					return true
				else
				{
					if (packageIndex < packageCount.value - 1)
						return true
					else
						return false
				}
			}
        }
        MbOK
        {
            id: downloadButton
            width: 110
            anchors { right: installButton.left; bottom: previousButton.bottom }
            description: ""
            value: qsTr ("Download")
			onClicked: gitHubDownload ()
           show: navigate && downloadOk
            writeAccessLevel: User.AccessInstaller
        }
        MbOK
        {
            id: installButton
            width: 90
            anchors { right: uninstallButton.left; bottom: previousButton.bottom }
            description: ""
            value: qsTr ("Install")
            onClicked: install ()
            show: navigate && installOk 
            writeAccessLevel: User.AccessInstaller
        }
        MbOK
        {
            id: uninstallButton
            width: 100
            anchors { right: parent.right; bottom: installButton.bottom }
            description: ""
            value: qsTr("Uninstall")
            onClicked: uninstall ()
            show: navigate && installedValid
            writeAccessLevel: User.AccessInstaller
        }
    }
}
