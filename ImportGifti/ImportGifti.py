import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import numpy as np
import re
from pathlib import Path

#
# ImportGifti. Module to load gifti files into 3D Slicer.
#


class ImportGifti(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Import Gifti"
        self.parent.categories = ["Utilities"]
        self._dir_chosen = ""  # Saves path to vCast exe file
        self.parent.dependencies = []
        self.parent.contributors = ["Mauricio Cespedes (Western University)"]
        self.parent.helpText = """
        This tool is made to load surfaces (gifti) and volumetric (nifti) files into 3D Slicer.
        """
        self.parent.acknowledgementText = """
        This module was originally developed by Mauricio Cespedes Tenorio (Western University).
        """


#
# ImportGifti Widget
#


class ImportGiftiWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False
        # Parameters used to save states or useful information
        self._bool_subj = False
        self._dir_selected = False
        self.config = self.resourcePath("Config/config.yml")
        self.checkboxes = [[], []]

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        self._loadUI()
        self.logic = ImportGiftiLogic()

        # Connections
        self._setupConnections()

    def _loadUI(self):
        """
        Load widget from .ui file (created by Qt Designer).
        """
        # Load from .ui file
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/ImportGifti.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        # UI boot configuration of 'Apply' button and the input box.
        self.ui.applyButton.toolTip = "Please select a path to Hippunfold results"
        self.ui.applyButton.enabled = False
        # TableWidget to display files
        header = self.ui.tableFiles.horizontalHeader()
        header.setDefaultSectionSize(80)
        header.setSectionResizeMode(0, qt.QHeaderView.Stretch)
        header.setSectionResizeMode(1, qt.QHeaderView.Fixed)
        header.setSectionResizeMode(2, qt.QHeaderView.Fixed)

        # Dropdown to select subject
        self.ui.subj.addItems(["Select subject"])

        # Set default state of config path
        self.ui.configFileSelector.setCurrentPath(self.config)

        # Set default input and output path to home if not selected
        self.ui.InputDirSelector.filters = ctk.ctkPathLineEdit.Dirs
        self.ui.OutputDirSelector.filters = ctk.ctkPathLineEdit.Dirs
        home_directory = os.path.expanduser("~")
        if len(self.ui.InputDirSelector.currentPath) == 0:
            try:
                import yaml

                # Read yaml file to try to set it to
                with open(self.config) as file:
                    inputs_dict = yaml.load(file, Loader=yaml.FullLoader)
                if inputs_dict["bids_dir"]:
                    self.ui.InputDirSelector.setCurrentPath(inputs_dict["bids_dir"])
                else:
                    self.ui.InputDirSelector.setCurrentPath(home_directory)
            except:
                self.ui.InputDirSelector.setCurrentPath(home_directory)
        if len(self.ui.OutputDirSelector.currentPath) == 0:
            self.ui.OutputDirSelector.setCurrentPath(home_directory)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

    def _setupConnections(self):
        # Connections
        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose
        )
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose
        )

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.searchButton.connect("clicked(bool)", self.onDirectoryChange)
        self.ui.subj.connect("currentIndexChanged(int)", self.onSubjChange)
        self.ui.configFileSelector.connect(
            "currentPathChanged(QString)", self.onConfigChange
        )
        self.ui.VisibleAll.connect("clicked(bool)", self.onVisibleAllChange)
        self.ui.ConvertAll.connect("clicked(bool)", self.onConvertAllChange)
        # Buttons
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """
        # Unobserve previously selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(
                self._parameterNode,
                vtk.vtkCommand.ModifiedEvent,
                self.updateGUIFromParameterNode,
            )
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(
                self._parameterNode,
                vtk.vtkCommand.ModifiedEvent,
                self.updateGUIFromParameterNode,
            )

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def onSubjChange(self):
        """
        This method is called whenever subject dropdown object is changed.
        The module GUI is updated to show the current state of the parameter node.
        """
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        # Clean the list of files
        self.checkboxes = [[], []]
        # Set state of button only if a subj is selected
        if self.ui.subj.currentIndex > 0:
            # Save the state (subject is selected)
            self._bool_subj = True
            # Load the information if
            if self._dir_selected:
                # Clear the table
                while self.ui.tableFiles.rowCount > 0:
                    self.ui.tableFiles.removeRow(0)
                # Load the files
                for file, _ in self.files[self.ui.subj.currentText]:
                    rowPosition = self.ui.tableFiles.rowCount
                    self.ui.tableFiles.insertRow(rowPosition)
                    # Use file path without selected parent folder
                    filename = re.sub(
                        str(self.ui.InputDirSelector.currentPath), ".", file
                    )
                    self.ui.tableFiles.setItem(
                        rowPosition, 0, qt.QTableWidgetItem(filename)
                    )
                    # Add the two checkboxes
                    for i in range(1, 3):
                        # Construct checkbox and add to table
                        cell_widget = qt.QWidget()
                        chk_bx = qt.QCheckBox()
                        chk_bx.setCheckState(qt.Qt.Checked)
                        lay_out = qt.QHBoxLayout(cell_widget)
                        lay_out.addWidget(chk_bx)
                        lay_out.setAlignment(qt.Qt.AlignCenter)
                        lay_out.setContentsMargins(0, 0, 0, 0)
                        cell_widget.setLayout(lay_out)
                        self.ui.tableFiles.setCellWidget(rowPosition, i, cell_widget)
                        # Add checkbox object to list
                        self.checkboxes[i - 1].append(chk_bx)
                # Update state of check all boxes
                self.ui.VisibleAll.setText("Uncheck all")
                self.ui.ConvertAll.setText("Uncheck all")
                # Connect files checkboxes to function
                for chk_bx_conv in self.checkboxes[0]:
                    chk_bx_conv.stateChanged.connect(self.chkBoxConvertChange)
                for chk_box_vis in self.checkboxes[1]:
                    chk_box_vis.stateChanged.connect(self.chkBoxVisibleChange)
                # Enable button
                self.ui.applyButton.toolTip = "Run algorithm"
                self.ui.applyButton.enabled = True
        else:  # The button must be disabled if the condition is not met
            self.ui.applyButton.toolTip = "Select the required inputs"
            self.ui.applyButton.enabled = False
            self._bool_subj = False
            # Clear the table
            while self.ui.tableFiles.rowCount > 0:
                self.ui.tableFiles.removeRow(0)

    def onConfigChange(self):
        """
        Function to update the list of inputs depending on the configuration file.
        """
        # Load required packages, if not found, they are installed
        try:
            from bids import BIDSLayout
            import yaml
            from os.path import dirname, abspath
        except:
            if slicer.util.confirmOkCancelDisplay(
                "This module requires the Python packages 'pybids', and 'pyyaml'. \
                                                  Click OK to install it now."
            ):
                # Create progress bar to report installation
                progressbar = slicer.util.createProgressDialog(
                    parent=slicer.util.mainWindow(),
                    windowTitle="Downloading packages...",
                    value=0,
                    maximum=100,
                )
                ImportGiftiLogic().setupPythonRequirements_basic(progressbar)
                from bids import BIDSLayout
                import yaml
                from os.path import dirname, abspath
        if (
            os.path.isfile(str(self.ui.configFileSelector.currentPath))
            and self._dir_selected
        ):
            with slicer.util.tryWithErrorDisplay(
                "Failed to read config file properly. \
                                                 Make sure to follow the instructions in the package documentation.",
                waitCursor=True,
            ):
                # Get current dir
                current_dir = dirname(abspath(__file__))
                self.config = str(self.ui.configFileSelector.currentPath)
                # Read yaml file
                with open(self.config) as file:
                    inputs_dict = yaml.load(file, Loader=yaml.FullLoader)
                data_path = str(self.ui.InputDirSelector.currentPath)
                layout = BIDSLayout(
                    data_path,
                    config=self.resourcePath("Data/bids.json"),
                    validate=False,
                )
                self.files = {}
                for subj in self.list_subj:
                    self.files[subj] = []
                    for type_file in inputs_dict["pybids_inputs"]:
                        input_filters = {"subject": subj}
                        # Get pybids input filter based on the config file
                        dict_input = inputs_dict["pybids_inputs"][type_file]
                        # Update filter to add subject
                        input_filters.update(dict_input["pybids_filters"])
                        # Look for files based on BIDS
                        image_files = layout.get(**input_filters)
                        tmp_files = layout.get(**input_filters, return_type="filename")
                        # Check if there are scalars attached
                        # Case 1: gifti with scalars
                        if "scalars" in dict_input:
                            tmp_files_color = []
                            for tmp_file, image_file in zip(tmp_files, image_files):
                                labels_color = []
                                for scalar in dict_input["scalars"]:
                                    input_filters = {"subject": subj}
                                    input_filters.update(
                                        dict_input["scalars"][scalar]["pybids_filters"]
                                    )
                                    # Get entities from surf file
                                    if (
                                        "match_entities"
                                        in dict_input["scalars"][scalar]
                                    ):
                                        for entity in dict_input["scalars"][scalar][
                                            "match_entities"
                                        ]:
                                            input_filters[
                                                entity
                                            ] = image_file.get_entities()[entity]
                                    # print(input_filters)
                                    color_filenames = layout.get(
                                        **input_filters, return_type="filename"
                                    )
                                    if "colortable" in dict_input["scalars"][scalar]:
                                        # Update colortable path if relative
                                        colortable_path = dict_input["scalars"][scalar][
                                            "colortable"
                                        ]
                                        if not os.path.isabs(colortable_path):
                                            colortable_path = os.path.join(
                                                current_dir, colortable_path
                                            )
                                        # Update file list
                                        labels_color += [
                                            (
                                                file,
                                                colortable_path,
                                            )
                                            for file in color_filenames
                                        ]
                                    else:
                                        labels_color += [
                                            (file, None) for file in color_filenames
                                        ]
                                tmp_files_color.append((tmp_file, labels_color))
                        # Case 2: Nifti with colortable
                        elif "colortable" in dict_input:
                            # Update colortable path if relative
                            colortable_path = dict_input["colortable"]
                            if not os.path.isabs(colortable_path):
                                colortable_path = os.path.join(
                                    current_dir, colortable_path
                                )
                            if "show_unknown" in dict_input:
                                tmp_files_color = [
                                    (
                                        tmp_file,
                                        (
                                            colortable_path,
                                            dict_input["show_unknown"],
                                        ),
                                    )
                                    for tmp_file in tmp_files
                                ]
                            else:  # default to false
                                tmp_files_color = [
                                    (tmp_file, (colortable_path, False))
                                    for tmp_file in tmp_files
                                ]
                        # Case 3: Gifti without scalars
                        else:
                            tmp_files_color = [(tmp_file, []) for tmp_file in tmp_files]
                        # Add to list of files
                        self.files[subj] += tmp_files_color

    def onVisibleAllChange(self):
        """
        Function to select all or select none files to show in the 3D view.
        """
        if self.ui.VisibleAll.text == "Check all":
            for chk_bx in self.checkboxes[1]:
                chk_bx.setCheckState(qt.Qt.Checked)
            # Change the text of the GUI
            self.ui.VisibleAll.setText("Uncheck all")
        elif self.ui.VisibleAll.text == "Uncheck all":
            for chk_bx in self.checkboxes[1]:
                chk_bx.setCheckState(qt.Qt.Unchecked)
            # Change the text of the GUI
            self.ui.VisibleAll.setText("Check all")
        # Update checkboxes
        if len(self.checkboxes[1]) > 0:
            self.chkBoxVisibleChange()

    def onConvertAllChange(self):
        """
        Function to select all or select none files to convert.
        """
        if self.ui.ConvertAll.text == "Check all":
            for chk_bx in self.checkboxes[0]:
                chk_bx.setCheckState(qt.Qt.Checked)
            # Change the text of the GUI
            self.ui.ConvertAll.setText("Uncheck all")
        elif self.ui.ConvertAll.text == "Uncheck all":
            for chk_bx in self.checkboxes[0]:
                chk_bx.setCheckState(qt.Qt.Unchecked)
            # Change the text of the GUI
            self.ui.ConvertAll.setText("Check all")
        if len(self.checkboxes[0]) > 0:
            self.chkBoxConvertChange()

    def onDirectoryChange(self):
        """
        Function to update the list of files based on the input directory chosen. Also defines the state of 'Apply' button.
        """
        # Load required packages, if not found, they are installed
        try:
            from bids import BIDSLayout
        except:
            if slicer.util.confirmOkCancelDisplay(
                "This module requires the Python package 'pybids'. \
                                                  Click OK to install it now."
            ):
                # Create progress bar to report installation
                progressbar = slicer.util.createProgressDialog(
                    parent=slicer.util.mainWindow(),
                    windowTitle="Downloading...",
                    value=0,
                    maximum=100,
                )
                ImportGiftiLogic().setupPythonRequirements_basic(progressbar)
                from bids import BIDSLayout
        _tmp_dir_input = str(self.ui.InputDirSelector.currentPath)

        # Bool to change button status
        # If the selected file is a valid one, the button is enabled.
        if os.path.exists(_tmp_dir_input):
            try:
                # Update dropdown
                data_path = _tmp_dir_input
                self.BIDSLayout = BIDSLayout(data_path, validate=False)
                self.list_subj = self.BIDSLayout.get(return_type="id", target="subject")
                self.ui.subj.clear()
                self.ui.subj.addItems(["Select subject"] + self.list_subj)
            except ValueError:
                self.ui.applyButton.toolTip = "Please select a valid directory"
                self.ui.applyButton.enabled = False
            # Set to true condition indicating that we have valid input directories
            self._dir_selected = True
            # Re-run config file
            self.onConfigChange()
            # Update button if both conditions are true
            if self._bool_subj:
                self.ui.applyButton.toolTip = "Run algorithm"
                self.ui.applyButton.enabled = True
            # Save the directory in the config file
            ImportGiftiLogic().replaceBIDSdir(self.config, _tmp_dir_input)
        # Else, it is disabled.
        else:
            self.ui.applyButton.toolTip = "Please select a valid directory"
            self.ui.applyButton.enabled = False
            self._dir_selected = False

    def chkBoxVisibleChange(self):
        """
        Function to manage checked items in the 'Visible' column.
        Updates the checkbox for each item as well as updating the 'All/None' checkbox.
        """
        # Look for amount of items checked
        item_checked = 0
        for chk_bx_conv, chk_box_vis in zip(self.checkboxes[0], self.checkboxes[1]):
            # Visible cannot be checked if convert is unchecked.
            if (
                chk_box_vis.checkState() == qt.Qt.Checked
                and chk_bx_conv.checkState() == qt.Qt.Unchecked
            ):
                chk_box_vis.setCheckState(qt.Qt.Unchecked)
            elif chk_box_vis.checkState() == qt.Qt.Checked:
                item_checked += 1
        # Update all/none state based on the amount of files checked.
        # If all are checked, the button should be to uncheck
        if item_checked == len(self.checkboxes[1]):
            self.ui.VisibleAll.setText("Uncheck all")
        else:
            self.ui.VisibleAll.setText("Check all")

    def chkBoxConvertChange(self):
        """
        Function to manage checked items in the 'Convert' column.
        Updates the checkbox for each item as well as updating the 'All/None' checkbox.
        """
        # Look for amount of items checked
        item_checked = 0
        for chk_bx in self.checkboxes[0]:
            if chk_bx.checkState() == qt.Qt.Checked:
                item_checked += 1
        # Update all/none state based on the amount of files checked.
        # If all are checked, the button should be to uncheck
        if item_checked == len(self.checkboxes[1]):
            self.ui.ConvertAll.setText("Uncheck all")
        else:
            self.ui.ConvertAll.setText("Check all")
        # Update visible boxes
        self.chkBoxVisibleChange()

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        wasModified = (
            self._parameterNode.StartModify()
        )  # Modify all properties in a single batch

        self._parameterNode.SetNodeReferenceID(
            "InputDir", self.ui.InputDirSelector.currentNodeID
        )
        self._parameterNode.SetNodeReferenceID(
            "OutputDir", self.ui.OutputDirSelector.currentNodeID
        )

        self._parameterNode.EndModify(wasModified)

    def onApplyButton(self):
        """
        Configures the behavior of 'Apply' button by connecting it to the logic function.
        """
        # Retrieve files to be converted
        files_convert = []
        for index, chk_bx in enumerate(self.checkboxes[0]):
            if chk_bx.checkState() == qt.Qt.Checked:
                files_convert.append(self.files[self.ui.subj.currentText][index])
        # Retrieve files to be visible
        files_visible = []
        for index, chk_bx in enumerate(self.checkboxes[1]):
            if chk_bx.checkState() == qt.Qt.Checked:
                files_visible.append(self.files[self.ui.subj.currentText][index][0])
        ImportGiftiLogic().convertToSlicer(
            str(self.ui.OutputDirSelector.currentPath), files_convert, files_visible
        )


#########################################################################################
####                                                                                 ####
#### ImportGiftiLogic                                                          ####
####                                                                                 ####
#########################################################################################
class ImportGiftiLogic(ScriptedLoadableModuleLogic):
    """ """

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        # Create a Progress Bar
        self.pb = qt.QProgressBar()

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("LUT"):
            parameterNode.SetParameter("LUT", "Select LUT file")

    def convertToSlicer(self, OutputPath, files_convert, files_visible):
        """
        Takes the files, convert them into an Slicer compatible format, saves them and loads them into 3D Slicer.
        """
        # Load required packages, if not found, they are installed
        try:
            import pandas as pd
            import nibabel as nb
            from nibabel.affines import apply_affine
            import nrrd
        except ModuleNotFoundError:
            if slicer.util.confirmOkCancelDisplay(
                "This module requires the Python packages 'nibabel', 'pynrrd' and 'pandas'. \
                                                  Click OK to install it now."
            ):
                # Create progress bar to report installation
                progressbar = slicer.util.createProgressDialog(
                    parent=slicer.util.mainWindow(),
                    windowTitle="Downloading...",
                    value=0,
                    maximum=100,
                )
                self.setupPythonRequirements_logic(progressbar)
                import pandas as pd
                import nibabel as nb
                from nibabel.affines import apply_affine
                import nrrd

        # Create dictionary to separate files based on their type (gifti vs nifti vs anything else)
        files_dict = {}
        for file, scalars in files_convert:
            filename = Path(file)
            ext = ""
            while filename.suffix:
                ext = filename.suffix + ext
                filename = filename.with_suffix("")
            if ext in files_dict:
                files_dict[ext].append((file, scalars))
            else:
                files_dict[ext] = [(file, scalars)]

        # Replace output path: If in the current work directory, Slicer sets OutputPath to './', which causes issues
        # in the dseg function.
        if OutputPath == ".":
            OutputPath = os.getcwd()

        # For each type of file, run the corresponding function
        for extension in files_dict:
            if extension == ".surf.gii":
                with slicer.util.tryWithErrorDisplay(
                    "Failed to convert surface file",
                    waitCursor=True,
                ):
                    self.convert_surf(files_dict[extension], OutputPath, files_visible)
            elif extension == ".nii.gz":
                with slicer.util.tryWithErrorDisplay(
                    "Failed to convert segmentation file",
                    waitCursor=True,
                ):
                    self.convert_dseg(files_dict[extension], OutputPath, files_visible)
            else:
                print(f"File type {extension} is not supported.")

    def convert_dseg(self, dseg_files, OutputPath, files_visible):
        """
        Converts nifti files to seg.nrrd and loads them into 3D Slicer.
        """
        import pandas as pd
        import nibabel as nb
        from pathlib import Path

        for dseg, (colortable, show_unknown) in dseg_files:
            # Read colortable
            atlas_labels = pd.read_table(colortable)
            atlas_labels["lut"] = atlas_labels[["r", "g", "b"]].to_numpy().tolist()
            # Find base file name to create output
            filename_with_extension = os.path.basename(dseg)
            base_filename = filename_with_extension.split(".", 1)[0]
            # Find parent dir
            path = Path(dseg)
            parent_dir = os.path.join(path.parents[1].name, path.parents[0].name)
            # Create sub and anat folder if it doesn't exist
            if not os.path.exists(os.path.join(OutputPath, parent_dir)):
                os.makedirs(os.path.join(OutputPath, parent_dir))
            seg_out_fname = os.path.join(
                OutputPath, parent_dir, f"{base_filename}.seg.nrrd"
            )
            # Load data from dseg file
            data_obj = nb.load(dseg)
            # Convert to nrrd
            self.write_nrrd(data_obj, seg_out_fname, atlas_labels, show_unknown)
            seg = slicer.util.loadSegmentation(seg_out_fname)
            if dseg in files_visible:
                seg.CreateClosedSurfaceRepresentation()

    def convert_surf(self, surf_files, OutputPath, files_visible):
        """
        Converts gifti files to vtk and loads them into 3D Slicer.
        """
        import pandas as pd
        import nibabel as nb
        from nibabel.affines import apply_affine

        for surf, label_files in surf_files:
            # Build the name of the output file
            # Find base file name to create output
            filename_with_extension = os.path.basename(surf)
            base_filename = filename_with_extension.split(".", 1)[0]
            # Find parent dir
            path = Path(surf)
            parent_dir = os.path.join(path.parents[1].name, path.parents[0].name)
            # Create surf folder if it doesn't exist
            if not os.path.exists(os.path.join(OutputPath, parent_dir)):
                os.makedirs(os.path.join(OutputPath, parent_dir))
            # Output file name
            outFilePath = os.path.join(OutputPath, parent_dir, f"{base_filename}.vtk")
            # Extract geometric data
            gii_data = nb.load(surf)
            vertices = gii_data.get_arrays_from_intent("NIFTI_INTENT_POINTSET")[0].data
            faces = gii_data.get_arrays_from_intent("NIFTI_INTENT_TRIANGLE")[0].data
            # Extract color data and add scalars
            arrayScalars = []
            labelsScalars = []
            active_scalar = None
            scalar_range = []
            if len(label_files) > 0:
                label_files_df = pd.DataFrame(label_files)
                # Iterate over the different files with scalars
                for index in label_files_df.index:
                    vert_colors_idx = nb.load(label_files_df.loc[index, 0]).agg_data()
                    name_label = (
                        os.path.basename(label_files_df.loc[index, 0])
                        .split(".", 1)[0]
                        .split("-")[-1]
                    )
                    # Case 1: Scalar + colortable
                    # Extract colors from df if a colortable was given
                    if label_files_df.loc[index, 1] != None:
                        df_colors = pd.read_table(
                            label_files_df.loc[index, 1], index_col="index"
                        )
                        # Create color table in Slicer
                        colorTableNode = slicer.mrmlScene.AddNewNodeByClass(
                            "vtkMRMLProceduralColorNode", "HippUnfoldColors"
                        )
                        colorTableNode.SetType(slicer.vtkMRMLColorTableNode.User)
                        colorTransferFunction = (
                            vtk.vtkDiscretizableColorTransferFunction()
                        )
                        for index_color in df_colors.index:
                            r = df_colors.loc[index_color, "r"] / 255.0
                            g = df_colors.loc[index_color, "g"] / 255.0
                            b = df_colors.loc[index_color, "b"] / 255.0
                            colorTransferFunction.AddRGBPoint(index_color, r, g, b)
                        colorTableNode.SetAndObserveColorTransferFunction(
                            colorTransferFunction
                        )
                        # Append scalars into the list of scalars
                        if len(arrayScalars) == 0:
                            arrayScalars = [
                                tuple([scalar]) for scalar in vert_colors_idx
                            ]
                        else:
                            for idx in range(len(vert_colors_idx)):
                                arrayScalars[idx] += tuple([vert_colors_idx[idx]])
                        # Append the name of the scalar into the list of names
                        labelsScalars.append(name_label)
                        # Set any scalar with colortable as the active scalar
                        active_scalar = name_label
                        # Extract the range of the active scalar
                        indexes = df_colors.index.values.tolist()
                        scalar_range = (indexes[0], indexes[-1])
                    # Case 2: Scalar without colotable.
                    else:
                        # Append scalars into the list of scalars
                        if len(arrayScalars) == 0:
                            arrayScalars = [
                                tuple([scalar]) for scalar in vert_colors_idx
                            ]
                        else:
                            for idx in range(len(vert_colors_idx)):
                                arrayScalars[idx] += tuple([vert_colors_idx[idx]])
                        # Append the name of the scalar into the list of names
                        labelsScalars.append(name_label)
                        # Set as active scalar only if there's no defined active scalar and this is the last scalar file
                        if (
                            active_scalar == None
                            and index == list(label_files_df.index)[-1]
                        ):
                            active_scalar = name_label
            # Create model
            surf_pv = self.makePolyData(vertices, faces, labelsScalars, arrayScalars)
            modelNode = slicer.modules.models.logic().AddModel(surf_pv)
            # Set name
            modelNode.SetName(base_filename)
            # Set active scalar
            # Case 1: scalar + colortable
            if len(scalar_range) > 0 and active_scalar != None:
                modelNode.GetDisplayNode().SetActiveScalar(
                    active_scalar, vtk.vtkAssignAttribute.POINT_DATA
                )
                modelNode.GetDisplayNode().SetAndObserveColorNodeID(
                    colorTableNode.GetID()
                )
                modelNode.GetDisplayNode().SetAutoScalarRange(False)
                modelNode.GetDisplayNode().SetScalarRange(
                    scalar_range[0], scalar_range[1]
                )
                modelNode.GetDisplayNode().SetScalarVisibility(True)
            elif active_scalar != None:
                modelNode.GetDisplayNode().SetActiveScalar(
                    active_scalar, vtk.vtkAssignAttribute.POINT_DATA
                )
                modelNode.GetDisplayNode().SetAutoScalarRange(True)
                modelNode.GetDisplayNode().SetScalarVisibility(True)
            # Set visibility
            if surf in files_visible:
                modelNode.SetDisplayVisibility(True)
            else:
                modelNode.SetDisplayVisibility(False)
            # Export model (needs to be recomputed as the vertices needs to be rotated)
            # Transform vertices
            LPS_to_RAS = np.array(
                [[-1, 0, 0, 0], [0, -1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
            )
            vertices = apply_affine(LPS_to_RAS, vertices)
            # Recompute surface and write
            surf_pv = self.makePolyData(vertices, faces, labelsScalars, arrayScalars)
            writer = vtk.vtkPolyDataWriter()
            writer.SetInputData(surf_pv)
            writer.SetFileName(outFilePath)
            writer.Write()

    # Functions to compute files
    def bounding_box(self, seg):
        """
        Defines bounding box around volumetric object
        """
        x = np.any(np.any(seg, axis=0), axis=1)
        y = np.any(np.any(seg, axis=1), axis=1)
        z = np.any(np.any(seg, axis=1), axis=0)
        ymin, ymax = np.where(y)[0][[0, -1]]
        xmin, xmax = np.where(x)[0][[0, -1]]
        zmin, zmax = np.where(z)[0][[0, -1]]
        bbox = np.array([ymin, ymax, xmin, xmax, zmin, zmax])
        return bbox

    def get_shape_origin(self, img_data):
        """
        Get shape of the volumetric data and defines the origin in one of its corners.
        """
        bbox = self.bounding_box(img_data)
        ymin, ymax, xmin, xmax, zmin, zmax = bbox
        shape = list(np.array([ymax - ymin, xmax - xmin, zmax - zmin]) + 1)
        origin = [ymin, xmin, zmin]
        return shape, origin

    def write_nrrd(self, data_obj, out_file, atlas_labels, show_unknown):
        """
        Writes nrrd file based on a nifti object.
        """
        import nibabel as nb
        import nrrd

        # Get data from the nifti
        data = data_obj.get_fdata()

        # Define some parameters for the nrrd
        keyvaluepairs = {}
        keyvaluepairs["dimension"] = 3
        keyvaluepairs["encoding"] = "gzip"
        keyvaluepairs["kinds"] = ["domain", "domain", "domain"]
        keyvaluepairs["space"] = "right-anterior-superior"
        keyvaluepairs["space directions"] = data_obj.affine[:3, :3].T
        keyvaluepairs["type"] = "double"

        # Get bounding box, shape and origin of the object.
        box = self.bounding_box(data)
        seg_cut = data[box[0] : box[1] + 1, box[2] : box[3] + 1, box[4] : box[5] + 1]
        shape, origin = self.get_shape_origin(data)
        origin = nb.affines.apply_affine(data_obj.affine, np.array([origin]))

        keyvaluepairs["sizes"] = np.array([*shape])
        keyvaluepairs["space origin"] = origin[0]
        i = 0  # Count segments
        # Set parameters for each different label in the nifti object
        for id in range(int(np.min(data)), int(np.max(data)) + 1):
            if id in atlas_labels["index"].tolist() or show_unknown:
                name = "Segment{}".format(i)
                # Define colors and name in an atlas was given
                if id in atlas_labels["index"].tolist():
                    col_lut = (
                        np.array(
                            atlas_labels[atlas_labels["index"] == id]["lut"].values[0]
                            + [255]
                        )
                        / 255
                    )
                    keyvaluepairs[name + "_Name"] = atlas_labels[
                        atlas_labels["index"] == id
                    ]["abbreviation"].values[0]
                    keyvaluepairs[name + "_Color"] = " ".join(
                        [f"{a:10.3f}" for a in col_lut]
                    )
                else:  # unknown region
                    col_lut = np.array([0, 0, 0, 0])
                    keyvaluepairs[name + "_Name"] = "Unknown"
                    keyvaluepairs[name + "_Color"] = " ".join(
                        [f"{a:10.3f}" for a in col_lut]
                    )
                keyvaluepairs[name + "_ColorAutoGenerated"] = "1"
                keyvaluepairs[
                    name + "_Extent"
                ] = f"0 {shape[0]-1} 0 {shape[1]-1} 0 {shape[2]-1}"
                keyvaluepairs[name + "_ID"] = "Segment_{}".format(id)
                keyvaluepairs[name + "_LabelValue"] = "{}".format(id)
                keyvaluepairs[name + "_Layer"] = "0"
                keyvaluepairs[name + "_NameAutoGenerated"] = 1
                keyvaluepairs[name + "_Tags"] = (
                    "TerminologyEntry:Segmentation category"
                    + " and type - 3D Slicer General Anatomy list~SRT^T-D0050^Tissue~SRT^"
                    + "T-D0050^Tissue~^^~Anatomic codes - DICOM master list~^^~^^|"
                )
                i += 1
        keyvaluepairs["Segmentation_ContainedRepresentationNames"] = "Binary labelmap|"
        keyvaluepairs["Segmentation_ConversionParameters"] = "placeholder"
        keyvaluepairs["Segmentation_MasterRepresentation"] = "Binary labelmap"

        nrrd.write(out_file, seg_cut, keyvaluepairs)

    # Function to create vtkPolyData object
    def makePolyData(self, verts, faces, labelsScalars, arrayScalars):
        """
        Create vtkPolyData based on vertices, faces and scalars. Recovered from:
        https://github.com/stephan1312/SlicerEAMapReader/blob/2798100fe2aebf482a83b347c1cef18135f2df87/EAMapReader-Slicer-4.11/lib/Slicer-4.11/qt-scripted-modules/EAMapReader.py#L218-L290
        https://programtalk.com/python-examples/vtk.vtkPolyData/
        """
        # Build structure
        mesh = vtk.vtkPolyData()
        pts = vtk.vtkPoints()
        for pt in verts:
            pts.InsertNextPoint(pt[0], pt[1], pt[2])
        cells = vtk.vtkCellArray()
        for f in faces:
            cells.InsertNextCell(len(f))
            for v in f:
                cells.InsertCellPoint(v)
        mesh.SetPoints(pts)
        mesh.SetPolys(cells)

        # Add scalars
        scalars = []
        for j in range(len(labelsScalars)):
            scalars.append(vtk.vtkFloatArray())
            scalars[j].SetNumberOfComponents(1)
            scalars[j].SetNumberOfTuples(len(arrayScalars))
            for i in range(len(arrayScalars)):
                scalars[j].SetTuple1(i, arrayScalars[i][j])
            scalars[j].SetName(labelsScalars[j])
            mesh.GetPointData().AddArray(scalars[j])

        return mesh

    def setupPythonRequirements_basic(self, progressDialog):
        """
        Installs packages required for the computation before the logic (to find files based on BIDS).
        """
        # Packages that need to be installed
        progressDialog.labelText = "Installing pybids"
        slicer.util.pip_install("pybids")
        progressDialog.setValue(50)
        progressDialog.labelText = "Installing pyyaml"
        slicer.util.pip_install("pyyaml")
        progressDialog.setValue(100)
        progressDialog.close()

    def setupPythonRequirements_logic(self, progressDialog):
        """
        Installs packages required to process the files.
        """
        # Packages that need to be installed
        progressDialog.labelText = "Installing nibabel"
        slicer.util.pip_install("nibabel")
        progressDialog.setValue(33.33)
        progressDialog.labelText = "Installing pynrrd"
        slicer.util.pip_install("pynrrd")
        progressDialog.setValue(66.67)
        progressDialog.labelText = "Installing pandas"
        slicer.util.pip_install("pandas")
        progressDialog.setValue(100)
        progressDialog.close()

    def replaceBIDSdir(self, yaml_file_path, new_bids_dir):
        # Read the content of the YAML file
        with open(yaml_file_path, "r") as yaml_file:
            yaml_content = yaml_file.read()

        # Define a regular expression pattern to match the 'bids_dir' line
        pattern = r"\b(bids_dir\s*:\s*).*"

        # Use the re.sub function to replace the 'bids_dir' value
        yaml_content = re.sub(pattern, rf"\1{new_bids_dir}", yaml_content)

        # Write the updated content back to the file
        with open(yaml_file_path, "w") as yaml_file:
            yaml_file.write(yaml_content)


class ImportGiftiTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    All the files come from running HippUnfold over the Sample Data "MRHead". Refer to the
    HippUnfold documentation for more information (https://hippunfold.readthedocs.io/en/latest/index.html).
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear(0)
        # Install required packages if not installed
        try:
            from bids import BIDSLayout
        except:
            if slicer.util.confirmOkCancelDisplay(
                "This module requires the Python package 'pybids'. \
                                                  Click OK to install it now."
            ):
                # Create progress bar to report installation
                progressbar = slicer.util.createProgressDialog(
                    parent=slicer.util.mainWindow(),
                    windowTitle="Downloading...",
                    value=0,
                    maximum=100,
                )
                ImportGiftiLogic().setupPythonRequirements_basic(progressbar)

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        # Test load only dseg file
        self.test_ImportGifti_dseg()
        self.setUp()
        # Test load only surf files (with and without scalar)
        self.test_ImportGifti_surf()
        self.setUp()
        # Test load multiple files (dseg + surf + invalid)
        self.test_ImportGifti_multiple()

    def test_ImportGifti_dseg(self):
        """
        Tests loading and converting two dseg files with colortable
        """
        import tempfile
        from bids import BIDSLayout
        from os.path import dirname, abspath
        import SampleData

        # Load MRHead Sample Data
        sampleDataLogic = SampleData.SampleDataLogic()
        sampleDataLogic.downloadSample("MRHead")
        # Output dir
        out_dir = tempfile.gettempdir()
        # dseg, (colortable, show_unknown)
        # Build files_convert
        current_dir = dirname(abspath(__file__))
        input_filters = {
            "subject": "001",
            "extension": ".nii.gz",
            "suffix": "dseg",
            "datatype": "anat",
        }
        current_dir = dirname(abspath(__file__))
        layout = BIDSLayout(
            os.path.join(current_dir, "Resources/Data/Test"),
            config=os.path.join(current_dir, "Resources/Data/bids.json"),
            validate=False,
        )
        # Look for files based on BIDS
        tmp_files = layout.get(**input_filters, return_type="filename")
        unknown = True
        files_convert = []
        for tmp_file in tmp_files:
            files_convert.append(
                (
                    tmp_file,
                    (
                        os.path.join(
                            current_dir,
                            "Resources/Data/desc-subfields_atlas-bigbrain_dseg.tsv",
                        ),
                        unknown,
                    ),
                )
            )
            unknown = False
        # Ony set to visible the second file
        files_visible = [tmp_files[-1]]
        ImportGiftiLogic().convertToSlicer(str(out_dir), files_convert, files_visible)

        self.delayDisplay("dseg test passed!")

    def test_ImportGifti_surf(self):
        """
        Tests loading two surfaces files (gifti). One file with scalars and the other without them.
        """
        from bids import BIDSLayout
        import tempfile
        from os.path import dirname, abspath
        import SampleData

        # Load MRHead Sample Data
        sampleDataLogic = SampleData.SampleDataLogic()
        sampleDataLogic.downloadSample("MRHead")
        # Output dir
        out_dir = tempfile.gettempdir()
        # (tmp_file, labels_color)
        # labels_color = [(file, dict_input['scalars'][scalar]['colortable']) for file in color_filenames]
        current_dir = dirname(abspath(__file__))
        # Input dictionary
        input_filters = {
            "subject": "001",
            "extension": ".surf.gii",
            "space": "T1w",
            "suffix": ["inner", "midthickness", "outer"],
        }
        current_dir = dirname(abspath(__file__))
        layout = BIDSLayout(
            os.path.join(current_dir, "Resources/Data/Test"),
            config=os.path.join(current_dir, "Resources/Data/bids.json"),
            validate=False,
        )
        # Look for files based on BIDS
        image_files = layout.get(**input_filters)
        tmp_files = layout.get(**input_filters, return_type="filename")
        # Config of scalar files
        extensions = [
            (
                ".label.gii",
                os.path.join(
                    current_dir, "Resources/Data/desc-subfields_atlas-bigbrain_dseg.tsv"
                ),
            ),
            (".shape.gii", None),
        ]
        match_entities = ["label", "hemi"]
        files_convert = []
        # Load one of the surf files with scalars
        labels_color = []
        for scalar_type, colortable in extensions:
            input_filters = {"subject": "001"}
            input_filters["extension"] = scalar_type
            for entity in match_entities:
                input_filters[entity] = image_files[0].get_entities()[entity]
            scalar_filenames = layout.get(**input_filters, return_type="filename")
            labels_color += [(file, colortable) for file in scalar_filenames]
        files_convert.append((tmp_files[0], labels_color))
        # Load the other file without the scalars
        files_convert.append((tmp_files[1], []))
        # Ony set to visible the first file
        files_visible = [tmp_files[0]]
        ImportGiftiLogic().convertToSlicer(str(out_dir), files_convert, files_visible)

        self.delayDisplay("surf test passed!")

    def test_ImportGifti_multiple(self):
        """
        Tests loading surfaces + volumetric + invalid files.
        """
        import tempfile
        from os.path import dirname, abspath
        from bids import BIDSLayout
        import SampleData

        # Load MRHead Sample Data
        sampleDataLogic = SampleData.SampleDataLogic()
        sampleDataLogic.downloadSample("MRHead")
        # Output dir
        out_dir = tempfile.gettempdir()
        # First compute dseg files
        # Build files_convert
        current_dir = dirname(abspath(__file__))
        input_filters = {
            "subject": "001",
            "extension": ".nii.gz",
            "suffix": "dseg",
            "datatype": "anat",
        }
        current_dir = dirname(abspath(__file__))
        layout = BIDSLayout(
            os.path.join(current_dir, "Resources/Data/Test"),
            config=os.path.join(current_dir, "Resources/Data/bids.json"),
            validate=False,
        )
        # Look for files based on BIDS
        tmp_files = layout.get(**input_filters, return_type="filename")
        unknown = False
        files_convert = []
        for tmp_file in tmp_files:
            files_convert.append(
                (
                    tmp_file,
                    (
                        os.path.join(
                            current_dir,
                            "Resources/Data/desc-subfields_atlas-bigbrain_dseg.tsv",
                        ),
                        unknown,
                    ),
                )
            )
        # Ony set to visible the second file
        files_visible = [tmp_files[-1]]

        # Now get surf files
        # Input dictionary
        input_filters = {
            "subject": "001",
            "extension": ".surf.gii",
            "space": "T1w",
            "suffix": ["inner", "midthickness", "outer"],
        }
        current_dir = dirname(abspath(__file__))
        # Look for files based on BIDS
        image_files = layout.get(**input_filters)
        tmp_files = layout.get(**input_filters, return_type="filename")
        # Config of scalar files
        extensions = [
            (
                ".label.gii",
                os.path.join(
                    current_dir, "Resources/Data/desc-subfields_atlas-bigbrain_dseg.tsv"
                ),
            ),
            (".shape.gii", None),
        ]
        match_entities = ["label", "hemi"]
        for tmp_file, image_file in zip(tmp_files, image_files):
            labels_color = []
            for scalar_type, colortable in extensions:
                input_filters = {"subject": "001"}
                input_filters["extension"] = scalar_type
                for entity in match_entities:
                    input_filters[entity] = image_file.get_entities()[entity]
                scalar_filenames = layout.get(**input_filters, return_type="filename")
                labels_color += [(file, colortable) for file in scalar_filenames]
            files_convert.append((tmp_file, labels_color))
        # Ony set to visible the second file
        files_visible.append(tmp_files[0])

        # Import invalid file
        input_filters = {
            "subject": "001",
            "extension": ".label.gii",
        }
        # Look for files based on BIDS
        tmp_files = layout.get(**input_filters, return_type="filename")
        unknown = True
        files_convert += [(tmp_file, []) for tmp_file in tmp_files]
        # Ony set to visible the second file
        files_visible.append(tmp_files[-1])
        ImportGiftiLogic().convertToSlicer(str(out_dir), files_convert, files_visible)

        self.delayDisplay("dseg+surf test passed!")
