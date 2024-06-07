from base import MOD_Base

from PyQt5.QtWidgets import QFileDialog, QDialog

from PyQt5 import QtCore
import datetime
from beamline import ID

import os, shutil
from PyQt5.QtCore import QDateTime

class CreateDirectories(MOD_Base):
    def __init__(self,needs_folder_to_write=False):
        MOD_Base.__init__(self,needs_folder_to_write)
        self.log.info(f'Loading {self.class_name}_MD module/instance')

        self.now = datetime.datetime.now()
        self.ROOT_DIR = f'/dls/{ID}/data/{self.now.year}/'

        self.overwrite_config_criteria2expire()

    def overwrite_config_criteria2expire(self):
        #A bit of a hack as this particular module won't follow the criteria2expire setup on the main config file. 
        #It will check the current date and make decisions based on that. 
        #This is to later be moved to base/GUI_blsetup.py to have all QT operations on the QT side of it

        key = f"{self.class_name}_{self.config['modules'][self.class_name]['widget2update']}_lastrun"
        if not self.check_day():
            self.log.warning('Current day is different from last setup. Resetting directories to empty and reseting last update for CreateDirectories to the past')
            self.reset_dirs()
            #Not ideal as I have QT5 stuff here
            self.set(key,QDateTime.fromSecsSinceEpoch(1553504400))
            
        else:
            self.log.debug('Directories still valid. Resetting date of last update for CreateDirectories to now')
            #Not ideal as I have QT5 stuff here
            self.set(key,QDateTime.currentDateTime())
            
    def check_day(self):
        check = self.now.strftime("%Y%m%d")
        dirs = self.get('directories')
        if type(dirs) != type({}) or dirs == {}:
            self.log.warning('List of directories does not exist in redis')
            return False
        for item in dirs:
            if dirs[item].split('/')[-2] != check:
                print(dirs[item].split('/')[-2])
                print(f'{check}')
                return False
            else:
                self.log.debug(f'{item} folder is still valid')
        return True

    def reset_dirs(self):
        self.set(f'directories', {})

    def launch_GUI(self):
        
        #folder = str(QFileDialog.getExistingDirectory(self, "Select Directory"))
        folder = self.FileDialog(directory=self.ROOT_DIR, forOpen=True, fmt='', isFolder=True)
        self.log.info(f'Got folder {folder}')
        folders = self.make_folders(folder)
        self.log.debug(f'Created folders for all modules {folders}. Also stored on redis hashmap as "directories"')
        self.set_status_true()
        

    def make_folders(self,base):
        dict_of_folders = {}
        for f in self.config['modules']:
            if self.config['modules'][f]['needs_folder_to_write']:
                self.log.info(f'{f}: need to create a folder for this module')
                new_folder = f'{base}/beamline_setup/{self.now.strftime("%Y%m%d")}/{f}'
                os.makedirs(new_folder, exist_ok=True)
                
                shutil.chown(new_folder,group='mx_staff')

                #print(new_folder)
                dict_of_folders[f] = new_folder
                shutil.chown(f'{base}/beamline_setup/{self.now.strftime("%Y%m%d")}',group='mx_staff')
        self.set(f'directories', dict_of_folders)
        return dict_of_folders

    def FileDialog(self,directory='', forOpen=True, fmt='', isFolder=False):
        #Taken from https://stackoverflow.com/questions/38746002/pyqt-qfiledialog-directly-browse-to-a-folder?rq=1
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
        dialog.setAcceptMode(QFileDialog.AcceptOpen) if forOpen else dialog.setAcceptMode(QFileDialog.AcceptSave)
    
        # SET FORMAT, IF SPECIFIED
        if fmt != '' and isFolder is False:
            dialog.setDefaultSuffix(fmt)
            dialog.setNameFilters([f'{fmt} (*.{fmt})'])
    
        # SET THE STARTING DIRECTORY
        if directory != '':
            dialog.setDirectory(str(directory))
        else:
            dialog.setDirectory(str(ROOT_DIR))
    
        if dialog.exec_() == QDialog.Accepted:
            self.log.debug(f'got {dialog.selectedFiles()[0]} from selector')
            path = dialog.selectedFiles()[0]  # returns a list
            return path
        else:
            return ''
