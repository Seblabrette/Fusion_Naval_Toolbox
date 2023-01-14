import adsk.core
import adsk.fusion
import os
from ...lib import fusion360utils as futil
from ... import config


app = adsk.core.Application.get()
ui = app.userInterface
design = app.activeProduct
rootComp = design.rootComponent
sketches = rootComp.sketches
planes = rootComp.constructionPlanes
bodies = rootComp.bRepBodies

# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_Disp_calc'
CMD_NAME = 'Calculer déplacement'
CMD_Description = 'Calcule le déplacement de carène en fonction du tirant d\'eau'

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
    # Création du champ de sélection de la surface
    body_selection = inputs.addSelectionInput('hull_surf', 'Hull surface :','Choisir la surface de la carène')
    body_selection.setSelectionLimits(1,1)
    body_selection.addSelectionFilter('SurfaceBodies')

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = app.activeProduct.unitsManager.defaultLengthUnits
    default_value = adsk.core.ValueInput.createByString('25')
    inputs.addValueInput('draft_input', 'Draft value: ', defaultLengthUnits, default_value)

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
    #retrieve input data from the dialog:
    value_draft_cm: adsk.core.ValueCommandInput = inputs.itemById('draft_input')
    recup_selection: adsk.core.SelectionCommandInput = inputs.itemById('hull_surf')
    recup_object:adsk.fusion.BRepBody = recup_selection.selection(0).entity
    #Create a plane at the waterline position
    z_min_cm=recup_object.boundingBox.minPoint.z
    offset = z_min_cm+value_draft_cm.value
    # Add construction plane by offset
    planeInput = planes.createInput()
    offsetValue = adsk.core.ValueInput.createByReal(offset)
    planeInput.setByOffset(rootComp.xYConstructionPlane, offsetValue)
    planeOne = planes.add(planeInput)
    planeOne.name = "Waterline"

    #Create the surface at the waterline:
    sketch = sketches.add(planeOne)
    courbes_intersection = sketch.intersectWithSketchPlane([recup_object])
    if sketch.profiles.count == 0:
        ui.messageBox("La surface prend l'eau à cet enfoncement. Réduisez le tirant d'eau.")
        sketch.deleteMe()
        planeOne.deleteMe()
        return
    patches = rootComp.features.patchFeatures
    patchInput = patches.createInput(sketch.profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    patch = patches.add(patchInput)
    surf_intersect_waterline = patch.bodies.item(0)
    surf_intersect_waterline.name="surface_waterline"
    # Verify that there is intersection with the waterline plane, and stop if not.
    if not courbes_intersection:
        ui.messageBox('The hull does not intersect with surface, please provide a different draft value.')
        return
    #creation d'une copie temporaire de la carène
    tempHullCopy = recup_object.copyToComponent(rootComp) #BRepBody
    tempHullCopy.name="tempHullCopy"
    #Ensuite on crée un split body feature pour diviser le corps en deux
    splitBodyFeats = rootComp.features.splitBodyFeatures
    splitBodyInput = splitBodyFeats.createInput(tempHullCopy, planeOne,True)
    splitBodyFeat = splitBodyFeats.add(splitBodyInput)    
    if not splitBodyFeat:
        ui.messageBox('split failed')
        return
    #et on ne garde que la partie sous l'eau
    for i in range(bodies.count):
        temp_surf=bodies.item(i)
        if "tempHullCopy" in temp_surf.name: #it is one of the newly created objects
            if round(temp_surf.boundingBox.minPoint.z,8) == round(z_min_cm,8):#If the lower one, we keep it.
                wet_surf= temp_surf
                wet_surf.name="Underwater_part"
            else:
                temp_surf.name="deleteMe"
                i-=1
                removeFeat = rootComp.features.removeFeatures.add(temp_surf)


    #Enfin on crée un solide correspondant à la partie sous l'eau de la coque (volume déplacé)
    # Define tolerance with 1 mm = 0.1cm.
    tolerance = adsk.core.ValueInput.createByReal(0.1)
    #add surfaces to object collection
    surfaces = adsk.core.ObjectCollection.create()
    surfaces.add(surf_intersect_waterline)
    surfaces.add(wet_surf)
    stitches = rootComp.features.stitchFeatures
    stitchInput = stitches.createInput(surfaces, tolerance, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    
    # Create a stitch feature.
    
    stitch = stitches.add(stitchInput)
    volume_deplace = stitch.bodies.item(0)
    volume_deplace.name="Volume déplacé"
    if round(volume_deplace.volume,0)==0:
        ui.messageBox("La carene est manifestement percée, bouchez le trou avant de mettre à l'eau.")
        stitch.deleteMe()
        splitBodyFeat.deleteMe()
        wet_surf.deleteMe()
        patch.deleteMe()
        sketch.deleteMe()
        planeOne.deleteMe()
        return
    deplacement = volume_deplace.volume/1000
    #End of program:
    msg="Pour un tirant d'eau de "+str(round(value_draft_cm.value*10,2))+" mm,<br>"
    msg+="Le déplacement est de :"+str(round(deplacement, 2))+" kg."
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
    valueInput = inputs.itemById('draft_input')
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
