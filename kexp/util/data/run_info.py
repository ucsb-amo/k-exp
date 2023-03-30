from kexp.util.data.data_vault import DataSaver
import time

class RunInfo():
    def __init__(self):
        _ds = DataSaver()
        self.run_id = _ds._get_rid()
        self.run_datetime = time.localtime(time.time())
        self.filepath = []