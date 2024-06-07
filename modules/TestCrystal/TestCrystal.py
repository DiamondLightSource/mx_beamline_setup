from base import MOD_Base

from PyQt5.QtWidgets import QFileDialog, QDialog, QWizard
from PyQt5 import QtCore

from .QualityControl import TestCrystalResults
from .ImageManipulation import TestCrystalPictures
from modules.TestCrystal.GUI_TestCrystal import GUI

from datetime import datetime
import pathlib


class TestCrystal(MOD_Base):
    def __init__(self, needs_folder_to_write=False):
        MOD_Base.__init__(self, needs_folder_to_write)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now()

    def launch_GUI(self):
        self.TestCrystal_WZ = QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        # TODO: implement display configuration and zoom in beamline library
        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.TestCrystal_WZ)

        # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.TestCrystal_WZ.button(QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.TestCrystal_WZ.button(QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.TestCrystal_WZ.button(QWizard.NextButton).clicked.connect(
            self.next
        )
        self.TestCrystal_WZ.button(QWizard.BackButton).clicked.connect(
            self.back
        )

        # Handle pressing the top right X button
        self.TestCrystal_WZ.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.TestCrystal_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.TestCrystal_WZ.show()


    def next(self):
        self.log.debug(
            f"Next button pressed. Going to drive the goniometer on a different thread"
        )
        self.drive()

    def back(self):
        self.log.debug(
            "Back button pressed, maybe you want to collect rotation axis data again?"
        )

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def drive(self):
        """ Select masterfile to then harvest test crystal statistics """
        try:
            self.module_folder = self.get("directories")["TestCrystal"]
        except Exception as e:
            self.log.error(
                f"Please create the directories first. Can't run test crystal without a folder to store the QC"
            )
            return False

        try:
            self.montage_file = str(
                pathlib.PurePath(self.module_folder, "crystalNdiff_images.png")
            )  # need to define this earlier because it is used by get_visit_folder to guess open file folder to start

            self.ROOT_DIR = self.get_visit_folder()
            self.log.debug(f"Folder to find master files will start at {self.ROOT_DIR}")

            # folder = str(QFileDialog.getExistingDirectory(self, "Select Directory"))
            self.log.debug(f"Using {self.ROOT_DIR} as starting point for GUI opening")
            self.masterfile = self.FileDialog(
                directory=self.ROOT_DIR, forOpen=True, fmt="_master.h5", isFolder=False
            )
            self.log.info(f"Got masterfile {self.masterfile}")

            self.log.debug(f"Going to extract processing results")
            extraction_status, payload = self.extract_processing_data(self.masterfile)
            self.log.debug(f"Going to make picture montage")
            montage_status = self.make_image_montage(self.masterfile)

            if montage_status:
                self.log.debug(f"Got a montage file, storing path into payload")
                payload["images"] = [self.montage_file]

            key = f'{self.class_name}_report_{self.now.strftime("%Y%m%d")}'
            self.log.debug(f"Preparing to store {payload} in redis hash key {key}")
            self.set(key, payload)

            if extraction_status and montage_status:
                self.log.info(
                    f"Both processing results extaction and picture montage were sucessfull. Happy days!"
                )
                self.set_status_true()
        except Exception as e:
            self.log.critical(f"Failed with error {e}")
            self.set_status_false()

    def get_visit_folder(self):
        list_path = self.montage_file.split("/")
        list_path.remove("beamline_setup")
        list_path.remove("TestCrystal")
        list_path = list_path[0:-1]
        probable_master_file_path = "/".join(list_path)
        path_dir = pathlib.Path(probable_master_file_path)
        if path_dir.is_dir():
            return probable_master_file_path
        else:
            self.log.debug(
                f"The folder for today does not exist on this visit. Going to provide the parent folder"
            )
            return str(path_dir.parent)

    def extract_processing_data(
        self,
        masterfile="/dls/i04/data/2024/cm37236-1/20240313/TestProteinaseK/ProtK_13/ProtK_13_3_master.h5",
    ):
        """
        Given a masterfile extract processing statistics from the corresponding autoprocessing runNumber
        """

        self.log.debug("before masterfile")
        # masterfile below for testing purposes - to  be replaced by popup and staff selecting directory
        qc = TestCrystalResults(masterfile)
        self.log.debug("After test instantiation")
        payload = qc.get_results()

        # Here some code just assess if this task ran successfully and set status to True/False
        status = True
        if status == False:
            self.set(f"{self.class_name}_status", status)
        return [status, payload]

    def make_image_montage(self, masterfile):
        self.log.debug(f"Will write montage file to {self.montage_file}")
        im = TestCrystalPictures(self.log)
        files2process = im.get_images(masterfile)
        im.create_l_montage(
            files2process["xtal_pictures"],
            files2process["diff_image"],
            self.montage_file,
        )
        if pathlib.Path(self.montage_file).is_file():
            status = True
        else:
            status = False
        return status

    def FileDialog(self, directory="", forOpen=True, fmt="", isFolder=False):
        # Taken from https://stackoverflow.com/questions/38746002/pyqt-qfiledialog-directly-browse-to-a-folder?rq=1
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        options |= QFileDialog.DontUseCustomDirectoryIcons
        dialog = QFileDialog()
        dialog.setOptions(options)

        dialog.setFilter(dialog.filter() | QtCore.QDir.Hidden)

        # ARE WE TALKING ABOUT FILES OR FOLDERS
        if isFolder:
            dialog.setFileMode(QFileDialog.DirectoryOnly)
        else:
            dialog.setFileMode(QFileDialog.AnyFile)
        # OPENING OR SAVING
        dialog.setAcceptMode(
            QFileDialog.AcceptOpen
        ) if forOpen else dialog.setAcceptMode(QFileDialog.AcceptSave)

        # SET FORMAT, IF SPECIFIED
        if fmt != "" and isFolder is False:
            dialog.setDefaultSuffix(".h5")
            dialog.setNameFilters([f"{fmt} (*{fmt})"])

        # SET THE STARTING DIRECTORY
        if directory != "":
            dialog.setDirectory(str(directory))
        else:
            dialog.setDirectory(str(self.ROOT_DIR))

        if dialog.exec_() == QDialog.Accepted:
            self.log.debug(f"got {dialog.selectedFiles()[0]} from selector")
            path = dialog.selectedFiles()[0]  # returns a list
            return path
        else:
            return ""
