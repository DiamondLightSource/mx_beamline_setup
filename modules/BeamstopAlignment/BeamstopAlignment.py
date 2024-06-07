from base import MOD_Base
from PyQt5 import QtCore, QtGui, QtWidgets
from modules.BeamstopAlignment.GUI_BeamstopAlignment import GUI
import time
from datetime import datetime

class BeamstopAlignment(MOD_Base):

    def __init__(self,needs_folder_to_write=False):
        MOD_Base.__init__(self,needs_folder_to_write)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now()

        #IMPORTANT: a run method defined on the upper class MOD_Base is triggered by clicking this module button on the GUI. One can overwrite the run function if requeried
        #The run method contains a call to launch_GUI function. If launch GUI does not exists a place holder pass function is called. 


    def launch_GUI(self):
        self.BeamstopAlignment_WZ = QtWidgets.QWizard()
        self.ui = GUI()
        self.log.debug(f'Created ui instance for new window for {self.class_name}')
        self.ui.read_config()

        # TODO: implement display configuration and zoom in beamline library
        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.BeamstopAlignment_WZ)

        
        #Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.BeamstopAlignment_WZ.button(QtWidgets.QWizard.FinishButton).clicked.connect(self.set_status_true)
        self.BeamstopAlignment_WZ.button(QtWidgets.QWizard.CancelButton).clicked.connect(self.set_status_false)
        self.BeamstopAlignment_WZ.button(QtWidgets.QWizard.NextButton).clicked.connect(self.next)
        self.BeamstopAlignment_WZ.button(QtWidgets.QWizard.BackButton).clicked.connect(self.back)
       

        #Handle pressing the top right X button
        self.BeamstopAlignment_WZ.rejected.connect(self.reject)
        
        #Lock main window to prevent other tasks
        self.BeamstopAlignment_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.BeamstopAlignment_WZ.show()

        #import code
        #code.interact(local=locals())
        

    def next(self):
        self.log.debug(f'Next button pressed')

    def back(self):
        self.log.debug('Back button pressed')

    def reject(self):
        self.log.debug('Kill X was clicked')
        self.set_status_false()
