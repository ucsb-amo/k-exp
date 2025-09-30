import time
import numpy as np
import os
import copy
import h5py

from kexp.util.data.server_talk import check_for_mapped_data_dir, get_run_id, update_run_id
from kexp.base.sub.dealer import Dealer

data_dir = os.getenv("data")

code_dir = os.getenv("code")
params_path = os.path.join(code_dir,"k-exp","kexp","config","expt_params.py")
cooling_path = os.path.join(code_dir,"k-exp","kexp","base","sub","cooling.py")
imaging_path = os.path.join(code_dir,"k-exp","kexp","base","sub","image.py")

class DataSaver():

    def save_data(self,expt:Dealer,expt_filepath="",data_object=None):

        if expt.setup_camera:
            
            pwd = os.getcwd()
            os.chdir(data_dir)
            
            fpath, _ = self._data_path(expt.run_info)

            if data_object:
                f = data_object
            else:
                f = h5py.File(fpath,'r+')

            if expt.scope_data._scope_trace_taken:
                scope_data = f['data'].create_group('scope_data')
                for scope in expt.scope_data.scopes:
                    data = scope.reshape_data()
                    if expt.sort_idx:
                        data = expt._unshuffle_ndarray(data,exclude_dims=2)
                    scope_data.create_dataset(scope.label,data=data)

            if expt.sort_idx:
                expt.images = np.array(f['data']['images'])
                expt.image_timestamps = np.array(f['data']['image_timestamps'])
                expt.xvardims = [len(xvar.values) for xvar in expt.scan_xvars]
                expt.N_xvars = len(expt.xvardims)
                expt._unshuffle_struct(expt)
                f['data']['images'][...] = expt.unscramble_images()
                f['data']['image_timestamps'][...] = expt._unscramble_timestamps()
                expt._unshuffle_struct(expt.params)

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
            # self._update_run_id(expt.run_info)
            os.chdir(pwd)

    def get_xvardims(self,expt):
        return [len(xvar.values) for xvar in expt.scan_xvars]
    
    def pad_sort_idx(self,expt):
        maxN = np.max(expt.sort_N)
        for i in range(len(expt.sort_idx)):
            N_to_pad = maxN - len(expt.sort_idx[i])
            expt.sort_idx[i] = np.append(expt.sort_idx[i], [-1]*N_to_pad).astype(int)

    def create_data_file(self,expt):

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
            # pad with [-1]s to allow saving in hdf5 (avoid staggered array)
            self.pad_sort_idx(expt)
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

    def _data_path(self,run_info,lite=False):
        this_data_dir = data_dir
        run_id_str = f"{str(run_info.run_id).zfill(7)}"
        expt_class = self._bytes_to_str(run_info.expt_class)
        datetime_str = self._bytes_to_str(run_info.run_datetime_str)
        if lite:
            run_id_str += "_lite"
            this_data_dir = os.path.join(data_dir,"_lite")
        filename = run_id_str + "_" + datetime_str + "_" + expt_class + ".hdf5"
        filepath_folder = os.path.join(this_data_dir,
                                       self._bytes_to_str(run_info.run_date_str))
        filepath = os.path.join(filepath_folder,filename)
        return filepath, filepath_folder

    def _update_run_id(self,run_info):
        update_run_id(run_info)

    def _get_rid(self):
        return get_run_id()
    
    def _bytes_to_str(self,attr):
        if isinstance(attr,bytes):
            attr = attr.decode("utf-8")
        return attr