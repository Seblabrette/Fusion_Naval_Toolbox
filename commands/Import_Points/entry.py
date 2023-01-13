import adsk.core
import os
from ...lib import fusion360utils as futil
from ... import config
import csv


app = adsk.core.Application.get()
ui = app.userInterface
design = app.activeProduct
rootComp = design.rootComponent
sketches = rootComp.sketches;

# Set styles of file dialog.
fileDlg = ui.createFileDialog()
fileDlg.isMultiSelectEnabled = False
fileDlg.title = 'Select your points file'
fileDlg.filter = '*.csv'
 

# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_Import_Points'
CMD_NAME = 'Importer des points'
CMD_Description = 'Importe un tableau de cotes réunis dans une liste de points au format CSV'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = False

# TODO *** Define the location where the command button will be created. ***
# This is done by specifying the workspace, the tab, and the panel, and the 
# command it will be inserted beside. Not providing the command to position it
# will insert it at the end.
WORKSPACE_ID = 'FusionSolidEnvironment' # => Espace de travail CONCEPTION
PANEL_ID = 'NauticTools' #'SolidScriptsAddinsPanel' # => toolbarPanel
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    # Get the SOLID tab.
    solidTab = workspace.toolbarTabs.itemById('SolidTab')
    # Get the panel the button will be created in.
    panel = solidTab.toolbarPanels.itemById(PANEL_ID)
    if not panel:
        panel = solidTab.toolbarPanels.add(PANEL_ID, 'Nautic Tools', 'SelectPanel', False)
    # Create the button command control in the UI after the specified existing command.
    control = panel.controls.addCommand(cmd_def)#, COMMAND_BESIDE_ID, False)

    # Specify if the command is promoted to the main toolbar. 
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # TODO Define the dialog for your command by adding different inputs to the command.
    #No command inputs created for this function, go directly to command_execute function.
    

    # TODO Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    # futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    # futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    # futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    # futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    # TODO ******************************** Your code here ********************************
    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs

    # Show file open dialog
    dlgResult = fileDlg.showOpen()
    if dlgResult == adsk.core.DialogResults.DialogOK:
        msg = '\nFiles to Open:'
        msg += '\n\t{}'.format(fileDlg.filename)
    else:
        return       
    
    #Processing the selected file
    listing=[]
    with open(fileDlg.filename, 'r',encoding="utf-8") as f:
        f.readline() #skip first line containing headers
        curr_line=1 #tracking the file current line number
        while True:
            text = f.readline()
            curr_line+=1
            if text:
                if text.find("\n")>=0:
                    text = text.replace('\n','')
                try:
                    listing.append([float(text.split(';')[0]),float(text.split(';')[1]),float(text.split(';')[2])])
                except:
                    msg='Error at line '+str(curr_line)+':<br>'+text+'<br>'
                    msg+='Make sure coordinates have 0.00 format separated by ";" character.'
                    ui.messageBox(msg)
                    return
            else:
                break
    #listing is a list containing the 3 coordinates of each point.
    #Now, lets create group of points per X coordinate
    grouped_points={}
    for point in listing:
        x_coord=point[0]
        if x_coord in grouped_points.keys():
            grouped_points[x_coord].append(point)
        else:
            grouped_points[x_coord]=[point]
    #Now, lets create a list of groups with X in ascending order:
    groups = list(grouped_points.keys())
    groups.sort()

    #Now, let's create a sketch for each group of points
    for x in groups:
        # Create a new sketch on the offsetted yz plane.
        # Get construction planes
        planes = rootComp.constructionPlanes
        # Create construction plane input
        planeInput = planes.createInput()
        # Add construction plane by offset
        offsetValue = adsk.core.ValueInput.createByReal(x)
        planeInput.setByOffset(rootComp.yZConstructionPlane, offsetValue)
        planeOne = planes.add(planeInput)
        planeOne.name = "X="+str(x)
        sketch = sketches.add(planeOne)
        sketch.name = "Points at X="+str(x)
        # Get sketch points
        sketchPoints = sketch.sketchPoints
        # Create sketch point
        for coord in grouped_points[x]:#go through each point of the group at x.
            #Attention: coordinates of point in the local coordinate system of the sketch
            point = adsk.core.Point3D.create(-coord[2], coord[1],coord[0]) 
            # ui.messageBox(str(coord[0])+" / "+str(coord[1])+" / "+str(coord[2]))
            somepoint = sketchPoints.add(point)
    #Conclusion message:
    ui.messageBox('Import successful!<br>'+str(len(listing))+' points imported in total.')


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Validate Input Event')

    inputs = args.inputs
    
    # Verify the validity of the input values. This controls if the OK button is enabled or not.
    valueInput = inputs.itemById('value_input')
    if valueInput.value >= 0:
        args.areInputsValid = True
    else:
        args.areInputsValid = False
        

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []
