'''
#IMPORT LIBRARIES AND SET UP PATHS
'''
import sys, logging,  urllib, ast, time, glob, re, os, subprocess, numpy, pylab, math, multiprocessing, getpass
from PIL import Image
#from jinja2 import Environment, FileSystemLoader
from scipy import optimize
from numpy import mat
import numpy as np
import pandas as pd
from os.path import isfile as isfile
from os.path import isdir as isdir
from subprocess import call, Popen, PIPE, STDOUT, check_output

from redisobj import RedisHashMap
from beamline import redis
import json
from beamline import variables as blconfig
from beamline import motors
import matplotlib.pyplot as plt


import beamline

class TiltTest():
    """Sets up for a new tilttest job
    
    The tilttest functions are used by tilttest.py. Given a lanthanum 
    hexaborate powder diffraction sample the script calculates detector
    distance, pitch and yaw.    

    Note that running with python2.7 -m BeamCentre will not result in the pop-ups
    asking to accept changes and move CCDZ, these only occur when run through
    the entire Beamline Setup process    
    """
    
    '''
    Constructor
    '''
    def __init__(self,param_dict):
        self.user = getpass.getuser()
        if beamline.variables.ID == "MX1":
            self.mymap = RedisHashMap('mx1_beamline_setup')
            self.minimum_distance = 73 # Replace hardcoded number with PV?
        else:
            self.minimum_distance = 108 # Replace hardcoded number with PV?
            self.mymap = RedisHashMap('mx2_beamline_setup')
        self.detector_delta_threshold = 0.1 # detector distance offset change required

        self.datapoints = {}        
        self.delete_list = []
        self.param_dict = param_dict
        self.skip = 'No'
        ###start a log file
        self.logger = logging.getLogger('beamline_setup')
        self.logger.info('Running TiltTest script')

        try:
            if 'password' in self.param_dict:
                pass
            else:
                m = SetUp()
                m.DefineParameters()
                m.GetPassword()
                self.param_dict = m.ReturnDictionary()
        except:
            m = SetUp()
            m.DefineParameters()
            m.GetPassword()
            self.param_dict = m.ReturnDictionary()

    def GetEigerHeaderInfo(self, h5file):
        import pprint
        pp = pprint.PrettyPrinter(indent=4)
        header_dict = {}
        instrument = h5file['entry']['instrument']
        detector = instrument['detector']
        header_dict['PIXEL_SIZE'] = detector['x_pixel_size'].value * 1000 # convert to mm, same as y_pixel_size
        header_dict['DISTANCE'] = detector['detector_distance'].value * 1000 # convert m to mm
        # TODO assuming values on detector are in pixels
        header_dict['BEAM_CENTER_X'] = detector['beam_center_x'].value * header_dict['PIXEL_SIZE']
        header_dict['BEAM_CENTER_Y'] = detector['beam_center_y'].value * header_dict['PIXEL_SIZE']
        header_dict['WAVELENGTH'] = instrument['beam']['incident_wavelength'].value
        header_dict['SIZE1'] = detector['detectorSpecific']['x_pixels_in_detector'].value
        header_dict['SIZE2'] = detector['detectorSpecific']['y_pixels_in_detector'].value
        self.logger.debug('beam_center_x: %s (adxv-space)' % (detector['beam_center_x'].value))
        self.logger.debug('beam_center_y: %s (adxv-space)' % (detector['beam_center_y'].value))
        return header_dict


    def DefineParameters(self,image):
        if self.skip == "Yes":
            return

        self._path_and_imagename = image

        ###test if image exists
        if not isfile(self._path_and_imagename):        
            self.logger.error('Image '+str(self._path_and_imagename)+' does not exist')
            self.skip = "Yes"
            return

        self.header_dict = {}
        if beamline.detector_type == 'eiger':
            import hdf5plugin
            import h5py
            self.header_dict = self.GetEigerHeaderInfo(h5py.File(self._path_and_imagename, 'r'))

        elif beamline.detector_type == 'adsc':
            ###harvest header info
            imagefile = open(self._path_and_imagename, "r")
            fileheader = imagefile.read(1024)
            imagefile.close()
            for line in (''.join(fileheader)).split('\n')[1:-1]:
                try:
                    self.header_dict[((line.replace('=',' ').replace(';','')).split())[0]]=((line.replace('=',' ').replace(';','')).split())[1]
                except:
                    pass
        ###prepare output file
        try:
            self.outputfile = open('/var/tmp/'+str(self.user)+'_tilttest_output.txt', "w")
            self.delete_list.append('/var/tmp/'+str(self.user)+'_tilttest_output.txt')
            output_string = '"twotheta angle (deg)","X beamcentre (px)","Y beamcentre (px)","Detector distance (mm)"\n'
            self.outputfile.write(output_string)
            self.outputfile.close()
        except:
            self.logger.error('cannot write to output file /var/tmp/'+str(self.user)+'_tilttest_output.txt')
            self.skip = "Yes"
            return
        
        ###test output
        try:
            self.pixelsize_mm = float(self.header_dict['PIXEL_SIZE'])
            self.wavelength_A = float(self.header_dict['WAVELENGTH'])
            self.distance_mm = float(self.header_dict['DISTANCE'])
            self.detectorsize1_pixels = float(self.header_dict['SIZE1'])
            self.detectorsize2_pixels = float(self.header_dict['SIZE2'])
            self.detectorsize1_mm = self.detectorsize1_pixels * self.pixelsize_mm
            self.detectorsize2_mm = self.detectorsize2_pixels * self.pixelsize_mm
            if beamline.variables.ID == "MX1":
               self.beamx_mm = float(self.header_dict['BEAM_CENTER_Y']) #Xfit2d = YadcsDetector
               self.beamy_mm = float(self.header_dict['BEAM_CENTER_X']) #Yfit2d = XadcsDetector
            elif beamline.variables.ID == "MX2":
               self.beamx_mm = float(self.header_dict['BEAM_CENTER_X'])  # Xfit2d = Xadxv
               self.beamy_mm = self.detectorsize2_mm - float(self.header_dict['BEAM_CENTER_Y'])  # Yfit2d = Height - Yadxv
            self.beamx_pixels = self.beamx_mm / self.pixelsize_mm
            self.beamy_pixels = self.beamy_mm / self.pixelsize_mm

            self.logger.debug('Got header info from image at '+str(self.distance_mm)+' mm')
            self.logger.debug('self.pixelsize_mm '+str(self.pixelsize_mm)+' ')
            self.logger.debug('self.detectorsize1_pixels '+str(self.detectorsize1_pixels)+' ')
            self.logger.debug('self.detectorsize2_pixels '+str(self.detectorsize2_pixels)+' ')
            self.logger.debug('self.detectorsize1_mm '+str(self.detectorsize1_mm)+' ')
            self.logger.debug('self.detectorsize2_mm '+str(self.detectorsize2_mm)+' ')
            self.logger.debug('self.beamx_mm '+str(self.beamx_mm)+'(fit2d space)')
            self.logger.debug('self.beamy_mm '+str(self.beamy_mm)+'(fit2d space)')
            self.logger.debug('self.beamx_pixels '+str(self.beamx_pixels)+'(fit2d space)')
            self.logger.debug('self.beamy_pixels '+str(self.beamy_pixels)+'(fit2d space)')
            return 'PASS'
        
        except:
            self.logger.error('Cannot harvest header records from image')
            self.skip = "Yes"
            return 'FAIL'

    def GetLab6Peaks(self):
        if self.skip == "Yes":
            return
        ###define some parameters
        temperature = 295.65
        expansion_coefficient = 6.4e-6
        a = 4.156919032 # FOR 660a at 295.65 K (22.5 degrees C)
        #a = 4.1569118   # FOR 660b at 295.65 K (22.5 degrees C)

        a = a + (temperature - 295.65) * expansion_coefficient #correct a for thermal expansion
        indices = [[1,0,0],[1,1,0],[1,1,1],
                   [2,0,0],[2,1,0],[2,1,1],[2,2,0],
                   [3,0,0],[3,1,0],[3,1,1],[2,2,2],
                   [3,2,0],[3,2,1],
                   [4,0,0],[4,1,0],[4,1,1],
                   [3,3,1],[4,2,0],[4,2,1],[3,3,2],[4,2,2],
                   [5,0,0],[5,1,0],[5,1,1],
                  ]

        ###define lab6 dspacings in mm!
        self.dspacings = []
        for index in indices:
            d = math.sqrt(1 / (( (index[0]**2) + (index[1]**2) + (index[2]**2) ) / ( a**2 )))
            self.dspacings.append(d)

        ###define lab6 2theta in radians!
        self.twotheta = []
        for dspacing in self.dspacings:
            theta = math.asin(( self.wavelength_A ) / ( 2*dspacing ))
            self.twotheta.append(2 * theta)
        
        ###define lab6 peaks in mm!
        self.peaks = []
        for angle in self.twotheta:
            peak = (self.distance_mm * math.tan(angle))
            self.peaks.append(peak)

        ###calculate which peaks are on the image
        centre_to_edge = []
        centre_to_edge.append(self.beamx_mm)                             #centre_to_left  
        centre_to_edge.append(self.detectorsize1_mm - self.beamx_mm)      #centre_to_right 
        centre_to_edge.append(self.beamy_mm)                             #center_to_top   
        centre_to_edge.append(self.detectorsize2_mm - self.beamy_mm)      #center_to_bottom
        self.max_peak = max(centre_to_edge)
        self.rings = []
        for peak in self.peaks:
            if 0 < peak <= self.max_peak:
                self.rings.append(peak)

        self.logger.info('Defined position of '+str(len(self.rings))+' LaB6 peaks on the image')

        self.delete_list.append('/var/tmp/'+str(self.user)+'_calibrant.Ds')
        with open('/var/tmp/'+str(self.user)+'_calibrant.Ds', 'w') as calfile:
            for d in self.dspacings:
                calfile.write(str(d)+'\n')

    def ConvertH5MasterToTiff(self, filename, output_filename, image_number):
        # put imports here to isolate from MX1
        import hdf5plugin
        import h5py
        dirname = os.path.dirname(filename)
        data_filename = '%s_data_000001.h5' % filename.split('_master.h5')[0]
        h5file = h5py.File(data_filename)
        data = h5file['entry']['data']['data']
        image = Image.fromarray(data[image_number])
        image.save(output_filename) # after image, add convert('I;16') (16bit) convert('L') (8-bit) before save() to get the appropriate bit depth

    def MakeFit2dMacro(self):
        if self.skip == "Yes":
            return

        self.radius_px = float(sorted(self.rings)[0]) / float(self.pixelsize_mm)
        self.firstpoint_x = float(self.beamx_pixels)
        self.firstpoint_y = float(self.beamy_pixels) + float(self.radius_px) 
        self.secondpoint_x = float(self.beamx_pixels)
        self.secondpoint_y = float(self.beamy_pixels) - float(self.radius_px) 
        self.thirdpoint_x = float(self.beamx_pixels) + float(self.radius_px) 
        self.thirdpoint_y = float(self.beamy_pixels)
        self.fourthpoint_x = float(self.beamx_pixels) - float(self.radius_px) 
        self.fourthpoint_y = float(self.beamy_pixels)


        if beamline.detector_type:# == 'adsc':
            if beamline.detector_type == 'eiger':
                filename = '/var/tmp/%s.tif' % self.user
                self.ConvertH5MasterToTiff(self._path_and_imagename, filename, 0)
	    else:
                filename = self._path_and_imagename
            with open('/var/tmp/'+str(self.user)+'_fit2d.mac', 'w') as macfile:
                  macfile.write('%!*\ START OF MACRO FILE\n')
                  macfile.write('I ACCEPT\n')
                  macfile.write('POWDER DIFFRACTION (2-D)\n')
                  macfile.write('INPUT\n')
                  macfile.write(str(filename)+'\n')
                  macfile.write('O.K.\n')
		  if beamline.detector_type == 'eiger':
		      macfile.write('O.K.\n')
                  macfile.write('CALIBRANT\n')
                  macfile.write('USER DEFINED\n')
                  macfile.write('/var/tmp/'+str(self.user)+'_calibrant.Ds\n')
                  macfile.write('REFINE WAVELENGTH\n')
                  macfile.write('NO\n')
                  macfile.write('DISTANCE\n')
                  macfile.write(str(self.distance_mm)+'\n')
                  macfile.write('WAVELENGTH\n')
                  macfile.write(str(self.wavelength_A)+'\n')
                  macfile.write('X-PIXEL SIZE\n')
                  macfile.write(str(self.pixelsize_mm * 1000)+'\n')
                  macfile.write('Y-PIXEL SIZE\n')
                  macfile.write(str(self.pixelsize_mm * 1000)+'\n')
                  macfile.write('O.K.\n')
                  macfile.write('4\n')
                  macfile.write(str(self.firstpoint_x)+'\n')
                  macfile.write(str(self.firstpoint_y)+'\n')
                  macfile.write(str(self.secondpoint_x)+'\n')
                  macfile.write(str(self.secondpoint_y)+'\n')
                  macfile.write(str(self.thirdpoint_x)+'\n')
                  macfile.write(str(self.thirdpoint_y)+'\n')
                  macfile.write(str(self.fourthpoint_x)+'\n')
                  macfile.write(str(self.fourthpoint_y)+'\n')
                  if beamline.detector_type =='adsc':
		      macfile.write('O.K.\n')
                  macfile.write('EXIT\n')
                  macfile.write('EXIT FIT2D\n')
                  macfile.write('YES\n')
                  macfile.write('%!*\ END OF MACRO FILE\n')
        else:
            raise Exception('Unknown detector type in fit2d script creation method')
        self.delete_list.append('/var/tmp/'+str(self.user)+'_fit2d.mac')



        fit2d_command = 'fit2d -dim'+str(int(self.detectorsize1_pixels))+'x'+str(int(self.detectorsize2_pixels))+' -mac/var/tmp/'+str(self.user)+'_fit2d.mac'

        p = Popen(fit2d_command, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
        fit2d_output = p.stdout.readlines()

        try:
            ###GET DISTANCE
            index = [i for i, item in enumerate(fit2d_output) if re.search('.*Refined sample to detector distance =.*', item)][-1]
            self.refined_distance = fit2d_output[index].split()[7]
             
            ###GET PITCH AND YAW
            index = [i for i, item in enumerate(fit2d_output) if re.search('.*INFO: ROT X =.*', item)][-1]
            self.refined_yaw = fit2d_output[index].split()[4]
            self.refined_pitch = fit2d_output[index].split()[8]
              
            ###GET WAVELENGTH
            index = [i for i, item in enumerate(fit2d_output) if re.search('.*INFO: Refined wavelength =.*', item)][-1]
            self.refined_wavelength = fit2d_output[index].split()[4]
            
            ###GET BEAMCENTRE X AND Y PIXELS
            index = [i for i, item in enumerate(fit2d_output) if re.search('.*INFO: Refined Beam centre =.*(pixels).*', item)][-1]
            if beamline.variables.ID == "MX1":
               self.refined_beamcentrex_px = fit2d_output[index].split()[6] #XadscDetector = Yfit2d
               self.refined_beamcentrey_px = fit2d_output[index].split()[5] #YadscDetector = Xfit2d
            # Fit2d to adxv
            elif beamline.variables.ID == "MX2":
               self.beamx_pixels = float(self.header_dict['BEAM_CENTER_X']) / self.pixelsize_mm
               self.beamy_pixels = float(self.header_dict['BEAM_CENTER_Y']) / self.pixelsize_mm
               self.logger.debug(fit2d_output[index])
               self.refined_beamcentrex_px = fit2d_output[index].split()[5] #Xadxv=Xfit2d
               self.refined_beamcentrey_px = self.detectorsize2_pixels - float(fit2d_output[index].split()[6]) #Yadxv=Height-Yfit2d
            
            ###GET BEAMCENTRE X AND Y MM
            index = [i for i, item in enumerate(fit2d_output) if re.search('.*INFO: Refined Beam centre =.*(mm).*', item)][-1]
            if beamline.variables.ID == "MX1":
               self.refined_beamcentrex_mm = fit2d_output[index].split()[6] #XadscDetector = Yfit2d
               self.refined_beamcentrey_mm = fit2d_output[index].split()[5] #YadscDetector = Xfit2d
               #self.swap_center = True #To be able to print in the log on image coordinate system and not on fit2d coordinate system
                 # Fit2d to adxv
            elif beamline.variables.ID == "MX2":
               self.beamx_mm = float(self.header_dict['BEAM_CENTER_X'])
               self.beamy_mm = float(self.header_dict['BEAM_CENTER_Y'])
               self.refined_beamcentrex_mm = float(self.refined_beamcentrex_px) * float(self.pixelsize_mm)
               self.refined_beamcentrey_mm = float(self.refined_beamcentrey_px) * float(self.pixelsize_mm)
             
            print "###IMAGE "+str(self._path_and_imagename)
            #print "DISTANCE:   "+str(self.refined_distance)+" ("+str(self.distance_mm)+")"
            print "PARAMETER: value (previous) #Difference @Change percent"
            
            dist_comp = self.compare_values(self.refined_distance,self.distance_mm)
            wave_comp = self.compare_values(self.refined_wavelength,self.wavelength_A)
            x_px = self.compare_values(self.refined_beamcentrex_px,self.beamx_pixels)
            y_px = self.compare_values(self.refined_beamcentrey_px,self.beamy_pixels)
            x_mm = self.compare_values(self.refined_beamcentrex_mm,self.beamx_mm)
            y_mm = self.compare_values(self.refined_beamcentrey_mm,self.beamy_mm)
            print "DISTANCE:  %s (%s) #%s @%s" % dist_comp
            print "WAVELENGTH: %s (%s) #%s @%s" % wave_comp
            print "PITCH:      "+str(self.refined_pitch)+" deg"
            print "YAW:        "+str(self.refined_yaw)+" deg"
            print "ATTENTION: on MX1 x,y might look swapped"
            print "BEAM X PX: %s (%s) #%s @%s " % x_px
            print "BEAM Y PX: %s (%s) #%s @%s " % y_px
            print "BEAM X MM: %s (%s) #%s @%s " % x_mm
            print "BEAM Y MM: %s (%s) #%s @%s " % y_mm
            print " "
             
            self.datapoints[float(self.distance_mm)] = [float(self.refined_distance),
                                                        float(self.refined_wavelength),
                                                        float(self.refined_pitch),
                                                        float(self.refined_yaw),
                                                        float(self.refined_beamcentrex_px),
                                                        float(self.refined_beamcentrey_px),
                                                        float(self.refined_beamcentrex_mm),
                                                        float(self.refined_beamcentrey_mm)]
        except Exception as e:
            self.logger.error(e)
            self.logger.error('fit2d did not run for '+str(self._path_and_imagename))

    def compare_values(self,new,old):
        diff = abs(float(new)-float(old))
        change_percent = round(diff/float(old)*100,3)
        #new = round(new,3)
        #old = round(old,3)
        return (new,old,diff,change_percent)

    def RefineBeamcentre(self):
        # Needs debugging; currently only works on MX2 if set to zero.
        if len(self.datapoints.keys()) < 0:
            self.logger.error('There were insufficient points to run fitting')
            return
        
        ###FITTING X DATA
        self.logger.info('Fitting beam centre X data')

        x = self.datapoints.keys()
        y = []
        for value in x:
            if beamline.variables.ID == "MX1": # mm
                y.append(self.datapoints[value][6])
            elif beamline.variables.ID == "MX2":
                y.append(self.datapoints[value][4]) # pixels

        x = numpy.array(x)
        y = numpy.array(y)
        
        
        def f(x, m, c):
            return (m * x + c)
        
        def resid(p, y, x):
            m, c = p
            return y - f(x, m, c)
        
        m0, c0 = 1,1024
        
        [m, c], flag = optimize.leastsq(resid, [m0, c0], args=(y, x))
        
        ###CREATE A PYLAB PLOT OBJECT
#        self.myfigure = pylab.figure()  
        self.myfigure, self.ax1  = plt.subplots()
        self.ax1.set_title('Deviation of beam centre as a function of distance')
        self.ax1.set_xlabel('Distance (mm)')
        if beamline.variables.ID == "MX1":
            self.ax1.set_ylabel('Beam centre X (mm)', color='r')
        elif beamline.variables.ID == "MX2":
            self.ax1.set_ylabel('Beam centre X (px)', color='r')
        self.ax1.tick_params('y', colors='r')

        #plot the datapoints
        self.ax1.plot(x, y, 'ro')
        
        # plot the smooth model fit
        xc = numpy.linspace(x.min(), x.max(), 2)
        self.ax1.plot(xc, f(xc, m, c ), 'r-')
        
        
        self.xbeam_m = m
        self.xbeam_c = c

        ###FITTING Y DATA
        self.logger.info('Fitting beam centre Y data')

        x = self.datapoints.keys()
        y = []
        for value in x:
            if beamline.variables.ID == "MX1": # mm
                y.append(self.datapoints[value][7])
            elif beamline.variables.ID == "MX2":
                y.append(self.datapoints[value][5]) # pixels


        x = numpy.array(x)
        y = numpy.array(y)
                
        def f(x, m, c):
            return (m * x + c)
        
        def resid(p, y, x):
            m, c = p
            return y - f(x, m, c)
        
        m0, c0 = 1,1024
        
        [m, c], flag = optimize.leastsq(resid, [m0, c0], args=(y, x))
        
        #add datapoints to pylab plot
        self.ax2 = self.ax1.twinx()
        self.ax2.plot(x, y, 'bo')
        if beamline.variables.ID == "MX1":
            self.ax2.set_ylabel('Beam centre Y (mm)', color='b')
        elif beamline.variables.ID == "MX2":
            self.ax2.set_ylabel('Beam centre Y (px)', color='b')
        self.ax2.tick_params('y', colors='b')
        
        # plot the smooth model fit
        xc = numpy.linspace(x.min(), x.max(), 2)
        self.ax2.plot(xc, f(xc, m, c ), 'b-')

        plt.show()

        #save the plot to file
        output_image='/var/tmp/'+str(self.user)+'_beamcentre_fit.png'
        self.delete_list.append(output_image)
        self.myfigure.savefig(output_image, format="png")

        self.ybeam_m = m
        self.ybeam_c = c

        ###USE THE RESULTS
        if beamline.variables.ID == 'MX2':
            old_mx = beamline.detector.xbeam_slope
            old_cx = beamline.detector.xbeam_intercept
            old_my = beamline.detector.ybeam_slope
            old_cy = beamline.detector.ybeam_intercept
        elif beamline.variables.ID == 'MX1':
            xslope_pv = 'SR03BM01HU02IOC09:ADSC_XBEAM_SLOPE'
            xicpt_pv = 'SR03BM01HU02IOC09:ADSC_XBEAM_INTERCEPT'
            yslope_pv = 'SR03BM01HU02IOC09:ADSC_YBEAM_SLOPE'
            yicpt_pv = 'SR03BM01HU02IOC09:ADSC_YBEAM_INTERCEPT'
            old_mx = epics.caget(xslope_pv)
            old_cx = epics.caget(xicpt_pv)
            old_my = epics.caget(yslope_pv)
            old_cy = epics.caget(yicpt_pv)
        else:
            self.logger.error('Cannot determine beamline')
            return

        mxdiff = abs(old_mx - self.xbeam_m)
        mydiff = abs(old_my - self.ybeam_m)
        cxdiff = abs(old_cx - self.xbeam_c)
        cydiff = abs(old_cy - self.ybeam_c)

        #self.logger.info(('Change X formula from m = %s to %s (delta %s) and c = %s to %s (delta %s)') % (old_mx,self.xbeam_m,mxdiff,old_cx,self.xbeam_c,cxdiff))
        #self.logger.info(('Change Y formula from m = %s to %s (delta %s) and c = %s to %s (delta %s)') % (old_my,self.ybeam_m,mydiff,old_cy,self.ybeam_c,cydiff))


        arr = np.array([['name', 'old', 'new'],['slope x',old_mx,self.xbeam_m],['slope y',old_my,self.ybeam_m],['intercept x',old_cx,self.xbeam_c],['intercept y',old_cy,self.ybeam_c]])
        df = pd.DataFrame(arr[1:,1:],index=arr[1:,0],columns=arr[0,1:])
        df['old'] = pd.to_numeric(df['old']).round(7)
        df['new'] = pd.to_numeric(df['new']).round(7)
        df['diff'] = abs(df['old'] - df['new'])        
        df['% change'] = df['diff']/df['new']*100
        df['% change'] = df['% change'].round(4)
        self.logger.info("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        self.logger.info("Table comparision of X,Y beam fit formula")
        self.logger.info('%s %s' %('\n',df))
        self.logger.info("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        delta_dist = self.CalculateOffsetDistance()['delta_dist']
        self.logger.info("Detector distance offset: %5f - values of %s or less are acceptable" % (delta_dist, self.detector_delta_threshold))
        self.logger.info("Look at the values above, particularly the % change before accepting to push the values to the beam centre PVs")
#        self.myfigure.show()

        #app = wx.PySimpleApp()
        response = wx.lib.dialogs.messageDialog(title='Beamcentre', message='Do you want to update the header records?',aStyle=wx.YES_NO)
        #app.Yield()
        #del app

        if response.returnedString == "No":
            self.logger.info('will not update header records or save images')
            pylab.close('all')
            return
        else:
            self.logger.info('saving images and updating headers')
            pylab.close('all')

	if beamline.variables.ID == 'MX1':
            epics.caput(xslope_pv, self.xbeam_m)
            epics.caput(xicpt_pv, self.xbeam_c)
            epics.caput(yslope_pv, self.ybeam_m)
            epics.caput(yicpt_pv, self.ybeam_c)
        elif beamline.variables.ID == 'MX2':
            beamline.detector.xbeam_slope = self.xbeam_m
            beamline.detector.xbeam_intercept = self.xbeam_c
            beamline.detector.ybeam_slope = self.ybeam_m
            beamline.detector.ybeam_intercept = self.ybeam_c
        else:
            self.logger.error('Cannot determine beamline')
            return
        self.logger.info('Updated beamcentre PVs in EPICS')

        
        
        ###transfer output image to users calibration dir
        timestamp = time.strftime("%y-%m-%d-%H-%M")
        ###transfer output image to /data/home/calibration dir
        local_file = '/var/tmp/'+str(self.user)+'_beamcentre_fit.png'
        remote_file2 = '/data/home/calibration/beamcenterlog.png'
        remote_file3 = '/data/home/calibration/beamcenter/'+str(timestamp)+'_beamcenterlog.png'
        sshc = ssh.SSHClient()
        sshc.set_missing_host_key_policy(ssh.AutoAddPolicy())
        sshc.connect('localhost', username='blctl', password=str(self.param_dict['password']))
        stdin, stdout, stderr = sshc.exec_command('cp '+local_file+' '+remote_file2)
        self.logger.info('Wrote output to '+str(remote_file2))
        stdin, stdout, stderr = sshc.exec_command('cp '+local_file+' '+remote_file3)
        self.logger.info('Wrote output to '+str(remote_file3))
        sshc.close()


        self.mymap['BeamcentreDate'] = time.time()

    def CalculateOffsetDistance(self):
        if len(self.datapoints.keys()) < 3:
            return

        ###FITTING X DATA
        self.logger.info('Refining detector distance')

        working_dist = min(self.datapoints.keys())
        refined_dist = self.datapoints[working_dist][0]
        delta_dist = refined_dist - working_dist

        self.mymap['ExpectedDist'] = str(working_dist)
        self.mymap['RefinedDist'] = str(refined_dist)

        self.logger.info('image at '+str(working_dist)+' mm was refined to '+str(refined_dist)+' mm. A discrepency of '+str(delta_dist)+' mm')
        
        ###USE THE RESULTS
         
        if beamline.variables.ID == 'MX2':
            ccd_z_offset_pv = 'SR03ID01CCD01:Z_MTR_OFFSET_SP'
            ccd_y2_offset_pv = 'SR03ID01CCD01:Y2_MTR_OFFSET_SP'
            self.jack_separation = 302
            old_z_offset = epics.caget(ccd_z_offset_pv)
            self.old_y2_offset = epics.caget(ccd_y2_offset_pv)
        elif beamline.variables.ID == 'MX1':
            ccd_z_offset_pv = 'SR03BM01CCD01:Z_MTR_OFFSET_SP'
            ccd_y2_offset_pv = 'SR03BM01CCD01:Y2_MTR_OFFSET_SP'
            self.jack_separation = 308
            old_z_offset = epics.caget(ccd_z_offset_pv)
            self.old_y2_offset = epics.caget(ccd_y2_offset_pv)
        else:
            self.logger.error('Cannot determine beamline')
            return

        new_offset = float(old_z_offset) - delta_dist
        return {'ccd_z_offset_pv': ccd_z_offset_pv, 'delta_dist': delta_dist, 'new_offset' : new_offset, 'old_z_offset' : old_z_offset}

    def RefineDistance(self):
        try:
            offset_distance = self.CalculateOffsetDistance()
        except TypeError:
            print 'not enough data points, exiting'
            return
        
        self.logger.info('Distance is off by '+str(offset_distance['delta_dist'])+' this can be fixed by changing the CCD Z offset from '+str(offset_distance['old_z_offset'])+' to '+str(offset_distance['new_offset']))
        if abs(offset_distance['delta_dist']) < self.detector_delta_threshold:
            self.logger.info('the error in the detector distance is less than the threshold of %s mm, no need to update.' % self.detector_delta_threshold)
        else:
            response = wx.lib.dialogs.messageDialog(title='Beamcentre', message='Do you want to change the CCD Z offset from '+str(offset_distance['old_z_offset'])+' to '+str(offset_distance['new_offset'])+'?\nNote: will not change headers on images already collected. Running repeatedly on the same images will continue to move distance offset.',aStyle=wx.YES_NO)

            if response.returnedString == "No":
                self.logger.info('will not change CCD Z offset')
            else:
                self.logger.info('updating CCD Z offset')
                epics.caput(offset_distance['ccd_z_offset_pv'], offset_distance['new_offset'])
                self.logger.info('Updated CCD Z offset in EPICS')

    def RefinePitchYaw(self):
        if len(self.datapoints.keys()) < 3:
            return

        pitch = self.datapoints[min(self.datapoints.keys())][2]
        yaw = self.datapoints[min(self.datapoints.keys())][3]
        new_y2_offset = self.old_y2_offset - ( self.jack_separation * numpy.tan( numpy.radians(pitch) ))
        
        self.logger.info('Detector is pitched by '+str(pitch)+' and yawed by '+str(yaw)+' degrees.')
        self.logger.info('Pitch can be corrected by changing the CCD Y2 OFFSET from '+str(self.old_y2_offset)+' to '+str(new_y2_offset))
        self.logger.info('Yaw can only be corrected by trimming the A frame using the jacking bolts on the feet')

    def CleanTempFiles(self):
        time.sleep(2)#it was deleting the temp files before they'd been copied to /data/home/calibration!
        #all files in delete list are in the /var/tmp dir
        no_duplicates = list(set(self.delete_list))
        for file in no_duplicates:
            try:
                os.remove(file)
            except:
                self.logger.info('Could not delete '+file)
                
if __name__ == '__main__':
    app = wx.PySimpleApp()
    tilttest = TiltTest('NotDefined')
    tilttest.TakeImages()
    for image in tilttest.imagelist:
        tilttest.DefineParameters(image)
        tilttest.GetLab6Peaks()
        tilttest.MakeFit2dMacro()
    tilttest.RefineBeamcentre()
    tilttest.RefineDistance()
    tilttest.RefinePitchYaw()
    tilttest.CleanTempFiles()
    del app



