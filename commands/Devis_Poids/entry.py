import adsk.core
import os
from ...lib import fusion360utils as futil
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface
design = app.activeProduct
rootComp = design.rootComponent

# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_Devis_Poids'
CMD_NAME = 'Devis de Poids'
CMD_Description = 'Génère un listing des poids de l\'ensemble des corps du composant actif'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

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
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)

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
    # Création du champ de sélection des solides
    body_selection = inputs.addSelectionInput('selection_corps', 'Solides :','Choisir un solide')
    body_selection.setSelectionLimits(1,0)
    body_selection.addSelectionFilter('SolidBodies')


    # TODO Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    # TODO ******************************** Your code here ********************************

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs

    # Calcul de la masse total et du CdG de l'ensemble
    selection: adsk.core.CommandInput = inputs.itemById('selection_corps')
    
    solide=selection.selection(0).entity
    masse_tot=solide.physicalProperties.mass # masse en kg
    CdG_tot = solide.physicalProperties.centerOfMass

    if selection.selectionCount > 1: #si plus d'un solide est sélectionné
        for i in range(1,selection.selectionCount):
            solide=selection.selection(i).entity
            masse_temp=masse_tot
            masse_tot +=solide.physicalProperties.mass # masse en kg
            CdG_temp = CdG_tot
            CdG_tot.x = (CdG_temp.x*masse_temp + solide.physicalProperties.centerOfMass.x*solide.physicalProperties.mass)/masse_tot
            CdG_tot.y = (CdG_temp.y*masse_temp + solide.physicalProperties.centerOfMass.y*solide.physicalProperties.mass)/masse_tot
            CdG_tot.z = (CdG_temp.z*masse_temp + solide.physicalProperties.centerOfMass.z*solide.physicalProperties.mass)/masse_tot

    #On met tout ça dans un Sketch pour y accéder plus tard si nécessaire
    # Create a new sketch on the xy plane.
    sketches = rootComp.sketches;
    xyPlane = rootComp.xYConstructionPlane
    sketch = sketches.add(xyPlane)
    sketch.name = "CdG"

    # Get sketch points
    sketchPoints = sketch.sketchPoints
    
    # Create sketch point
    sketchPoint = sketchPoints.add(CdG_tot)

    msg = "Calcul terminé.<br>Masse totale: "+str(round(masse_tot,2))+" kg<br> Position du CdG:<br>   - en X: "+str(round(CdG_tot.x,2)) \
        +"<br>   - en Y: "+str(round(CdG_tot.y,2))+"<br>   - en Z: "+str(round(CdG_tot.z,2))
    ui.messageBox(msg)


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
