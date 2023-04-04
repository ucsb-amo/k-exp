from kexp.util.data.data_vault import DataSaver
import time

class RunInfo():
    def __init__(self,expt_obj=None):
        _ds = DataSaver()
        self.run_id = _ds._get_rid()
        self.run_datetime = time.localtime(time.time())
        self.filepath = []
        if expt_obj not None:
            expt_class = expt_obj.__class__.__name__
        else:
            expt_class = "expt"
            