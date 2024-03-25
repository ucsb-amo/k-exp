from kexp.util.data.data_vault import DataSaver
import time

class RunInfo():
    def __init__(self,expt_obj=None,save_data=True):
        _ds = DataSaver()
        self.run_id = _ds._get_rid()
        self.run_datetime = time.localtime(time.time())

        self._run_description = ""

        date = self.run_datetime
        
        self.run_date_str = time.strftime("%Y-%m-%d", date)
        self.run_datetime_str = time.strftime("%Y-%m-%d_%H-%M-%S", date)

        self.filepath = []
        self.experiment_filepath = []
        self.xvarnames = []

        self.absorption_image = True
        
        self.save_data = int(save_data)

        if expt_obj is not None:
            self.expt_class = expt_obj.__class__.__name__
        else:
            self.expt_class = "expt"
            