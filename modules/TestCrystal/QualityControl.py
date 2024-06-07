#!/dls/science/groups/b21/PYTHON3/bin/python3

from beamline import detector
from beamline import redis
import json
import os
import pandas as pd
import argparse
import logging
from logging.config import dictConfig


class QualityControl():
    
    def __init__(self):
        self.programs = {"fast_dp": {'procpath': 'fast_dp', 'software' : self.parse_fastdp},
                         "xia2": {'procpath': 'fast_dp', 'software' : self.parse_xia2}}  
#        to re-add these you need to put parameter back into __init__ as argument
#        self.last = int(parameter['last'])
#        self.number = int(parameter['number'])
#        self.debug = parameter['debug']
        self.redis_database = "i04:eiger:collections"
        self.special_collections = ['xraycentring']




        ### LOGGING BIT
        ERROR_FORMAT = "%(levelname)s: %(asctime)s in %(funcName)s in %(filename)s at line %(lineno)d: %(message)s\n"
        DEBUG_FORMAT = "%(asctime)s [%(levelname)s] in %(funcName)s in %(filename)s at line %(lineno)d: %(message)s"
        LOG_CONFIG = {'version':1,
              'formatters':{'error':{'format':ERROR_FORMAT},
                            'debug':{'format':DEBUG_FORMAT}},

              'handlers':{'console':{'class':'logging.StreamHandler',
                                     'formatter':'error',
                                     'level':logging.ERROR},

                          'file':{'class':'logging.FileHandler',
                                  'filename':'QualityControl.log',
                                  'formatter':'debug',
                                  'level':logging.DEBUG}},

              'root':{'handlers':('console', 'file')}}


        #logging.basicConfig()
        #logging.config.dictConfig(LOG_CONFIG)

        #self.log = logging.getLogger(self.__class__.__name__)


        #self.log.setLevel(logging.INFO)



    def get_masters(self, last, number):
        # returns the name of the master file for the n collections preceeding (and including) the last

        start = last
        end = last + number - 1

        masters = []

        for collection in redis.lrange("i04:eiger:collections", start, end * 10):
            
        #unix_time,new_state,filepath_rbv,filename_rbv, new_master,new_state_msg,new_status_msg,detector_ROI,
        #detector_ROIMode, time_to_injection,omega, new_energy,new_current, new_distance,new_flux, 
        #gonibase_x_vel,gonibase_y_vel,gonibase_z_vel
        
            payload = json.loads(collection.decode('utf'))
            
            if payload[5] == "Acquire" and payload[7] != "4M" and not "screening" in payload[2].split("/"):
                # print('+++++++', payload)
                masters.insert(0, f"{json.loads(collection.decode('utf'))[4]}")
                                                              
        last_collections = masters[1 : number + 1]

        return masters[len(masters) - number - last + 1:len(masters) - last + 1]

    def get_processed_dir(self, masterfile):
        # returns the visit directory, that of the data collection, 
        # the name of the processed dir (different if xrc) and a tag to identify non-rotation datasets 

        split_path = masterfile.split("/")

        visit_dir = '/'.join(split_path[0:6])
        sub_path = '/'.join(split_path[6:])

        dataset_id = sub_path.split("_master")[0]
        processed_dir = visit_dir+"/processed/"+dataset_id

        if 'xraycentring' in masterfile:
            special_tag = 1
        else:
            special_tag = 0

        return processed_dir



    def extract_quality_parameters(self, masterfile, processing_pipeline = 'fast_dp'):
        # opens the output of the specific pipeline and returns the results from the appropriate log files               
        payload = {}                

#        if processing_pipeline.keys():
#            self.log.error(f"extracting data from {processing_pipeline.keys()}")                      

#        print(f"Master file is {masterfile}")

        payload['masterfile'] = masterfile
        processing_directory = self.get_processed_dir(masterfile)

#        for processing_software in processing_pipeline:

#            if self.debug:
#                self.log.info(f'[DEBUG]: analysing log files from {processing_software}')

        to_add = self.programs[processing_pipeline]['software'](processing_directory)
        if to_add:
            payload.update(to_add)  

        return payload


    def parse_fastdp(self, processing_directory):        
        payload = {}    


        self.correct_lp = '/'.join([processing_directory, "fast_dp", "CORRECT.LP"])
        self.fastdp_log = '/'.join([processing_directory, "fast_dp", "fast_dp.log"])
        self.aimless_log = '/'.join([processing_directory, "fast_dp", "aimless.log"])


#        if self.debug:
#        self.log.info(f'\n[DEBUG]: Running FAST_DP analysis on {processing_directory}')        
#        self.log.info(f'[DEBUG]: opening {self.correct_lp}')

        # ISA from CORRECT.LP
        if os.path.exists(self.correct_lp):

#            if self.debug:
#            self.log.info(f'{self.correct_lp} log exists')

            # then parses CORRECT.LP output file for the ISa value
            with open(self.correct_lp) as resultfile:
                resultfile_content = resultfile.readlines()
                clean_file = [x[:-1] for x in resultfile_content]

                n = 0
                for i in clean_file:
                    if ('   ISa') in i:
                        isa = clean_file[n+1][-6:]
                        payload['ISa'] = isa
                        

                    n = n + 1


        # Resolution etc from fast_dp.log
        if os.path.exists(self.fastdp_log):

#            if self.debug:
#            self.log.info(f'[DEBUG]: {self.fastdp_log} log exists')

            # then parses CORRECT.LP output file for the ISa value
            with open(self.fastdp_log) as logfile:
                logfile_content = logfile.readlines()
                clean_file = [x[:-1] for x in logfile_content]

                n = 0
                for i in clean_file:

                    if ('   Completeness') in i:
                        payload['Completeness'] = float(clean_file[n][-19:-13])

                    if ('CC 1/2') in i:
                        payload['CChalf'] = float(clean_file[n][-19:-13])

                    if ('Rmerge') in i:
                        payload['Rmerge'] = float(clean_file[n][-12:-6])

                    if ('High resolution') in i:
                        payload['Resolution'] = float(clean_file[n][-6:])

                    n = n + 1         

        # Resolution etc from aimless.log
        if os.path.exists(self.aimless_log):

#            if self.debug:
#            self.log.info(f'[DEBUG]: {self.aimless_log} log exists')


            with open(self.aimless_log) as logfile:
                logfile_content = logfile.readlines()
                clean_file = [x[:-1] for x in logfile_content]

                n = 0
                for i in clean_file:

                    if ('Completeness            ') in i:
                        payload['Aimless_Completeness'] = float(clean_file[n][43:48])

                    if ('Mn(I) half-set correlation CC(1/2)') in i:
                        payload['Aimless_CChalf'] = float(clean_file[n][43:48])

                    if ('Rmeas (all I+ & I-) ') in i:
                        payload['Aimless_Rmeas'] = float(clean_file[n][53:58])

                    if ('Rmerge  (within I+/I-)') in i:
                        payload['Aimless_Rmerge'] = float(clean_file[n][53:58])

                    if ('High resolution limit') in i:
                        payload['Aimless_Resolution'] = float(clean_file[n][43:48])

                    n = n + 1  

        return payload


    def parse_xia2(self, processing_directory):        
        # model function
        payload = {}
        payload['xia2']='blah'
        return payload



                       
    def logging(self, message):
        #needs a better way of logging
        self.log.error(f'[DEBUG]: analyzing {message}')
#         self.log.append(f'[DEBUG]: analyzing {message}')
        return
               
                      
                               
                               
                               
                               
                               
    def full_analysis(self):
        print ()
                       
        if self.debug:
            self.log.info ('running in DEBUG mode')
                               
            self.log.info('FULL ANALYSIS REPORT\n\n')
        
        counter = 1
                               
        for dataset in self.get_masters(self.last, self.number):

            
            if self.debug:
                self.log.info(f'{counter}/{self.number} - masterfile: {dataset}')
                self.log.info(f'[DEBUG]: a{counter}/{self.number} - processed directory: {self.get_processed_dir(dataset)}')

                self.log.info(f'[DEBUG]: analyzing {dataset}')

            result = self.extract_quality_parameters(dataset, self.programs)
            
            print (result)
            if self.debug == True:
                if result != {}:
                   print(f'AUTOPROCESSING RESULTS: {result}\n')
                else:
                   print('no result')
            counter += 1
                               
        return result

                               
                               
           
def check_parameters():
    # reads the input parameters for the executable

    parser = argparse.ArgumentParser(
        description="Dataset quality check", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-l", dest='last', action ='store', type=int, help="last dataset")
    parser.add_argument("-n", dest='number', action ='store', type=int, help="number of datasets before the last")
    parser.add_argument("-d", dest='debug', action='store_true', help="debug mode")
    args = parser.parse_args()
    config = vars(args)


    return config


class TestCrystalResults():
    def __init__(self, masterfile):
        print("inside __init__")
        self.masterfile = masterfile
        print("before self.qc")
        self.qc = QualityControl()
        print("after self.qc")

    def get_results(self):
        """ Return a dictionary of processing results for a specific masterfile """
        return self.qc.extract_quality_parameters(self.masterfile)


if __name__ == "__main__":

    arguments = check_parameters()
    qc = QualityControl(arguments)
                               
    qc.full_analysis()


    
