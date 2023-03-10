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
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_Equilibrium'
CMD_NAME = 'Trouver Equilibre 2D'
CMD_Description = "Pour un CdG donné, calcul le tirant d'eau et l'assiette de la coque"

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
    default_value = adsk.core.ValueInput.createByString('1500')
    inputs.addValueInput('weight_input', 'Weight value: ', "kg", default_value)

    #Add selection of CoG point (vertex, or sketch point generated by Devis_poids)
    cog_selection = inputs.addSelectionInput('cog_point', 'CoG point (sketchpoint) :','Choisir le point du CdG')
    cog_selection.setSelectionLimits(1,1)
    cog_selection.addSelectionFilter('SketchPoints')

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
    hull_selection: adsk.core.SelectionCommandInput = inputs.itemById('hull_surf')
    weight_input: adsk.core.ValueCommandInput = inputs.itemById('weight_input')
    cog_selection: adsk.core.SelectionCommandInput = inputs.itemById('cog_point')
    hull_body:adsk.fusion.BRepBody = hull_selection.selection(0).entity
    cog_point = cog_selection.selection(0).entity
    weight_value = weight_input.value
    #get associated 3Dpoint in the rootcomponent coord system
    cog_3Dpoint = cog_point.worldGeometry
    # ui.messageBox("x: "+str(cog_3Dpoint.x)+"<br>y: "+str(cog_3Dpoint.y)+"<br>z: "+str(cog_3Dpoint.z))
    
    #Create a plane at the waterline position
    z_min_cm=hull_body.boundingBox.minPoint.z
    #valeur en cm du pas de départ pour trouver le déplacement, on commence par 10% de la hauteur de la coque.
    step_cm = 0.1*abs(hull_body.boundingBox.maxPoint.z-hull_body.boundingBox.minPoint.z)

    plane_position = z_min_cm
    planeInput = planes.createInput()
    displacement=0
    threshold = 0.01 #seuil limite pour considérer qu'on a trouvé la bonne waterline
    loop=0
    while (abs(displacement-weight_value)/weight_value > threshold) and (loop<10):
        loop+=1
        if (displacement==-1) or (displacement>weight_value):
            #dans ce cas on divise le step par 2 et on revient un cran en arrière
            step_cm=step_cm/2
            plane_position-=step_cm
        else:
            #sinon on passe au step suivant
            plane_position+=step_cm
        offsetValue = adsk.core.ValueInput.createByReal(plane_position)
        planeInput.setByOffset(rootComp.xYConstructionPlane, offsetValue)
        planecurrent = planes.add(planeInput)
        displacement = get_displ(hull_body,planecurrent)
        planecurrent.deleteMe()
    #en sortie de cette boucle on a plane_position pour le bon déplacement
    #on peut calculer le tirant d'eau associé et l'afficher
    draft_cm = plane_position-z_min_cm
    msg="Pour un déplacement de "+str(round(displacement,0))+" kg,"
    msg+="<br> le tirant d'eau sera de "+str(round(draft_cm,1))+" cm."
    ui.messageBox(msg)

    #End of program:
    msg="End of program"
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


#Fonction de calcul et affichage des paramètres hydrostatiques
#prend comme input le volume immergé de la carène uniquement.
def get_displ(body:adsk.fusion.BRepBody, plane:adsk.fusion.ConstructionPlane):
    #retourne le poids déplacé, ou -1 si entrée d'eau à cette hauteur.
    #crée l'intersection entre la coque et le plan:
    sketch = sketches.add(plane)
    sketch.intersectWithSketchPlane([body])
    #vérifie si à cet enfoncement ça prend l'eau ou pas
    if sketch.profiles.count == 0:
        return -1
    #si on arrive là c'est que ça ne prend pas l'eau, on crée la surface waterplane_surf.
    patches = rootComp.features.patchFeatures
    patchInput = patches.createInput(sketch.profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    patch = patches.add(patchInput)
    waterplane_surf = patch.bodies.item(0)

    list_bodies_before_split=[bodies.item(i) for i in range(bodies.count)]
    z_min = round(body.boundingBox.minPoint.z,2)

    #Ensuite coupe la coque par le plan pour récupérer la partie immergée
    splitBodyFeats = rootComp.features.splitBodyFeatures
    splitBodyInput = splitBodyFeats.createInput(body, plane,True)
    splitBodyFeat = splitBodyFeats.add(splitBodyInput)    
    if not splitBodyFeat:
        ui.messageBox('split failed')
        return -1
    
    #et on ne garde que la partie sous l'eau
    for i in range(bodies.count):
        if (bodies.item(i)==body) or (bodies.item(i) not in list_bodies_before_split):
            if round(bodies.item(i).boundingBox.minPoint.z,2) == z_min:#If the lower one, we keep it.
                wet_surf= bodies.item(i)
                break
    
    #Enfin on crée un solide correspondant à la partie sous l'eau de la coque (volume déplacé)
    # Define tolerance with 1 mm = 0.1cm.
    tolerance = adsk.core.ValueInput.createByReal(0.1)
    #add surfaces to object collection
    surfaces = adsk.core.ObjectCollection.create()
    surfaces.add(waterplane_surf)
    surfaces.add(wet_surf)
    # Create a stitch feature.
    stitches = rootComp.features.stitchFeatures
    stitchInput = stitches.createInput(surfaces, tolerance, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    stitch = stitches.add(stitchInput)
    # récupère le volume immergé
    volume_deplace = stitch.bodies.item(0)
    if round(volume_deplace.volume,0)==0:
        ui.messageBox("La carene est manifestement percée, bouchez le trou avant de mettre à l'eau.")

    #stocke la valeur demandée
    deplacement = volume_deplace.volume/1000*config.WATER_DENSITY
    
    #nettoyage
    stitch.deleteMe()
    splitBodyFeat.deleteMe()
    patch.deleteMe()
    sketch.deleteMe()
    
    #renvoie la valeur demandée
    return deplacement
    #fin de la fonction