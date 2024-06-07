from base import MOD_Base

from .submit_logbook import Submit_Logbook

from datetime import datetime
from PyQt5.QtWidgets import QWizard
from PyQt5 import QtCore

from modules.CreateReport.GUI_CreateReport import GUI

class CreateReport(MOD_Base):
    def __init__(self, needs_folder_to_write=False):
        MOD_Base.__init__(self, needs_folder_to_write)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now()

    def launch_GUI(self):
        self.CreateReport_WZ = QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        # TODO: implement display configuration and zoom in beamline library
        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.CreateReport_WZ)

        # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.CreateReport_WZ.button(QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.CreateReport_WZ.button(QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.CreateReport_WZ.button(QWizard.NextButton).clicked.connect(
            self.next
        )
        self.CreateReport_WZ.button(QWizard.BackButton).clicked.connect(
            self.back
        )

        # Handle pressing the top right X button
        self.CreateReport_WZ.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.CreateReport_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.CreateReport_WZ.show()


    def next(self):
        self.log.debug(
            f"Next button pressed."
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
        try:
            if self.before():
                self.set_running()
                self.log.debug(
                    f"Trying to trigger run method on {self.class_name} module class."
                )
                payload_modules = {}
                try:
                    all = self.get_all()
                    for item in all.keys():
                        if f'_report_{self.now.strftime("%Y%m%d")}' in item:
                            payload_modules[item] = all[item]
                except Exception as e:
                    self.log.critical(f"Failed to get reporting data with error {e}")
                self.log.info(f"payload_modules is: {payload_modules}")
                elog = Submit_Logbook(
                    module_config=self.config,
                    original_class_name=self.class_name,
                    log=self.log,
                    data=payload_modules,
                    username=self.username
                )

                content = elog.prepare_logbook_entry()
                response = elog.submit_logbook(
                    title=f'Beamline setup {self.now.strftime("%A %d/%m/%Y")}',
                    content=content,
                )
                self.set_stopped()
            else:
                return False
            # Here some code just assess if this task ran successfully and set status to True/False
            if response.status_code == 200:
                return self.set_status_true()
            else:
                return self.set_status_false()
        except Exception as e:
            self.log.critical(f"Failed with error {e}")
            self.set_status_false()

