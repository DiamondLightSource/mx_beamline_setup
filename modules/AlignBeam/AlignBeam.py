# Mod Base
from base import MOD_Base

# pyQT5
from PyQt5 import QtCore, QtGui, QtWidgets
from modules.AlignBeam.GUI_AlignBeam import GUI

# APP
import requests
import getpass
from beamline import cameras
from beamline import ID
import shutil
import epics

# PIL
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw

# Others
import functools
from datetime import datetime


class AlignBeam(MOD_Base):
    def __init__(self, needs_folder_to_write=False):
        MOD_Base.__init__(self, needs_folder_to_write)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now().strftime("%Y%m%d")

    def launch_GUI(self):
        self.AlignBeam_WZ = QtWidgets.QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        # TODO: implement display configuration and zoom in beamline library
        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.AlignBeam_WZ)

        # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.AlignBeam_WZ.button(QtWidgets.QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.AlignBeam_WZ.button(QtWidgets.QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.AlignBeam_WZ.button(QtWidgets.QWizard.NextButton).clicked.connect(
            self.next
        )
        self.AlignBeam_WZ.button(QtWidgets.QWizard.BackButton).clicked.connect(
            self.back
        )

        # Handle pressing the top right X button
        self.AlignBeam_WZ.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.AlignBeam_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.AlignBeam_WZ.show()

        # import code
        # code.interact(local=locals())

    def next(self):
        self.log.debug("Next button pressed. Going to collect optical alignment data")
        self.collect_qc_data()

    def back(self):
        self.log.debug(
            "Back button pressed, maybe you want to collect rotation axis data again?"
        )

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def collect_qc_data(self):
        """
        Collecting various optics alignment data
        """
        try:
            self.log.debug(
                f"Triggered collect_qc_data method on {self.class_name} module class"
            )

            alignbeam_qc = OpticsChecks(
                self.get, self.ui.config, self.class_name, self.log
            )

            # Collect optical alignment data
            payload = alignbeam_qc.collect_Ops_data()
            key = f"{self.class_name}_report_{self.now}"
            self.set(key, payload)
            self.log.info(f"Storing data for report under redis hash key {key}")

            # TODO: Implement drive to different zoom
            #      Get vertical coordinates for crosshairs (for current zoom)

        except Exception as e:
            self.log.critical(f"Failed with error {e}")


class OpticsChecks(object):
    def __init__(self, get_redis_method, module_config, original_class_name, log):
        self.url = f"http://{cameras.ROIs['xtal']['server']}{cameras.ROIs['xtal']['static'][0]}"
        self.username = username = getpass.getuser()
        self.get = get_redis_method
        self.config = module_config
        self.original_class = original_class_name
        self.log = log
        self.now = datetime.now().strftime("%Y%m%d")

        self.display_configuration_file = self.config["display_configuration"]
        self.zoom_pv = epics.PV(self.config["zoom_pv"])

        self.log.debug(f"{self.config['PVs']}")
        self.PV_instances = self.set_PVs()

    def collect_Ops_data(self):
        dict_data = {}
        dict_data["EPICS"] = self.get_PVs()
        self.log.info(
            f'List of human readable PVs available {dict_data["EPICS"].keys()}'
        )
        if self.checks():
            self.log.info(f"Passed checks")
            initial_zoom = self.zoom_pv.get()
            self.move_to_zoom(0)
            epics.poll(0.5)
            locations_and_zooms = self.collect_all_zoom_images()
            self.move_to_zoom(initial_zoom)
            from pprint import pformat

            # payload_text = pformat(str(dict_data["EPICS"]))
            payload_text = f"""
            {self.now}

            Flux: {dict_data['EPICS']['FLUX']} ph/s
            Transmission: {dict_data['EPICS']['TRANSMISSION']}
            Beamsize: {round(float(dict_data['EPICS']['BEAM_SIZE_X']),1)} um (H) x {round(float(dict_data['EPICS']['BEAM_SIZE_Y']),1)} um (V)
            Feedback on: {dict_data['EPICS']['Feedback_enable']}
            Machine Steer X: {dict_data['EPICS']['Machine_X_STEER']}
            Machine Steer Y: {dict_data['EPICS']['Machine_Y_STEER']}

            """
            locations_and_zooms.append(self.create_image_with_text(text=payload_text))
            path = self.make_montage(locations_and_zooms)

            # path, zoom = self.get_image_from_url(url=self.url,filename='beam_in_scintilator')

            path = self.store_beam_image_for_report(path)

        dict_data["images"] = [path]
        return dict_data

    def collect_single_picture(self, new_zoom):
        self.log.info(f"Moving to {new_zoom} zoom level")
        self.move_to_zoom(new_zoom)
        epics.poll(0.5)
        path, zoom = self.get_image_from_url(url=self.url, filename=new_zoom)
        self.log.info(f"Got image for zoom {new_zoom} with path {path}")
        return [path, zoom]

    def move_to_zoom(self, zoom):
        self.zoom_pv.put(zoom)
        epics.poll(0.2)

    def get_zoom_dict(self):
        # Needs location of configuration stored in self.display_configuration_file

        self.zoom_dict = {}
        with open(self.display_configuration_file) as display_configuration:
            for line in display_configuration:
                parsed_line = line.split("=")
                if parsed_line[0].strip() == "zoomLevel":
                    n = 0
                    current_zoom = parsed_line[1].strip()
                    self.zoom_dict[current_zoom] = {}
                self.zoom_dict[current_zoom][parsed_line[0].strip()] = parsed_line[
                    1
                ].strip()

        # Example of zoom_dict structure, values will be different
        # {'1.0': {'bottomRightX': '410',
        #         'bottomRightY': '278',
        #         'crosshairX': '589',
        #         'crosshairY': '359',
        #         'topLeftX': '383',
        #         'topLeftY': '253',
        #         'zoomLevel': '1.0'},
        # '1.5': {'bottomRightX': '410',
        #         'bottomRightY': '278',
        #         'crosshairX': '582',
        #         'crosshairY': '359',
        #         'topLeftX': '383',
        #         'topLeftY': '253',
        #     }

        return self.zoom_dict

    def checks(self):
        # check shutter opened
        # check scintilator up
        # check flux
        self.log.critical(
            f"FIXME - I am not checking for shutter opened, scintillator up and flux is okish!!"
        )
        return True

    def get_PVs(self):
        self.data = {}
        for PV_prefix, PV_dict in self.config["PVs"].items():
            for name, suffix in PV_dict.items():
                self.data[name] = getattr(self.PV_instances[PV_prefix], name)()
        self.log.info(f"Gather PV data without errors")
        return self.data

    def set_PVs(self):
        PV_instances = {}
        for prefix, pvs in self.config["PVs"].items():
            PV_instances[prefix] = BeamlineEpics(
                prefix=prefix, _init_list_=pvs.values(), nonpvs=list(pvs.keys())
            )
            lambdas = {}
            for name, suffix in pvs.items():
                self.log.debug(
                    f"Setting functool with pv {prefix} and suffix to query {suffix}"
                )
                # lambdas[suffix] = lambda: PV_instances[prefix].get(suffix)
                lambdas[suffix] = functools.partial(
                    PV_instances[prefix].get, suffix, as_string=True
                )
                self.log.info(
                    f"Setting new property {name} on PV to run lamba and get value of {lambdas[suffix]()}"
                )
                setattr(PV_instances[prefix], name, lambdas[suffix])
        return PV_instances

    def create_image_with_text(self, path="/var/tmp/", text=""):
        new_location = f"{path}{self.username}_Z.jpg"
        img = Image.new("RGB", (1024, 768), (255, 255, 255))
        font = ImageFont.truetype("arial.ttf", 24)
        ImageDraw.Draw(img).text((100, 100), text, (0, 0, 0), font=font)
        img.save(new_location, "JPEG")
        return [new_location, "AlignBeam"]

    def get_image_from_url(self, url, location="/var/tmp/", filename="image"):
        final_location = f"{location}{self.username}_{filename}.jpg"

        response = requests.get(url, stream=True)

        zoom = self.zoom_pv.get(as_string=True).strip("x")

        with open(final_location, "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)
        del response
        return final_location, zoom

    def collect_all_zoom_images(self):
        # TODO: Ask permission to drive goniometer
        # range8: 8 zoom levels from 1X,1.5X,2X,2.5X,3X,5X,7.5X,10X with PV starting at zero
        zooms = range(8)
        self.log.info(f"Going to collect {len(zooms)} images at different zoom levels")
        picture_locations_and_zooms = [
            self.collect_single_picture(zoom) for zoom in zooms
        ]
        return picture_locations_and_zooms

    def make_montage(self, locations_with_zooms):
        locations = [path[0] for path in locations_with_zooms]
        self.log.debug(f"Files to make montage are: {locations}")
        pill_image = self.make_contact_sheet(
            locations_with_zooms, 3, 3, 1024, 768, 1, 1, 1, 1, 1, draw_beam_cross=True
        )
        temp_save = f"/var/tmp/{self.username}_montage.png"
        pill_image.save(temp_save)
        self.log.info(f"Saved montage image to {temp_save}")
        pill_image.show()
        return temp_save

    def store_beam_image_for_report(self, montage_image):
        final_location = (
            f"{self.get('directories')[self.original_class]}/beam_at_sample.png"
        )
        try:
            shutil.copy2(montage_image, final_location)
            shutil.chown(final_location, group="mx_staff")
            self.log.info(f"Storing image {montage_image} to {final_location}")
            return final_location
        except Exception as e:
            self.log.critical(
                f"Could not copy image to {final_location} with error {e}"
            )

    def make_contact_sheet(
        self,
        locations_zoom,
        ncols,
        nrows,
        photow,
        photoh,
        marl,
        mart,
        marr,
        marb,
        padding,
        draw_horizontal_line=False,
        draw_beam_cross=False,
    ):
        """
        Make a contact sheet from a group of filenames:
    
        fnames       A list of names of the image files
        
        ncols        Number of columns in the contact sheet
        nrows        Number of rows in the contact sheet
        photow       The width of the photo thumbs in pixels
        photoh       The height of the photo thumbs in pixels
    
        marl         The left margin in pixels
        mart         The top margin in pixels
        marr         The right margin in pixels
        marb         The bottom margin in pixels
    
        padding      The padding between images in pixels
    
        returns a PIL image object.
        http://code.activestate.com/recipes/578267-use-pil-to-make-a-contact-sheet-montage-of-images/
        """

        fnames = [path[0] for path in locations_zoom]
        fzooms = [zoom[1] for zoom in locations_zoom]

        self.log.info(f"locations_zoom: {locations_zoom}")
        self.log.info(f"fnames: {fnames}")
        self.log.info(f"fzooms: {fzooms}")

        if draw_horizontal_line or draw_beam_cross:
            zoom_dict = self.get_zoom_dict()

        # Calculate the size of the output image, based on the
        #  photo thumb sizes, margins, and padding
        marw = marl + marr
        marh = mart + marb

        padw = (ncols - 1) * padding
        padh = (nrows - 1) * padding
        isize = (ncols * photow + marw + padw, nrows * photoh + marh + padh)

        # Create the new image. The background doesn't have to be white
        white = (255, 255, 255)
        self.log.debug("Creating empty white canvas")
        inew = Image.new("RGB", isize, white)

        count = 0
        # Insert each thumb:
        for irow in range(nrows):
            for icol in range(ncols):
                left = marl + icol * (photow + padding)
                right = left + photow
                upper = mart + irow * (photoh + padding)
                lower = upper + photoh
                bbox = (left, upper, right, lower)
                try:
                    name = fnames[count].split(".")[0].split("_")[1]
                    # Read in an image and resize appropriately
                    img = Image.open(fnames[count]).resize((photow, photoh))
                    # draw = ImageDraw.Draw(img)

                    if draw_horizontal_line == True:
                        self.log.debug(
                            "Ok, we have centre of rotation pictures going to draw an horizontal line"
                        )
                        # ImageDraw.Draw(img).line((512,0,512,photoh), fill=128,width=3) - vertical line not needed

                        # get crosshair for this zoom
                        # self.log.debug(zoom_dict)
                        self.log.debug(f"fzooms[count]: {fzooms[count]}")
                        Y_coordinate = int(zoom_dict[fzooms[count]]["crosshairY"])
                        self.log.debug(f"Got an Y coordinate of: {Y_coordinate}")
                        # Write horizontal line at Y height
                        ImageDraw.Draw(img).line(
                            (0, Y_coordinate, photow, Y_coordinate), fill=128, width=3
                        )
                        self.log.debug(
                            f"Line from 0,{Y_coordinate} to {photow},{Y_coordinate} drawn"
                        )

                    if draw_beam_cross == True and fzooms[count] != "AlignBeam":
                        self.log.info(
                            "Ok, we have beam in yag image. Going to draw a cross"
                        )
                        self.log.debug(f"fzooms[count]: {fzooms[count]}")
                        self.log.debug(f"fzooms[count]: {fzooms[count]}")
                        Y_coordinate = int(zoom_dict[fzooms[count]]["crosshairY"])
                        X_coordinate = int(zoom_dict[fzooms[count]]["crosshairX"])
                        size_of_line = (
                            15  # size in pixels for vertical and horizontal lines
                        )

                        # Draw horizontal line with size equal size_of_line
                        ImageDraw.Draw(img).line(
                            (
                                X_coordinate - size_of_line,
                                Y_coordinate,
                                X_coordinate + size_of_line,
                                Y_coordinate,
                            ),
                            fill=128,
                            width=3,
                        )

                        # Draw vertical line with size equal size_of_line
                        ImageDraw.Draw(img).line(
                            (
                                X_coordinate,
                                Y_coordinate - size_of_line,
                                X_coordinate,
                                Y_coordinate + size_of_line,
                            ),
                            fill=128,
                            width=3,
                        )

                    font = ImageFont.truetype("arial.ttf", 48)
                    ImageDraw.Draw(img).text(
                        (0, 0), fzooms[count], (255, 255, 255), font=font
                    )
                except Exception as e:
                    self.log.critical(
                        f"Failed to prepare montage with error {e} for image {count}"
                    )
                self.log.info("Pasting the images into the white canvas")
                inew.paste(img, bbox)
                count += 1
        self.log.debug("Finished making montage. Giving it back")
        return inew


class BeamlineEpics(epics.Device):
    def __init__(self, prefix=None, _init_list_=(), nonpvs=[]):
        nonpvs = nonpvs + list(epics.Device._nonpvs)
        epics.Device.__init__(
            self, prefix=prefix, delim=":", attrs=list(_init_list_), nonpvs=nonpvs
        )
