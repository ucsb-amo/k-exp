class SLM():
    """Goal:
    A class to control the SLM. An object of this class will exist as an
    attribute of the experiment class (self.slm = SLM()). Then we can call SLM
    updates in line with experiment code with something like:
    

    self.slm.write_phase_spot(diameter = 200, phase = np.pi / 2, x_center
        = 100, y_center = 300)

    Break different elements into separate functions -- one to format and send a
    message to the SLM server, one that gets called by the command-line
    interface ("input" style), one that the user will call in experiments (like
    the "slm.write_phase_spot" example above).
    """    
    def __init__(self):
        self.ip = "192.168.1.102"