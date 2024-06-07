import yaml as config_loader
from base import Config
import json


class Base(Config):
    def __init__(
        self, needs_folder_to_write=False, reload_config=False, default_name=True
    ):
        Config.__init__(self, reload_config, default_name)

        if default_name == True:
            self.class_name = self.__class__.__name__
            self.log.debug(f"Keeping default name as {self.class_name}")
        else:
            self.class_name = default_name

        self.needs_folder = needs_folder_to_write

        # Defined the widget type to update when finalised with the job
        try:
            self.widget2update = self.config["modules"][self.class_name][
                "widget2update"
            ]
        except:
            self.log.warning(
                f"Failed to obtained widget2update for {self.class_name} with error {e}. Setting it to UNK"
            )
            self.widget2update = "UNK"
        try:
            self.criteria2expire = self.config["modules"][self.class_name][
                "criteria2expire"
            ]
        except Exception as e:
            self.log.warning(
                f"Failed to get criteria2expire for {self.class_name} with error {e}. Going to set it to 0 seconds"
            )
            self.criteria2expire = [0, "second"]

    def load_config(self, file):
        # Load config. TODO: not totally abstracted from yaml as we need to tell the yaml.loader. If changed to pickle,json code needs changing here
        return config_loader.load(open(file, "r"), Loader=config_loader.FullLoader)

    def before(self):
        if self.needs_folder:
            result = self.check_folder_is_setup()
            if not result:
                # if check_folder_is_setup is False (failed) then throw failure and stop here
                return False

        if self.get("module_running"):
            self.log.warning("Cannot start a job because another already running")
            return False
        else:
            return True

    def check_folder_is_setup(self):
        try:
            directories = self.get("directories")
        except:
            directories = {}
            self.set("directories", directories)
            self.log.warning(f"Directories have not been stored in redis")
            self.log.warning(
                f"Can't run {self.class_name} task because folders have not been setup first"
            )
            return False

        if directories.get(self.class_name):
            self.log.debug(f"Ok. We have setup a folder for {self.class_name}")
            return True
        else:
            self.log.warning(f"Needs folder setup. Run Create directories first")
            return False

    def run(self):
        """
        Basic run method that is called by clicking the respective module button.
        This method calls a GUI if the method exists. Create a launch_GUI method on the inherited respective module class if you wish this.
        """
        if self.before():
            self.set_running()
            try:
                self.log.debug(
                    f"Trying to trigger run method on {self.class_name} module class"
                )

                # Launch module new window if any. Won't work if module class has not overwritten the launch_GUI function
                self.launch_GUI()
                self.log.debug("GUI launched")

            except Exception as e:
                self.log.critical(f"Failed with error {e}")
            finally:
                self.set_stopped()
                return True
        else:
            return False

    def set_running(self):
        self.set("module_running", True)
        self.set(f"{self.class_name}_running", True)

    def set_stopped(self):
        self.set("module_running", False)
        self.set(f"{self.class_name}_running", False)

    def set_status(self, status=True):
        """
        Updated the check box or date with succesfully delivered the result of the module
        """
        self.status = status
        self.log.debug(f"STATUS IS: {self.status}")
        self.set(f"{self.class_name}_status", status)

        if status == True:
            CB = 2
        elif status == False:
            CB = 0
        else:
            CB = 1
        # The update widget function is added to this module on the beamline_setup.py. It is not inherited.
        self.update_widget(task=self.class_name, status=CB, value="current")

        # print(f'STATUS IS: {self.status}')
        return status

    def set_status_true(self):
        return self.set_status(True)

    def set_status_false(self):
        return self.set_status(False)

    def launch_GUI(self):
        """
        This function needs to be overwritten to launch a new GUI for that particular module. If the module does not have a GUI this is just a place holder and will do nothing
        """
        pass
