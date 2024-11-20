from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
      QPushButton, QPlainTextEdit, QComboBox, QSizePolicy, QDoubleSpinBox,
      QSpinBox)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QIcon, QFont
from queue import Queue
import numpy as np
from kexp.analysis.image_processing import compute_OD, process_ODs

import matplotlib
import matplotlib.pyplot as plt
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

dv = -100.

class Analyzer(QObject):

    analyzed = pyqtSignal()

    def __init__(self,plotting_queue:Queue):
        super().__init__()
        self.imgs = []
        self.plotting_queue = plotting_queue
        self.roi = []

    def get_img_number(self,N_img,N_shots,N_pwa_per_shot):
        self.N_img = N_img
        self.N_shots = N_shots
        self.N_pwa_per_shot = N_pwa_per_shot

    def get_analysis_type(self,absorption_image_bool):
        self.absorption_image = absorption_image_bool

    def got_img(self,img):
        self.imgs.append(np.asarray(img))
        if len(self.imgs) == (self.N_pwa_per_shot+2):
            self.analyze()
            self.imgs = []

    def analyze(self):
        self.img_atoms = self.imgs[0]
        self.img_light = self.imgs[self.N_pwa_per_shot]
        self.img_dark = self.imgs[self.N_pwa_per_shot+1]

        self.od_raw = compute_OD(self.img_atoms,
                        self.img_light,
                        self.img_dark,
                        abs_image_bool=self.absorption_image)
        self.od_raw = np.array([self.od_raw])
        self.od, self.sum_od_x, self.sum_od_y = \
            process_ODs(self.od_raw,self.roi)
        self.od_raw = self.od_raw[0]
        self.od = self.od[0]
        self.sum_od_x = self.sum_od_x[0]
        self.sum_od_y = self.sum_od_y[0]

        self.analyzed.emit()
        self.plotting_queue.put((self.img_atoms,
                           self.img_light,
                           self.img_dark,
                           self.od,
                           self.sum_od_x,
                           self.sum_od_y))

class ODviewer(QWidget):
    def __init__(self):
        super().__init__()

        self.Nimg = 0

        self.setup_widgets()
        self.setup_layout()

    def setup_widgets(self):
        self.img_atoms_plot = ImgPlotPanel(title='Atoms + Light')
        self.img_light_plot = ImgPlotPanel(title='Light only')
        self.img_dark_plot = ImgPlotPanel(title='Dark')

        self.od_plot = ImgPlotPanel(title='OD')
        self.sum_od_x_plot = LinePlotPanel(hlabel='Position (pixels)',
                                           vlabel='Integrated OD',
                                           title='y-integrated OD (sum_od_x)')
        self.sum_od_y_plot = RotatedLinePlotPanel(vlabel='Position (pixels)',
                                                  hlabel='Integrated OD',
                                                  title='x-integrated OD (sum_od_y)')
        
        self.max_OD_spinner = QDoubleSpinBox()
        self.max_OD_spinner_label = QLabel("Max OD")
        self.max_OD_spinner.setValue(2.0)
        self.max_OD_spinner.setMinimum(0.)
        self.max_OD_spinner.setSingleStep(0.1)

        self.min_OD_spinner = QDoubleSpinBox()
        self.min_OD_spinner_label = QLabel("Min OD")
        self.min_OD_spinner.setMinimum(0.)
        self.min_OD_spinner.setSingleStep(0.1)

        self.image_count_label = QLabel(f"Image Count: / {self.Nimg} ")
        self.clear_axes_button = QPushButton("Clear Axes")
    
    def setup_layout(self):
        
        # self.img_atoms_plot.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        # self.img_light_plot.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        # self.img_dark_plot.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.image_count_label.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.od_plot.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.sum_od_y_plot.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Minimum)
        self.sum_od_x_plot.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Minimum)

        self.layout = QVBoxLayout()
        
        images = QHBoxLayout()
        images.addWidget(self.img_atoms_plot)
        images.addWidget(self.img_light_plot)
        images.addWidget(self.img_dark_plot)

        self.image_count_label.setFixedWidth(200)
        self.clear_axes_button.setFixedWidth(200)
        top_row_corner = QVBoxLayout()
        top_row_corner.addWidget(self.image_count_label)
        top_row_corner.addWidget(self.clear_axes_button)

        top_row = QHBoxLayout()
        top_row.addLayout(images)
        top_row.addLayout(top_row_corner)
        self.layout.addLayout(top_row)

        max_spinner_layout = QHBoxLayout()
        max_spinner_layout.addWidget(self.max_OD_spinner)
        max_spinner_layout.addWidget(self.max_OD_spinner_label)

        min_spinner_layout = QHBoxLayout()
        min_spinner_layout.addWidget(self.min_OD_spinner)
        min_spinner_layout.addWidget(self.min_OD_spinner_label)

        spinner_layout = QVBoxLayout()
        spinner_layout.addLayout(max_spinner_layout)
        spinner_layout.addLayout(min_spinner_layout)

        OD_grid = QGridLayout()
        OD_grid.addWidget(self.od_plot,0,1,3,3)
        OD_grid.addWidget(self.sum_od_y_plot,0,4,3,1)
        OD_grid.addWidget(self.sum_od_x_plot,4,1,1,3)
        OD_grid.addLayout(spinner_layout,4,4,1,1)
        self.layout.addLayout(OD_grid)

        self.setLayout(self.layout)
        IMG_SIZE = 200
        OD_SIZE = 450
        self.od_plot.setMinimumHeight(10)
        self.od_plot.setMinimumWidth(10)
        self.img_atoms_plot.setFixedSize(IMG_SIZE,IMG_SIZE)
        self.img_light_plot.setFixedSize(IMG_SIZE,IMG_SIZE)
        self.img_dark_plot.setFixedSize(IMG_SIZE,IMG_SIZE)
        # self.od_plot.setFixedSize(OD_SIZE,OD_SIZE)
        self.sum_od_y_plot.setFixedHeight(self.od_plot.height())
        self.sum_od_y_plot.setFixedWidth(150)
        self.sum_od_x_plot.setFixedWidth(self.od_plot.width())
        self.sum_od_x_plot.setFixedHeight(150)

    def get_img_number(self,N_img,N_shots,N_pwa_per_shot):
        self.N_img = N_img
        self.N_shots = N_shots
        self.N_pwa_per_shot = N_pwa_per_shot

    def update_image_count(self,count):
        self.image_count_label.setText(f"Image count: {int(count)}/{int(self.Nimg)}")

class Plotter(QThread):
    def __init__(self,
                  plotwindow:ODviewer,
                  plotting_queue:Queue):
        super().__init__()
        self.plotwindow = plotwindow
        self.plotting_queue = plotting_queue

        self.plotwindow.clear_axes_button.clicked.connect(self.clear)

    def run(self):
        while True:
            to_plot = self.plotting_queue.get()
            self.img_atoms = to_plot[0]
            self.img_light = to_plot[1]
            self.img_dark = to_plot[2]
            self.od = to_plot[3]
            self.sum_od_x = to_plot[4]
            self.sum_od_y = to_plot[5]

            self.plotwindow.img_atoms_plot.plot(self.img_atoms)
            self.plotwindow.img_light_plot.plot(self.img_light)
            self.plotwindow.img_dark_plot.plot(self.img_dark)
            self.plotwindow.od_plot.plot(self.od,
                                         min_od=self.plotwindow.min_OD_spinner.value(),
                                         max_od=self.plotwindow.max_OD_spinner.value())
            self.plotwindow.sum_od_x_plot.plot(self.sum_od_x)
            self.plotwindow.sum_od_y_plot.plot(self.sum_od_y)

    def clear(self):
        for k in vars(self.plotwindow).keys():
            obj = vars(self.plotwindow)[k]
            if issubclass(type(obj),PlotPanel):
                obj.clear()
                obj.draw()

class AtomHistory(QWidget):
    def __init__(self):
        super().__init__()

class PlotPanel(FigureCanvasQTAgg,QWidget):
    def __init__(self,hlabel="",vlabel="",title="",height=0,width=0):
        super().__init__()
        fig = Figure()
        self.axes = fig.add_subplot(111)
        super(FigureCanvasQTAgg,self).__init__(fig)

        if height and (width==0):
            fig.set_figheight(height)
        if width and (height==0):
            fig.set_figwidth(width)
        if width and height:
            fig.set_figheight(height)
            fig.set_figwidth(width)

        self._plot_ref = None
        self.hlabel = hlabel
        self.vlabel = vlabel
        self.title = title
        self.ydatalim = 1.

    def clear(self):
        if self._plot_ref:
            self.axes.cla()
            self._plot_ref = None

    def set_labels(self):
        self.axes.set_title(self.title)
        self.axes.set_ylabel(self.vlabel)
        self.axes.set_xlabel(self.hlabel)

    def fix_ylim(self,ydata,flip_axes=False):
        self.ydatalim = np.max([self.ydatalim,np.max(ydata)])
        if not flip_axes:
            self.axes.set_ylim([0,self.ydatalim])
        else:
            self.axes.set_xlim([0,self.ydatalim])

class ImgPlotPanel(PlotPanel):
    def plot(self,img,max_od=dv,min_od=dv):
        try:
            if self._plot_ref == None:
                if max_od == dv and min_od == dv:
                    self._plot_ref = self.axes.imshow(img, origin='lower')
                else:
                    self._plot_ref = self.axes.imshow(img,vmin=min_od,vmax=max_od, origin='lower')
                self.set_labels()
            else:
                self._plot_ref.set_data(img)
                if not (max_od == dv and min_od == dv):
                    self._plot_ref.set_clim(vmin=min_od,vmax=max_od)

            self.draw()
        except Exception as e:
            print(e)

class LinePlotPanel(PlotPanel):
    def plot(self,ydata):
        try:
            if self._plot_ref == None:
                self._plot_ref, = self.axes.plot(ydata)
                self.set_labels()
            else:
                self._plot_ref.set_ydata(ydata)
            self.fix_ylim(ydata)
            self.draw()
        except Exception as e:
            print(e)

class RotatedLinePlotPanel(PlotPanel):
    def plot(self,ydata):
        try:
            xdata = np.arange(len(ydata))
            if self._plot_ref == None:
                self._plot_ref, = self.axes.plot(np.flip(ydata),xdata)
                self.set_labels()
            else:
                self._plot_ref.set_data(np.flip(ydata),xdata)
            self.fix_ylim(ydata,flip_axes=True)
            self.draw()
        except Exception as e:
            print(e)