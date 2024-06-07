# Mod Base
from base import MOD_Base

# pyQT5
from PyQt5 import QtCore, QtGui, QtWidgets
from modules.RotationAxis.GUI_RotationAxis import GUI

# APP
import requests
import getpass
from beamline import motors
from beamline import cameras
from beamline import ID
import shutil
import epics

from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw

# Others
import functools
from datetime import datetime


class RotationAxis(MOD_Base):
    def __init__(self, needs_folder_to_write=False):
        MOD_Base.__init__(self, needs_folder_to_write)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.ID = ID
        self.now = datetime.now().strftime("%Y%m%d")

        # Method run() from upper class MOD_base/Modules.py is run when the GUI button is clicked. Run method calls launch GUI (Defined below)

    def launch_GUI(self):
        self.RotationAxis_WZ = QtWidgets.QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        # TODO: implement display configuration and zoom in beamline library
        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.RotationAxis_WZ)

        # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.RotationAxis_WZ.button(QtWidgets.QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.RotationAxis_WZ.button(QtWidgets.QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.RotationAxis_WZ.button(QtWidgets.QWizard.NextButton).clicked.connect(
            self.next
        )
        self.RotationAxis_WZ.button(QtWidgets.QWizard.BackButton).clicked.connect(
            self.back
        )

        # Handle pressing the top right X button
        self.RotationAxis_WZ.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.RotationAxis_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.RotationAxis_WZ.show()

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
        """
        Collecting rotation axis images
        """
        try:
            self.log.debug(
                f"Triggered drive goniometer method on {self.class_name} module class"
            )

            # Possibly implement a sub-GUI here later where the images can be shown and a "can I rotate goniometer question pops up"
            rotationaxis_qc = DriveBeamline(
                self.get, self.ui.config, self.class_name, self.log
            )

            # Rotate gonio and collect images
            payload = rotationaxis_qc.collect_CoR_data()
            # Store data in redis for ReportModule
            key = f"{self.class_name}_report_{self.now}"
            self.set(key, payload)
            self.log.info(f"Storing data for report under redis hash key {key}")

            # TODO: Implement drive to particular zoom
            #      Get vertical coordinate of crosshairs (for current zoom) and draw vertical line on image (maybe using PIL) at that coordinate

        except Exception as e:
            self.log.critical(f"Failed with error {e}")


class DriveBeamline(object):
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

    def get_PVs(self):
        self.data = {}
        for PV_prefix, PV_dict in self.config["PVs"].items():
            for name, suffix in PV_dict.items():
                if name == "Smargon_home":
                    self.data[name] = (
                        self.PV_instances[PV_prefix]
                        .get_PV_change_time("HOMESTATUS_MSG")
                        .strftime("%Y-%m-%d %H:%M")
                    )
                    self.log.info(f"Time since last home {self.data[name]}")
                else:
                    self.data[name] = getattr(self.PV_instances[PV_prefix], name)()
                    print(f"above getattr call name is: {name}, PV instances {self.PV_instances[PV_prefix]}")
                    self.log.debug(
                        f'looking at PV instance {PV_prefix} that has methods {dir(self.PV_instances[PV_prefix])}'
                    )
                    self.data[f"{name}_change_time"] = getattr(
                        self.PV_instances[PV_prefix], f"{name}"
                    )()
        self.log.info(f"Gather PV data without errors")
        return self.data

    def set_PVs(self):
        PV_instances = {}
        for prefix, pvs in self.config["PVs"].items():
            PV_instances[prefix] = BeamlineEpics(
                prefix=prefix, _init_list_=pvs.values(), nonpvs=list(pvs.keys())
            )
            self.log.info(f"PV_instances keys are {PV_instances.keys()}")
            lambdas = {}
            for name, suffix in pvs.items():
                self.log.info(
                    f"Setting functool with pv {prefix} and suffix to query {suffix}"
                )
                lambdas[suffix] = functools.partial(
                    PV_instances[prefix].get, suffix, as_string=True
                )
                self.log.info(
                    f"Setting new property {name} on PV to run lamba and get value of {lambdas[suffix]()}"
                )

                setattr(PV_instances[prefix], name, lambdas[suffix])
        return PV_instances

    def collect_CoR_data(self):
        dict_data = {}
        dict_data["EPICS"] = self.get_PVs()

        self.is_needle_mounted()
        initial_location = motors.omega.RBV
        locations_and_zooms = self.collect_four_images()
        self.drive_goniometer_to(initial_location)
        path = self.make_montage(locations_and_zooms)
        final_path = self.store_montage_for_report(path)
        dict_data["images"] = [final_path]

        return dict_data

    def get_zoom_dict(self):
        """ Example of zoom_dict structure, values will be different
            {'1.0': {'bottomRightX': '410',
                    'bottomRightY': '278',
                    'crosshairX': '589',
                    'crosshairY': '359',
                    'topLeftX': '383',
                    'topLeftY': '253',
                    'zoomLevel': '1.0'},
            '1.5': {'bottomRightX': '410',
                    'bottomRightY': '278',
                    'crosshairX': '582',
                    'crosshairY': '359',
                    'topLeftX': '383',
                    'topLeftY': '253',
                }
        """
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



        return self.zoom_dict

    def is_needle_mounted(self):
        # get robot PVs and compare
        pass

    def collect_single_picture(self, angle):
        self.drive_goniometer_to(angle)
        path, zoom = self.get_image_from_url(url=self.url, filename=angle)
        return [path, zoom]

    def drive_goniometer_to(self, angle):
        self.log.debug(f"Moving omega to {angle}")
        motors.omega.move(angle, wait=True, ignore_limits=True)

    def get_image_from_url(self, url, location="/var/tmp/", filename="image"):
        final_location = f"{location}{self.username}_{filename}.jpg"

        response = requests.get(url, stream=True)

        self.log.debug(f"Source data for zoom is {self.zoom_pv.char_value}")
        zoom = self.zoom_pv.get(as_string=True).strip("x")
        self.log.debug(f"Storing zoom level for this picture as {zoom}")

        with open(final_location, "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)
        del response
        return final_location, zoom

    def collect_four_images(self):
        # TODO: Ask permission to drive goniometer
        angles = [0, 90, 180, 270]
        picture_locations_and_zooms = [
            self.collect_single_picture(angle) for angle in angles
        ]
        return picture_locations_and_zooms

    def make_montage(self, locations_with_zooms):
        ninty = locations_with_zooms[1]
        locations_with_zooms.remove(ninty)
        locations_with_zooms.insert(2, ninty)
        locations = [path[0] for path in locations_with_zooms]
        self.log.debug(f"Files to make montage are: {locations}")
        pill_image = self.make_contact_sheet(
            locations_with_zooms,
            2,
            2,
            1024,
            768,
            1,
            1,
            1,
            1,
            1,
            draw_horizontal_line=True,
        )
        temp_save = f"/var/tmp/{self.username}_montage.png"
        pill_image.save(temp_save)
        pill_image.show()
        return temp_save

    def store_montage_for_report(self, montage_image):
        final_location = (
            f"{self.get('directories')[self.original_class]}/rotationaxis_montage.png"
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

        self.log.debug(f"locations_zoom: {locations_zoom}")
        self.log.debug(f"fnames: {fnames}")
        self.log.debug(f"fzooms: {fzooms}")

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
                        X_coordinate = int(zoom_dict[fzooms[count]]["crosshairX"])
                        self.log.debug(
                            f"Got an X, Y coordinates: {X_coordinate},{Y_coordinate}"
                        )
                        # Write horizontal line at Y height
                        ImageDraw.Draw(img).line(
                            (0, Y_coordinate, photow, Y_coordinate), fill=128, width=3
                        )
                        self.log.debug(
                            f"Line from 0,{Y_coordinate} to {photow},{Y_coordinate} drawn"
                        )
                        # Write vertical line at X width
                        ImageDraw.Draw(img).line(
                            (X_coordinate, 0, X_coordinate, photoh), fill=128, width=3
                        )
                        self.log.debug(
                            f"Line from {Y_coordinate},0 to {Y_coordinate},{photoh} drawn"
                        )

                    if draw_beam_cross == True:
                        self.log.debug("Ok, we have beam in yag. Going to draw a cross")
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
                    ImageDraw.Draw(img).text((0, 0), name, (255, 255, 255), font=font)
                except Exception as e:
                    self.log.critical(f"Failed to prepare montage with error {e}")
                self.log.debug("Pasting the images into the white canvas")
                inew.paste(img, bbox)
                count += 1
        self.log.debug("Finished making montage. Giving it back")
        return inew


class BeamlineEpics(epics.Device):
    def __init__(self, prefix=None, _init_list_=(), nonpvs=[]):
        nonpvs = nonpvs + ["get_PV_change_time"] + list(epics.Device._nonpvs)
        print(nonpvs)
        epics.Device.__init__(
            self, prefix=prefix, delim=":", attrs=list(_init_list_), nonpvs=nonpvs
        )

    def get_PV_change_time(self, suffix):
        return datetime.fromtimestamp(self.PV(suffix).timestamp)


if __name__ == "__main__":
    pass
#    a.make_montage(
#        [
#            "/var/tmp/ffd84814_0.png",
#            "/var/tmp/ffd84814_90.png",
#            "/var/tmp/ffd84814_180.png",
#            "/var/tmp/ffd84814_270.png",
#        ]
#    )
