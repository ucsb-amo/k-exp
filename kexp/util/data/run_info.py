import time
from kexp.util.data.server_talk import get_run_id

from kexp.config.camera_id import img_types as img

class RunInfo():
    def __init__(self,expt_obj=None,save_data=True):
        if expt_obj != None:
            self.run_id = get_run_id()
            print(f'Run id: {self.run_id}')
        else:
            self.run_id = 0
        self.run_datetime = time.localtime(time.time())

        self._run_description = ""

        date = self.run_datetime
        
        self.run_date_str = time.strftime("%Y-%m-%d", date)
        self.run_datetime_str = time.strftime("%Y-%m-%d_%H-%M-%S", date)

        self.filepath = []
        self.experiment_filepath = []
        self.xvarnames = []

        self.imaging_type = img.ABSORPTION
        
        self.save_data = int(save_data)

        if expt_obj is not None:
            self.expt_class = expt_obj.__class__.__name__
        else:
            self.expt_class = "expt"
            