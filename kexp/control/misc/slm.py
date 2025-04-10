class SLM():
    """Goal:
    A class to control the SLM. An object of this class will exist as an
    attribute of the experiment class (self.slm = SLM()). Then we can call SLM
    updates in line with experiment code with something like:
    

    self.slm.write_phase_spot(diameter = 200, phase = np.pi / 2, x_center
        = 100, y_center = 300)

    Break different elements into separate functions -- one to format a command,
    one to send a message to the SLM server, one that gets called by the command-line
    interface ("input" style), one that the user will call in experiments (like
    the "slm.write_phase_spot" example above).
    """    
    def __init__(self):
        self.ip = "192.168.1.102"

    def write_phase_spot(self,diameter,phase,x_center,y_center):
        command_str = self.format_phase_spot_slm_commmand(diameter,phase,x_center,y_center)
        self.send_command(command_str)

    def format_phase_spot_slm_commmand(self,diameter,phase,x_center,y_center):
        pass

    def send_command(self, command):
        pass