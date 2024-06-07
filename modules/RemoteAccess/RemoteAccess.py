from base import MOD_Base
from .RA_ssh import Manage_NX_Connections
import getpass

from datetime import datetime
from PyQt5.QtWidgets import QWizard
from PyQt5 import QtCore

from modules.RemoteAccess.GUI_RemoteAccess import GUI


class RemoteAccess(MOD_Base):
    def __init__(self,needs_folder_to_write=False):
        MOD_Base.__init__(self,needs_folder_to_write)
        self.log.info(f'Loading {self.class_name}_MD module/instance')
        self.now = datetime.now()

    def launch_GUI(self):
            self.RemoteAccess_WZ = QWizard()
            self.ui = GUI()
            self.log.debug(f"Created ui instance for new window for {self.class_name}")
            self.ui.read_config()

            # TODO: implement display configuration and zoom in beamline library
            self.ui.config["display_configuration"] = self.ui.config[
                "display_configuration"
            ].format(BEAMLINE=self.ID)

            self.ui.setupUi(self.RemoteAccess_WZ)

            # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
            self.RemoteAccess_WZ.button(QWizard.FinishButton).clicked.connect(
                self.set_status_true
            )
            self.RemoteAccess_WZ.button(QWizard.CancelButton).clicked.connect(
                self.set_status_false
            )
            self.RemoteAccess_WZ.button(QWizard.NextButton).clicked.connect(
                self.next
            )

            self.RemoteAccess_WZ.button(QWizard.BackButton).clicked.connect(
                self.back
            )

            self.RemoteAccess_WZ.button(QWizard.FinishButton).clicked.connect(
                self.finish
            )

            # Handle pressing the top right X button
            self.RemoteAccess_WZ.rejected.connect(self.reject)

            # Lock main window to prevent other tasks
            self.RemoteAccess_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
            self.RemoteAccess_WZ.show()


    def next(self):
        self.log.debug(
            f"Next button pressed. Collecting user information then going to next window."
        )
        return self.drive()

    def finish(self):
        self.log.debug(
            f"Finish button pressed. Module ended"
        )


    def back(self):
        self.log.debug(
            "Back button pressed, maybe you want to collect rotation axis data again?"
        )

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def drive(self):
        try:
            if self.before():
                fedid = self.username
                pw = self.password
                nx_machines = self.nx_machines
                self.log.info("before set_running() in RemoteAccess")
                self.set_running()
                self.log.debug(f'Trying to trigger collect remote No machine users on {self.class_name} module class')
                nx_manager = Manage_NX_Connections(fedid, nx_machines, pw)
                self.log.debug(f'setting up nx_manager {nx_manager}')
                self.connections = nx_manager.get_list_of_sessions()
                self.log.info(f"current NX connections: {self.connections}")

                # redis data
                payload = {'nx_connections': self.connections}
                key = f"{self.class_name}_report_{self.now.strftime('%Y%m%d')}"
                self.set(key, payload)
                self.log.info(f"Storing data for report under redis hash key {key}")
                self.set_stopped()
            else:
                return False
            self.set_status_true()
            #Here some code just assess if this task ran successfully and set status to True/False
            status = True
            if status == False:
                self.set(f'{self.class_name}_status',status)
            return self.connections
        except Exception as e:
            self.log.critical(f"Failed with error {e}")
            self.set_status_false()
