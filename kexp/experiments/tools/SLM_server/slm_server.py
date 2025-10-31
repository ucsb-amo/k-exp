import ctypes
from ctypes import *
import numpy as np
from PIL import Image
import time
import matplotlib.pyplot as plt

slm_lib = None
width, height = 1920, 1200  # Default values; updated after initialization
is_eight_bit_image = c_uint(1)

phase_LUT_PATH = r"C:\Program Files\Meadowlark Optics\Blink 1920 HDMI\LUT Files\phase_to_gray.txt"
data = np.loadtxt(phase_LUT_PATH)
phase_values = data[:, 1]  
gray_levels = data[:, 0] 


class SLM_server():

    def __init__(self):
        # self.LUT_PATH = r"C:\Program Files\Meadowlark Optics\Blink 1920 HDMI\LUT Files\phase_to_gray.txt"
        # self.phase_values, self.gray_levels = self.load_phase_to_gray_lut(self.LUT_PATH)
        self.slm_initialized = False  # Track whether SLM is initialized

    # def load_phase_to_gray_lut(self, lut_path):
    #     try:
    #         data = np.loadtxt(lut_path)
    #         phase_values = data[:, 0]  # First column
    #         gray_levels = data[:, 1]   # Second column
    #         return phase_values, gray_levels
    #     except Exception as e:
    #         print(f"Error reading LUT file: {e}")
    #         exit()
    def phase2gray(self,phase):

        closest_index = np.abs(phase_values - phase).argmin()
        mapped_gray_value = int(gray_levels[closest_index])
        print(f"Phase {phase}pi is mapped to gray level {mapped_gray_value}")

        return mapped_gray_value
    
    def generate_mask(self, dimension, phase, center_x, center_y, grating_spacing = 10, angle_deg=0, mask = 1):
        if mask == 1:
            self.mask_type = 'spot'
         
            return self.generate_spot_mask(dimension, phase, center_x, center_y)
        elif mask == 2:
            self.mask_type = 'grating'
            return self.generate_grating_mask(dimension, phase, center_x, center_y, grating_spacing, angle_deg)
        elif mask == 3:
            self.mask_type = 'cross'
            return self.generate_cross_mask(dimension, phase, center_x, center_y)
        else:
            print(f"Unknown mask type: {mask}")
            return self.generate_cross_mask(0, 0, center_x, center_y)

    # LUT Mapping
    def generate_spot_mask(self, dimension, phase, center_x, center_y):

        global width, height
        radius = dimension // 2

        mapped_gray_value = self.phase2gray(phase)

        image = np.full((height, width), 0, dtype=np.uint8)

        # center_x, center_y = width // 2, height // 2
        y, x = np.ogrid[:height, :width]
        distance_from_center = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
        mask = distance_from_center <= radius
        image[mask] = mapped_gray_value

        return image
    
    def generate_grating_mask(self, dimension, phase, center_x, center_y, grating_spacing=10):
        period = grating_spacing
        filling_factor = 0.5

        mapped_gray_value = self.phase2gray(phase)

        image = np.full((height, width), 0, dtype=np.uint8)

        half_length = dimension // 2
        x_start = max(center_x - half_length, 0)
        x_end = min(center_x + half_length, width)
        y_start = max(center_y - half_length, 0)
        y_end = min(center_y + half_length, height)

        for x in range(x_start, x_end):
            position_in_period = (x - x_start) % period
            if position_in_period < period * filling_factor:
                image[y_start:y_end, x] = mapped_gray_value

        return image

    def generate_grating_mask(self, dimension, phase, center_x, center_y,
                            grating_spacing=10, angle_deg=0):
        period = grating_spacing
        filling_factor = 0.5
        mapped_gray_value = self.phase2gray(phase)


        image = np.zeros((height, width), dtype=np.uint8)

        half = dimension // 2
        x_start = max(center_x - half, 0)
        x_end   = min(center_x + half, width)
        y_start = max(center_y - half, 0)
        y_end   = min(center_y + half, height)

        # coordinate grid over the ROI
        xs = np.arange(x_start, x_end)
        ys = np.arange(y_start, y_end)
        xx, yy = np.meshgrid(xs, ys)

        # rotation 
        theta = np.deg2rad(angle_deg)
        c, s = np.cos(theta), np.sin(theta)

        # project onto the variation axis 
     
        proj = (xx - center_x) * c + (yy - center_y) * s

        mask = (np.mod(proj, period) < period * filling_factor)

        roi = image[y_start:y_end, x_start:x_end]
        roi[mask] = mapped_gray_value
        image[y_start:y_end, x_start:x_end] = roi

        return image

    def generate_cross_mask(self, dimension, phase, center_x, center_y):
        global width, height
        arm_length = 200* dimension

        mapped_gray_value = self.phase2gray(phase)

        image = np.full((height, width), 0, dtype=np.uint8)

        x_start = max(center_x - arm_length // 2, 0)
        x_end = min(center_x + arm_length // 2, width)
        y_start_h = max(center_y - dimension // 2, 0)
        y_end_h = min(center_y + dimension // 2, height)
        image[y_start_h:y_end_h, x_start:x_end] = mapped_gray_value

        y_start = max(center_y - arm_length // 2, 0)
        y_end = min(center_y + arm_length // 2, height)
        x_start_v = max(center_x - dimension // 2, 0)
        x_end_v = min(center_x + dimension // 2, width)
        image[y_start:y_end, x_start_v:x_end_v] = mapped_gray_value

        return image

    # SLM Initializing function
    def initialize_slm(self):
        global slm_lib, width, height, is_eight_bit_image

        if self.slm_initialized:
            return  # Skip re-initialization if already done

        awareness = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except AttributeError:
            pass  

        #  Load Meadowlark SDK
        if slm_lib is None:
            cdll.LoadLibrary("C:\\Program Files\\Meadowlark Optics\\Blink 1920 HDMI\\SDK\\Blink_C_wrapper")
            slm_lib = CDLL("Blink_C_wrapper")

        # Define function prototypes
        slm_lib.Create_SDK.argtypes = []
        slm_lib.Create_SDK.restype = None

        slm_lib.Get_Height.argtypes = []
        slm_lib.Get_Height.restype = c_uint

        slm_lib.Get_Width.argtypes = []
        slm_lib.Get_Width.restype = c_uint

        slm_lib.Get_Depth.argtypes = []
        slm_lib.Get_Depth.restype = c_uint

        slm_lib.Load_lut.argtypes = [c_char_p]
        slm_lib.Load_lut.restype = c_int

        slm_lib.Write_image.argtypes = [POINTER(c_ubyte), c_uint]
        slm_lib.Write_image.restype = None

        slm_lib.Delete_SDK.argtypes = []
        slm_lib.Delete_SDK.restype = None

        #  Initialize the SDK & Retrieve SLM Info
        slm_lib.Delete_SDK()  # Ensure no previous instance is running
        slm_lib.Create_SDK()
        print("Blink SDK was successfully initialized.")

        height = slm_lib.Get_Height()
        width = slm_lib.Get_Width()
        print(f"SLM Width: {width}, Height: {height}")

        #  Load the LUT 
        LUT_PATH = r"C:\Program Files\Meadowlark Optics\Blink 1920 HDMI\LUT Files\19x12_8bit_linearVoltage.lut"
        load_success = slm_lib.Load_lut(LUT_PATH.encode('utf-8'))

        if load_success > 0:
            print("LUT Loaded Successfully.")
        else:
            print("Error: Failed to load LUT!")
            slm_lib.Delete_SDK()
            exit()

        #  Clear the SLM Before Uploading Image
        clear_pattern = np.zeros((height * width), dtype=np.uint8)
        slm_lib.Write_image(clear_pattern.ctypes.data_as(POINTER(c_ubyte)), is_eight_bit_image)
        print("SLM Cleared to Blank Pattern.")
        time.sleep(1)

        self.slm_initialized = True  # Mark as initialized


    #  Function to Upload function
    def upload_to_slm(self,image):
        global slm_lib, width, height, is_eight_bit_image
        
        # #  Ensure SLM is initialized before first use
        # if not self.slm_initialized:
        #     print("SLM not initialized. Initializing now...")
        #     # self.initialize_slm()
        # else: 
        #     print("SLM has initialized")

        #  Load and Prepare the Image
        if isinstance(image, str):
            img = Image.open(image) # Load image from file path
        else:
            img = Image.fromarray(image) # Use the NumPy array directly

        # Ensure image is in grayscale ('L' mode)
        if img.mode != 'L':
            img = img.convert('L')

        img_data = np.array(img, dtype=np.uint8).ravel()


        # Upload image to SLM
        time.sleep(1) 
        slm_lib.Write_image(img_data.ctypes.data_as(POINTER(c_ubyte)), is_eight_bit_image)
        print("Image successfully uploaded to SLM.")

        # Plot the image for checking
        # plt.imshow(img_data.reshape((height, width)), cmap='gray', vmin=0, vmax=255)
        # plt.axis('off')
        # plt.show()

    def fast_upload_to_slm(self,image):
            global slm_lib, width, height, is_eight_bit_image

            if isinstance(image, str):
                img = Image.open(image) 
            else:
                img = Image.fromarray(image) 

            if img.mode != 'L':
                img = img.convert('L')

            img_data = np.array(img, dtype=np.uint8).ravel()

            slm_lib.Write_image(img_data.ctypes.data_as(POINTER(c_ubyte)), is_eight_bit_image)




