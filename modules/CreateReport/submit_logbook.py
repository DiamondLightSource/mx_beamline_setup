import os
import json
import getpass
from jinja2 import Environment, FileSystemLoader
from .posters import ElogPoster

from datetime import datetime


class Submit_Logbook:
    """
    Class for preparation and submission of beamline setup logbook entries

    Preparation:
      - Jinja2 templates for each step that can be customised as required

    Logbooks:
      - DLS uses elog
      - SLS usees scilog
    """

    def __init__(self, module_config, original_class_name, log, data, username):
        self.config = module_config
        self.original_class = original_class_name
        self.log = log
        self.log.info(
            f"Config is {self.config.keys()} and class name is {self.original_class}"
        )
        self.payload_data = data
        self.beamline_scientist = getpass.getuser()
        self.beamline = "I04"
        self.fedid = username
        self.now = datetime.now()
        self.log.info(f"Logbook entry performed by {self.beamline_scientist}")
        self.logbook = ElogPoster(beamline=self.beamline, poster=self.fedid)
        self.data = self.data_parsing()

    def prepare_images(self, image_dictionary):
        """
        ELOG requires images to be pre-uploaded and the URL to be assigned for inclusion in posts.
        """
        image_links = self.logbook.upload_multiple_files(image_dictionary)
        return image_links

    def prepare_image(self, image_path):
        """
        ELOG requires images to be pre-uploaded and the URL to be assigned for inclusion in posts.
        """
        link = self.logbook.upload_file_get_link("image", image_path)
        return link

    def data_parsing(self):
        """
        Agreed API is that there will be a payload_data for each module and it will contain
        images filepaths and EPICS channel readbacks.
        """
        self.log.info(f"Redis payload keys are: {self.payload_data.keys()}")
        self.date = self.now.strftime("%Y%m%d")
        self.datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log.info(f"self.date is {self.date}")
        self.data = {
            "beamline": self.beamline,
            "date": self.date,
            "beamline_scientist": self.beamline_scientist,
            "image_width_px": 600,
            "modules": self.payload_data,
        }
        for module in self.data["modules"]:
            if "images" in self.data["modules"][module].keys():
                self.data["modules"][module]["image_url"] = self.prepare_image(
                    self.data["modules"][module]["images"][0]
            )
        return self.data

    def prepare_logbook_entry(
        self,
        templates_folder="modules/CreateReport/templates",
        template_file="beamline_logbook_template.jinja2",
    ):
        """
        Function that creates a Jinja2 environment from the specified
        templates directory and renders a logbook entry.
        """

        THIS_DIR = os.path.join(os.getcwd(), templates_folder)
        self.log.debug(f"Templates for beamline setup in {THIS_DIR}")

        j2_env = Environment(loader=FileSystemLoader(THIS_DIR), trim_blocks=True)

        return j2_env.get_template(template_file).render(data=self.data)

    def submit_logbook(self, title, content):
        """
        Submit prepared logbook entry to respective logbooks (elog, scilog, etc)
        """
        response = self.logbook.post(title, content)
        return response
