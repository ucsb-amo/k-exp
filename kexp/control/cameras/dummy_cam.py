import numpy as np

class DummyCamera():
    def __init__(self):
        pass

    def close(self):
        pass

    def Close(self):
        pass

    def is_opened(self):
        return False
    
    def start_grab(self) -> np.ndarray:
        return None
    
    def stop_grab(self):
        pass
    
    def open(self):
        pass

    def Open(self):
        pass