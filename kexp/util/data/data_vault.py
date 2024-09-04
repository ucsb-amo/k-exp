import time
import numpy as np
import os
import copy
import h5py

from kexp.util.data.server_talk import check_for_mapped_data_dir, get_run_id, update_run_id

try:
    data_dir = os.getenv("data")

    code_dir = os.getenv("code")
    params_path = os.path.join(code_dir,"k-exp","kexp","config","expt_params.py")
    cooling_path = os.path.join(code_dir,"k-exp","kexp","base","sub","cooling.py")
    imaging_path = os.path.join(code_dir,"k-exp","kexp","base","sub","image.py")
except:
    pass

class DataSaver():

    def save_data(self,expt,expt_filepath="",data_object=None):

        if expt.setup_camera:
            
            pwd = os.getcwd()
            os.chdir(data_dir)
            
            fpath, _ = self._data_path(expt.run_info)

            if data_object:
                f = data_object
            else:
                f = h5py.File(fpath,'r+')

            del f['params']
            params_dset = f.create_group('params')
            self._class_attr_to_dataset(params_dset,expt.params)

            if expt_filepath:
                with open(expt_filepath) as expt_file:
                    expt_text = expt_file.read()
                f.attrs["expt_file"] = expt_text
            else:
                f.attrs["expt_file"] = ""

            with open(params_path) as params_file:
                params_file = params_file.read()
            f.attrs["params_file"] = params_file

            with open(cooling_path) as cooling_file:
                cooling_file = cooling_file.read()
            f.attrs["cooling_file"] = cooling_file

            with open(imaging_path) as imaging_file:
                imaging_file = imaging_file.read()
            f.attrs["imaging_file"] = imaging_file

            f.close()
            print("Parameters saved, data closed.")
            self._update_run_id(expt.run_info)
            os.chdir(pwd)

    def create_data_file(self,expt):

        if expt.setup_camera:

            pwd = os.getcwd()

            check_for_mapped_data_dir()
            os.chdir(data_dir)

            fpath, folder = self._data_path(expt.run_info)

            if not os.path.exists(folder):
                os.mkdir(folder)

            expt.run_info.filepath = fpath
            expt.run_info.xvarnames = expt.xvarnames

            f = h5py.File(fpath,'w')
            data = f.create_group('data')

            f.attrs['camera_ready'] = 0
            f.attrs['camera_ready_ack'] = 0
            
            f.attrs['xvarnames'] = expt.xvarnames
            data.create_dataset('images',data=expt.images)
            data.create_dataset('image_timestamps',data=expt.image_timestamps)
            if expt.sort_idx:
                data.create_dataset('sort_idx',data=expt.sort_idx)
                data.create_dataset('sort_N',data=expt.sort_N)
            
            # store run info as attrs
            self._class_attr_to_attr(f,expt.run_info)
            # also store run info as dataset
            runinfo_dset = f.create_group('run_info')
            self._class_attr_to_dataset(runinfo_dset,expt.run_info)
            params_dset = f.create_group('params')
            self._class_attr_to_dataset(params_dset,expt.params)
            cam_dset = f.create_group('camera_params')
            self._class_attr_to_dataset(cam_dset,expt.camera_params)
            
            f.close()

            os.chdir(pwd)

            return fpath

    def _class_attr_to_dataset(self,dset,obj):
        try:
            keys = list(vars(obj)) 
            for key in keys:
                if not key.startswith("_"):
                    value = vars(obj)[key]
                    try:
                        dset.create_dataset(key, data=value)
                    except Exception as e:
                        print(f"Failed to save attribute \"{key}\" of {obj}.")
                        print(e)
        except Exception as e:
            print(e)

    def _class_attr_to_attr(self,dset,obj):
        try:
            keys = list(vars(obj))  
            for key in keys:
                value = vars(obj)[key]
                dset.attrs[key] = value
        except Exception as e:
            print(e)

    def _data_path(self,run_info):
        run_id_str = f"{str(run_info.run_id).zfill(7)}"
        expt_class = run_info.expt_class
        datetime_str = run_info.run_datetime_str
        filename = run_id_str + "_" + datetime_str + "_" + expt_class + ".hdf5"
        filepath_folder = os.path.join(data_dir,run_info.run_date_str)
        filepath = os.path.join(filepath_folder,filename)
        return filepath, filepath_folder

    def _update_run_id(self,run_info):
        update_run_id(run_info)

    def _get_rid(self):
        return get_run_id()

class DataVault():
    def __init__(self,atomdata_list=[],datalist_path=[]):

        if atomdata_list != []:
            if ~isinstance(atomdata_list,list):
                atomdata_list = [copy.deepcopy(atomdata_list)]
            self.atomdata_list = atomdata_list

        self.run_ids = [ad.run_info.run_id for ad in atomdata_list]
        self.data_filepaths = [ad.run_info.filepath for ad in atomdata_list]
        self.data_dates = [time.strftime('%Y-%m-%d',ad.run_info.run_datetime) for ad in atomdata_list]
