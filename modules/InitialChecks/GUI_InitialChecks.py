from UIs_py.initial_checks import Ui_RemoteAccess_WZ as IC_UI_GUI
from PyQt5 import QtCore, QtGui, QtWidgets
import yaml as config_loader


class GUI(IC_UI_GUI):

    def read_config(self):
        #To remove the hardcoded path below
        #file = '/dls/science/groups/i04/Python/applications/beamline_setup/modules/InitialChecks/InitialChecks.yaml'
        # Relative path to modules folder
        file = "./modules/InitialChecks/InitialChecks.yaml"
        self.config = {}
        self.config = config_loader.load(open(file,'r'),Loader=config_loader.FullLoader)
        

    def retranslateUi(self, RemoteAccess_WZ):
        _translate = QtCore.QCoreApplication.translate
        RemoteAccess_WZ.setWindowTitle(_translate("RemoteAccess_WZ", "Wizard"))
        self.WP1_Label_1.setText(_translate(self.config['WP1_Label_1_Title'],self.config['WP1_Label_1_Text']))
        self.WP2_Label_1.setText(_translate(self.config['WP2_Label_1_Title'],self.config['WP2_Label_1_Text']))



if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    RemoteAccess_WZ = QtWidgets.QWizard()
    ui = RA_GUI()
    ui.read_config()
    ui.setupUi(RemoteAccess_WZ)
    RemoteAccess_WZ.show()
    #sys.exit(app.exec_())
