from pypylon import pylon

class BaslerUSB(pylon.InstantCamera):
    '''
    BaslerUSB is an InstantCamera object which initializes the connected Basler camera.
    Excercise caution if multiple cameras are connected.

    Args:
        ExposureTime (float): the exposure time in us. If below the minimum for the connected camera, sets to minimum value. (default: 0.)
        TriggerSource (str): picks the line that the camera triggers on. (default: 'Line1')
        TriggerMode (str): picks whether or not the camera waits for a trigger to capture frames. (default: 'On')
    '''
    def __init__(self,ExposureTime=0.,TriggerSource='Line1',TriggerMode='On'):
        super().__init__()

        tl_factory = pylon.TlFactory.GetInstance()
        self.Attach(tl_factory.CreateFirstDevice())

        self.Open()
        self.TriggerSource.SetValue(TriggerSource)
        self.TriggerMode.SetValue(TriggerMode)
        if ExposureTime < self.ExposureTime.GetMin():
            ExposureTime = self.ExposureTime.GetMin()
        self.ExposureTime.SetValue(ExposureTime)
        self.Close()

    def grab_N_images(self,N=1,timeout_us=5000):
        '''Grabs N images from the camera, then closes the camera connection.
        
        Args:
            N (int): the number of frames to be grabbed from the buffer. (default: 1)
            timeout_us (int): The time in microseconds to wait before throwing a timeout exception. (default: 5000)
        '''
        images = []
        self.StartGrabbing(pylon.GrabStrategy_OneByOne)
        count = 0
        while self.IsGrabbing():
            grab = self.RetrieveResult(timeout_us,pylon.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                img = grab.GetArray()
                images.append(img)
                count += 1
            grab.Release()
            if count >= N:
                break
        self.cam.Close()
        return images
        
        
        
