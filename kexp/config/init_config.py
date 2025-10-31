db = True

class InitConfig():
    def __init__(self):
        self.print_runid = True
        self.setup_camera = True

        self.init_dac = True
        
        self.init_dds = True
        self.dds_default = True
        self.dds_off = True
        self.beat_ref_on = True
        self.init_img = True

        self.init_shuttler = True
        self.init_lightsheet = True

        self.setup_awg = True
        self.setup_slm = True

    def update_values(self,
                      print_runid=db,
                      setup_camera=db,
                      init_dac=db,
                      init_dds=db,
                      dds_default=db,
                      dds_off=db,
                      beat_ref_on=db,
                      init_img=db,
                      init_shuttler=db,
                      init_lightsheet=db,
                      setup_awg=db,
                      setup_slm=db):
        if print_runid != (self.print_runid == db):
            self.print_runid = print_runid
        if setup_camera != (self.setup_camera == db):
            self.setup_camera = setup_camera
        if init_dac != (self.init_dac == db):
            self.init_dac = init_dac
        if init_dds != (self.init_dds == db):
            self.init_dds = init_dds
        if dds_default != (self.dds_default == db):
            self.dds_default = dds_default
        if dds_off != (self.dds_off == db):
            self.dds_off = dds_off
        if beat_ref_on != (self.beat_ref_on == db):
            self.beat_ref_on = beat_ref_on
        if init_img != (self.init_img == db):
            self.init_img = init_img
        if init_shuttler != (self.init_shuttler == db):
            self.init_shuttler = init_shuttler
        if init_lightsheet != (self.init_lightsheet == db):
            self.init_lightsheet = init_lightsheet
        if setup_awg != (self.setup_awg == db):
            self.setup_awg = setup_awg
        if setup_slm != (self.setup_slm == db):
            self.setup_slm = setup_slm

    def minimal_start(self):
        