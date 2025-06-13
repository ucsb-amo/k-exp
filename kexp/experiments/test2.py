import inspect
import os

class Parent:
    def get_filepath(self):
        # Returns the file path where the class is defined
        return os.path.abspath(inspect.getfile(self.__class__))
    
    def analyze(self):
        print(self.get_filepath())