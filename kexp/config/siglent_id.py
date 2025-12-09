from waxx.control.misc.sdg6000x import SDG6000X_CH

class siglent_frame():
    def __init__(self):
        IP_RY_CAVITY_SIGLENT = "192.168.1.101"
        self.siglent_405 = SDG6000X_CH(0,IP_RY_CAVITY_SIGLENT)
        self.siglent_980 = SDG6000X_CH(1,IP_RY_CAVITY_SIGLENT)