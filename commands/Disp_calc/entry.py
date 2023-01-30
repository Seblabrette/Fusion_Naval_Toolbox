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

    #Add slider for selection of number of sections for the areas curves
    sliderinput = inputs.addIntegerSliderCommandInput('nbsections', "Sections:", 5, 30)
    sliderinput.valueOne = 10 #sets default value to 10 sections

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
    sliderinput:adsk.core.IntegerSliderCommandInput = inputs.itemById('nbsections')
    nb_sections = sliderinput.valueOne #we take value from slider

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

    #appel à la fonction de calcul des paramètres hydrostatiques sur un volume donné
    #display_hydrostatics(volume_deplace)
    
    #appel à la fonction de calcul de la courbe des aires
    courbe_des_aires(volume_deplace,nb_sections)

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
def display_hydrostatics(body:adsk.fusion.BRepBody):
    disp_vol = body.volume
    water_density = 1.025/1000 #kg/cm3
    disp_weight = disp_vol*water_density
    
    #Find waterplane
    ref_vector = adsk.core.Vector3D.create(0,0,1)
    for face in body.faces:
        point = adsk.core.Point2D.create(0.5,0.5)
        normal_vector = face.evaluator.getNormalAtParameter(point)[1]
        if ref_vector.angleTo(normal_vector)<0.01:
            #Face du plan de flottaison trouvée, on la stocke.
            waterplane = face
            break
    waterplane_area = waterplane.area
    LWL = waterplane.boundingBox.maxPoint.x - waterplane.boundingBox.minPoint.x #Length at waterline
    beam_WL = waterplane.boundingBox.maxPoint.y - waterplane.boundingBox.minPoint.y #Beam at waterline
    wetted_area = body.area - waterplane_area #surface mouillée en cm2

    #centre de flottaison
    CoB = body.physicalProperties.centerOfMass #Point3D object for center of buoyancy
    #Position of CoB from Midship
    x_midship = (waterplane.boundingBox.maxPoint.x + waterplane.boundingBox.minPoint.x)/2
    pos_CoB_pct = (CoB.x - x_midship)*100/x_midship


    msg="Paramètres hydro statiques:"
    msg+="<br>Déplacement = "+str(round(disp_weight))+" kg"
    msg+="<br>Longueur Flottaison = "+str(round(LWL/100,3))+" m"
    msg+="<br>Bau maxi flottaison = "+str(round(beam_WL/100,3))+" m"
    msg+="<br>Surface mouillée = "+str(round(wetted_area/10000,3))+" m2"
    msg+="<br>Position Longi du centre de flottaison = "+str(round(pos_CoB_pct,2))+" %"
    ui.messageBox(msg)

def courbe_des_aires(body:adsk.fusion.BRepBody, sections:int):
    # Le but est de couper la partie immergée de la carène en plusieurs sections,et pour chacune d'elle
    # de déterminer l'aire de la section. Ensuite on stocke tout et on trace la courbe.
    NOMBRE_SECTIONS=sections
    LWL=body.boundingBox.maxPoint.x-body.boundingBox.minPoint.x
    start_x = body.boundingBox.minPoint.x
    planeInput = planes.createInput() #crée objet planeInput pour pouvoir créer des plans.
    aires=[0 for i in range(NOMBRE_SECTIONS+1) ]
    pos_x = [0 for i in range(NOMBRE_SECTIONS+1) ]
    offset_z = body.boundingBox.maxPoint.z #pour aligner la courbe des aires sur la waterline
    for i in range(NOMBRE_SECTIONS+1):
        pos_x[i]=start_x+i*LWL/NOMBRE_SECTIONS #position de la section courante
        #crée un plan décalé à cette position
        offsetValue = adsk.core.ValueInput.createByReal(pos_x[i])
        planeInput.setByOffset(rootComp.yZConstructionPlane, offsetValue)
        planecurrent = planes.add(planeInput)
        planecurrent.name = "Section @ "+str(round(pos_x[i],1))+" cm"
        #crée un sketch sur ce plan
        sketch = sketches.add(planecurrent)
        sketch.name = "Section @ "+str(round(pos_x[i],1))+" cm"
        # crée l'intersection du corps étudié avec ce plan
        sketch.intersectWithSketchPlane([body])
        #récupère son aire
        if sketch.sketchCurves.count == 0:
            #TODO: problème identifié, certaines sections ne donnent pas des loops...bizare...mais à résoudre.
            aires[i]=0
        else:
            if sketch.profiles.count==0:
                #cas particulier où ça ne crée pas un profile (ça devrait tt le tps, mais ça arrive que non)
                #on recrée une surface avec les courbes du sketch...
                patches = rootComp.features.patchFeatures
                patchInput = patches.createInput(sketch.sketchCurves.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                patch = patches.add(patchInput)
                face=patch.faces.item(0)
                aires[i]= face.area
                patch.deleteMe()
            else:
                for j in range(sketch.profiles.count): #boucle sur toutes les surfaces du sketch (1 seule normalement)
                    profile_current=sketch.profiles.item(j)
                    aires[i]+=round(profile_current.areaProperties().area,2) #en cm^2
        #efface ce qu'on a créé
        sketch.deleteMe()
        planecurrent.deleteMe()

    #trouve la section proche de la section max et les deux qui les entoure:
    sec=[(0,0),(0,0),(0,0),(0,0),(0,0)] #(aire, pos_x) tuples.
    for i in range(1,NOMBRE_SECTIONS-1):
        if (aires[i+1]>aires[i]) and (aires[i+1]>aires[i+2]):
            sec[0]=(aires[i], pos_x[i])
            sec[2] = (aires[i+1], pos_x[i+1])
            sec[4] = (aires[i+2], pos_x[i+2])
            break
    #a partir de ces sections encadrantes, on va chercher plus finement
    precision=0.05 #seuil pour considérer qu'on a la section max.
    section_max(body,sec,precision)

    #crée un sketch pour tracer la courbe des aires:
    pos_y=(body.boundingBox.maxPoint.y+body.boundingBox.minPoint.y)/2
    offsetValue = adsk.core.ValueInput.createByReal(pos_y)
    planeInput.setByOffset(rootComp.xZConstructionPlane, offsetValue)
    planecurrent = planes.add(planeInput)
    planecurrent.name = "Areas Curve"
    sketch = sketches.add(planecurrent)
    sketch.name = "Areas Curve"
    sketchPoints = sketch.sketchPoints
    points = adsk.core.ObjectCollection.create()
    for i in range(NOMBRE_SECTIONS+1):
        #crée un point3D avec la pos_X en abscisse et l'aire en ordonnée
        #Attention: coordinates of point in the local coordinate system of the sketch
        point = adsk.core.Point3D.create(pos_x[i], -aires[i]/10-offset_z,0) #Z=0 to create in the plane.
        sketchPoints.add(point)
        points.add(point)
    spline = sketch.sketchCurves.sketchFittedSplines.add(points)

    msg="Calcul de la courbe des aires terminé."
    ui.messageBox(msg)

def section_max(body:adsk.fusion.BRepBody,sec,precision:float):
    start_x = body.boundingBox.minPoint.x
    trigger=(body.boundingBox.maxPoint.x-body.boundingBox.minPoint.x)*precision
    planeInput = planes.createInput()
    counter=0
    while (abs(sec[4][1]-sec[0][1]) > trigger) and (counter < 100):
        counter+=1
        #récupère section entre chaque section inf,bau et sup
        sec[1] = get_mid_sect(body, sec[0], sec[2], planeInput)
        sec[3] = get_mid_sect(body, sec[2], sec[4], planeInput)
        for i in range(3):
            if (sec[i+1][0]>sec[i][0]) and (sec[i+1][0]>sec[i+2][0]):
                tmp1 = sec[i]
                tmp2 = sec[i+1]
                tmp3 = sec[i+2]                
                sec[0] = tmp1
                sec[1] = (0,0)
                sec[2] = tmp2
                sec[3] = (0,0)
                sec[4] = tmp3
                break
    msg="section max = "+str(round(sec[2][0],2))+" cm2."
    msg+="<br> @ x = "+str(round(sec[2][1],2))+" cm."
    ui.messageBox(msg)

def get_mid_sect(body, tuple_inf, tuple_sup, planeInput):
    pos_x=(tuple_inf[1]+tuple_sup[1])/2 #position de la section courante
    #crée un plan décalé à cette position
    offsetValue = adsk.core.ValueInput.createByReal(pos_x)
    planeInput.setByOffset(rootComp.yZConstructionPlane, offsetValue)
    planecurrent = planes.add(planeInput)
    #crée un sketch sur ce plan
    sketch = sketches.add(planecurrent)
    #crée l'intersection du corps étudié avec ce plan
    sketchEntities = sketch.intersectWithSketchPlane([body])
    aire=0
    for j in range(sketch.profiles.count): #boucle sur toutes les surfaces du sketch (1 seule normalement)
        profile_current=sketch.profiles.item(j)
        aire +=profile_current.areaProperties().area
    sketch.deleteMe()
    planecurrent.deleteMe() 
    return (aire,pos_x)