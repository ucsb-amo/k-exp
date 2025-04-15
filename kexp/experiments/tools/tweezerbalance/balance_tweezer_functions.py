from kexp.control import BaslerUSB
from queue import Queue
import scipy as sp
from IPython.display import clear_output
import numpy as np
import matplotlib.pyplot as plt
import spcm
from spcm import units
from Set_VPID1_Expt_Builder import ExptBuilder



class TweezerBalancer():

    def __init__(self, box_size = [30,50], f_list = [76.e6, 80.e6], a_list = [0.1,0.1], 
                 percentage_error = [100.,100.], goal_error = 1., p_gain_constant = 2.e-8, v_pid1 = 6.):
        self.BOX_SIZE = box_size
        self.F_LIST = f_list
        self.A_LIST = a_list
        self.N_TWEEZERS = len(self.A_LIST)
        self.PERCENTAGE_ERROR = percentage_error
        self.GOAL_ERROR = goal_error
        self.P_GAIN_CONSTANT = p_gain_constant
        self.V_PID1 = v_pid1

        self.cam = ""
        self.queue = ""
        self.trigger = ""
        self.card = ""
        self.dds = ""
        self.core_list = ""

        self.basler_connect()
        self.awg_connect()
        
        self.init_tweezers(f_list = self.F_LIST, a_list = self.A_LIST)
        self.set_v_pid1(self.V_PID1)
        
    
    def basler_connect(self):
        #connect to xBasler
        self.cam = BaslerUSB(TriggerMode='Off',ExposureTime=0.000020,BaslerSerialNumber="40320384")
        self.queue_img = Queue()

    #connect to awg
    def awg_connect(self):

        ip = 'TCPIP::192.168.1.83::INSTR'

        self.card = spcm.Card(ip)

        self.card.open(ip)

        # setup self.card for DDS
        self.card.card_mode(spcm.SPC_REP_STD_DDS)

        # Setup the channels
        channels = spcm.Channels(self.card)
        print(len(channels))
        channels.enable(True)
        channels.output_load(50 * units.ohm)
        channels.amp(1. * units.V)
        self.card.write_setup()

        # trigger mode
        self.trigger = spcm.Trigger(self.card)
        self.trigger.or_mask(spcm.SPC_TMASK_EXT0) # disable default software trigger
        self.trigger.ext0_mode(spcm.SPC_TM_POS) # positive edge
        self.trigger.ext0_level0(1.5 * units.V) # Trigger level is 1.5 V (1500 mV)
        self.trigger.ext0_coupling(spcm.COUPLING_DC) # set DC coupling
        self.card.write_setup()

        # Setup DDS functionality
        self.dds = spcm.DDS(self.card, channels=channels)
        self.dds.reset()

        self.dds.trg_src(spcm.SPCM_DDS_TRG_SRC_CARD)

        self.core_list = [hex(2**n) for n in range(20)]

        # core_list = [spcm.SPCM_DDS_CORE8,  spcm.SPCM_DDS_CORE9,  spcm.SPCM_DDS_CORE10, spcm.SPCM_DDS_CORE11, spcm.SPCM_DDS_CORE20]

        # dds.cores_on_channel(1, *core_list)

        self.card.start(spcm.M2CMD_CARD_ENABLETRIGGER)
    
    def awg_disconnect(self):
        self.card.stop()

        self.card.close(self.card._handle)

    def basler_disconnect(self):
        self.cam.close()

    def update_params(self, box_size, f_list, a_list, 
                 percentage_error, goal_error, p_gain_constant, v_pid1):
        self.BOX_SIZE = box_size
        self.N_TWEEZERS = len(a_list)
        self.F_LIST = f_list
        self.A_LIST = a_list
        self.PERCENTAGE_ERROR = percentage_error
        self.GOAL_ERROR = goal_error
        self.P_GAIN_CONSTANT = p_gain_constant
        self.V_PID1 = v_pid1
        self.update_a_list_manual(a_list)
        self.set_v_pid1(self.V_PID1)
        self.init_tweezers(f_list = self.F_LIST, a_list = self.A_LIST)

    def update_test_params(self, box_size, f_list, a_list, v_pid1):
        self.BOX_SIZE = box_size
        self.N_TWEEZERS = len(a_list)
        self.F_LIST = f_list
        self.A_LIST = a_list
        self.V_PID1 = v_pid1
        self.update_a_list_manual(a_list)
        self.set_v_pid1(self.V_PID1)
        self.init_tweezers(f_list = self.F_LIST, a_list = self.A_LIST)

    def update_f_list(self, f_list):
        self.F_LIST = f_list
        self.init_tweezers(f_list = self.F_LIST, a_list = self.A_LIST)

    # def update_a_list(self, a_list):
    #     self.A_LIST = a_list
    #     self.init_tweezers(f_list = self.F_LIST, a_list = self.A_LIST)

    def update_box_size(self, box_size):
        self.BOX_SIZE = box_size

    def update_v_pid1(self,v_pid1):
        self.V_PID1 = v_pid1
        self.set_v_pid1(self.V_PID1)

    def grab_image(self):
        self.cam.start_grab(1, self.queue_img)
        image = self.queue_img.get()[0]
        return image


    def find_centers(self, image):
        centers = []

        #need to find centers based off an image
        image = np.array(image)

        #x is the horizontal axis while y is the vertical axis on the image
        image_sumx = np.sum(image, axis = 0)
        image_sumy = np.sum(image,axis = 1)

        # normalizing
        image_sumx = image_sumx/np.max(image_sumx)
        image_sumy = image_sumy/np.max(image_sumy)

        # plt.plot(image_sumx)
        # plt.show()

        xpeaks_idx = sp.signal.find_peaks(image_sumx, prominence=0.1, distance = 50)[0]

        # if not (len(xpeaks_idx) == N_TWEEZERS):
        #     xpeaks_idx.sort()
        #     xpeaks_idx = xpeaks_idx[:N_TWEEZERS]
        ypeaks_idx = [np.argmax(image_sumy)]*len(xpeaks_idx)


        # plt.imshow(image)
        # plt.scatter(xpeaks_idx,ypeaks_idx)

        for i in xpeaks_idx:
            centers.append([i,ypeaks_idx[0]])

        return centers

    def find_tweezer_rois(self, image, box_size):
        
        centers = self.find_centers(image)

        tweezer_rois = []

        for i in range(len(centers)):
            tweezer_rois.append([[centers[i][0]-box_size[0],centers[i][0]+box_size[0]],
                            [centers[i][1]-box_size[1],centers[i][1]+box_size[1]]])
            
        return tweezer_rois

    def check_if_saturated(self, image, tweezer_rois):
        saturated_pixels = 0
        for roi in tweezer_rois:
            for i in range(roi[1][0], roi[1][1]):
                for j in range(roi[0][0], roi[0][1]):
                    if image[i][j] == 255.:
                        saturated_pixels = saturated_pixels + 1
        return (saturated_pixels > 1)


    def sum_pixels(self, image, roi):
        total_count = 0
        for i in range(roi[1][0], roi[1][1]):
            for j in range(roi[0][0], roi[0][1]):
                total_count += image[i][j]
        return total_count

    #then find total pixel count in each, and then decrease to specified value (right now the mean of all of them)
    #tweezer pixel counts is the total number of pixels in each tweezer

    def get_error(self, image, tweezer_rois):
        tweezer_pixel_counts = [0]*self.N_TWEEZERS

        for i in range(len(tweezer_rois)):
            tweezer_pixel_counts[i] = self.sum_pixels(image, tweezer_rois[i])

        mean_pixel_counts = sum(tweezer_pixel_counts)/len(tweezer_pixel_counts)

        pixel_differences = np.array(tweezer_pixel_counts) - np.array([mean_pixel_counts]*len(tweezer_pixel_counts))

        # pixel_differences = np.array(tweezer_pixel_counts) - np.array([MEAN_PIXELS]*len(tweezer_pixel_counts))

        percentage_error = 100*pixel_differences/tweezer_pixel_counts

        print("tweezer total pixel counts:", tweezer_pixel_counts)
        print("mean pixels:", mean_pixel_counts)
        print("difference in pixels from the mean:", pixel_differences)
        print("percentage error:", percentage_error)

        return [percentage_error, pixel_differences]

    def get_mean_pixels(self,image,tweezer_rois):
        tweezer_pixel_counts = [0]*self.N_TWEEZERS

        for i in range(len(tweezer_rois)):
            tweezer_pixel_counts[i] = self.sum_pixels(image, tweezer_rois[i])

        mean_pixel_counts = sum(tweezer_pixel_counts)/len(tweezer_pixel_counts)

        return mean_pixel_counts

    def update_a_list(self, pixel_differences, tweezer_order):

        sorted_pixel_differences = [0.]*len(pixel_differences)
        for i in range(len(pixel_differences)):
            sorted_pixel_differences[tweezer_order[i]] = pixel_differences[i]
        new_a_list = self.A_LIST - self.P_GAIN_CONSTANT* np.array(sorted_pixel_differences)
        self.A_LIST = new_a_list
        return new_a_list

    def update_a_list_inorder(self, pixel_differences):
        new_a_list = self.A_LIST - self.P_GAIN_CONSTANT* np.array(pixel_differences)
        self.A_LIST = new_a_list
        return new_a_list

    def update_a_list_manual(self, new_a_list_unsorted):
        tweezer_order = self.get_tweezer_order()
        new_a_list_sorted = [0.]*len(new_a_list_unsorted)
        for i in range(len(new_a_list_unsorted)):
            new_a_list_sorted[tweezer_order[i]] = new_a_list_unsorted[i]
        new_a_list = new_a_list_sorted
        self.A_LIST = new_a_list
        return new_a_list

    def normalize_a_list(self):
        total_amp = sum(self.A_LIST)
        normalized_a_list = [0.]*len(self.A_LIST)
        if total_amp == 1:
            pass
        else:
            for i in range(len(self.A_LIST)):
                normalized_a_list[i] = self.A_LIST[i]/total_amp

        return normalized_a_list

    def compute_tweezer_1064_phases(self):
        phase_tweezer_array = np.empty([self.N_TWEEZERS])
        for tweezer_idx in range(self.N_TWEEZERS):
            if tweezer_idx == 0:
                phase_tweezer_array[0] = 360
            else:
                phase_ij = 0
                for j in range(1,tweezer_idx):
                    phase_ij = phase_ij + 2*np.pi*(tweezer_idx - j)*self.A_LIST[tweezer_idx]
                phase_i = (phase_ij % 2*np.pi) * 360
                phase_tweezer_array[tweezer_idx] = phase_i
        return phase_tweezer_array

    #initializes tweezers

    def init_tweezers(self, f_list, a_list):
        phases = self.compute_tweezer_1064_phases()
        for tweezer_idx in range(len(self.core_list)):
            if tweezer_idx < len(f_list):
                self.dds[tweezer_idx].amp(a_list[tweezer_idx])
                self.dds[tweezer_idx].freq(f_list[tweezer_idx])
                self.dds[tweezer_idx].phase(phases[tweezer_idx])
            else:
                self.dds[tweezer_idx].amp(0.)
        self.dds.exec_at_trg()
        self.dds.write_to_card()
        self.trigger.force()
        
    def plot_tweezer_rois(self, image, tweezer_rois):
        plt.imshow(image)
        for i in range(len(tweezer_rois)):
            plt.vlines(tweezer_rois[i][0][0],ymin=tweezer_rois[i][1][0],ymax=tweezer_rois[i][1][1])
            plt.vlines(tweezer_rois[i][0][1],ymin=tweezer_rois[i][1][0],ymax=tweezer_rois[i][1][1])
            plt.hlines(tweezer_rois[i][1][0],xmin=tweezer_rois[i][0][0],xmax=tweezer_rois[i][0][1])
            plt.hlines(tweezer_rois[i][1][1],xmin=tweezer_rois[i][0][0],xmax=tweezer_rois[i][0][1])

    #write code to turn on each tweezer individually, check its x position, and put that scrambled into an array

    def get_tweezer_order(self, amplitude = 0.1):
        tweezer_xcenters = []

        for i in self.F_LIST:
            self.init_tweezers([i], [amplitude])
            image = self.grab_image()
            center = self.find_centers(image)
            # print(center)
            tweezer_xcenters.append(center[0][0])
            # plt.imshow(image)
            # plt.show()
            
        tweezer_order = np.argsort(tweezer_xcenters)
        print(tweezer_xcenters)
        return tweezer_order
    

    def unsaturate_pixels(self):
        image = self.grab_image()
        tweezer_rois = self.find_tweezer_rois(image, self.BOX_SIZE)
        while (self.check_if_saturated(image, tweezer_rois)):
            if self.V_PID1 < 0.25:
                self.V_PID1 = self.V_PID1 - 0.01
            else: 
                self.V_PID1 = self.V_PID1 - 0.1
            self.set_v_pid1(self.V_PID1)
            image = self.grab_image()
            tweezer_rois = self.find_tweezer_rois(image, self.BOX_SIZE)
            clear_output()
            plt.imshow(image)
            plt.show()
        self.V_PID1 = self.V_PID1
        self.set_v_pid1(self.V_PID1)
        return self.V_PID1

    def set_v_pid1(self,v_pid1):
        eBuilder =  ExptBuilder()
        eBuilder.write_experiment_to_file(eBuilder.set_dac_expt(v_pid1))
        eBuilder.run_expt()
