from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QPlainTextEdit, QComboBox, QSizePolicy)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QIcon, QFont
from queue import Queue
import numpy as np
from kexp.analysis.image_processing import compute_ODs

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

class Analyzer():
    def __init__(self):
        self.imgs = []
        self.crop_type = 'gm'

    def got_img(self,img):
        self.imgs.append(np.asarray(img))
        if len(self.imgs) == 3:
            self.analyze()
            self.imgs = []

    def analyze(self):
        self.img_atoms = self.imgs[0]
        self.img_light = self.imgs[1]
        self.img_dark = self.imgs[2]

        self.fix_datatype()

        self.od_raw, self.od, self.sum_od_x, self.sum_od_y = \
            compute_ODs(self.img_atoms,
                        self.img_light,
                        self.img_dark,
                        self.crop_type)
        self.od_raw = self.od_raw[0]
        self.od = self.od[0]
        self.sum_od_x = self.sum_od_x[0]
        self.sum_od_y = self.sum_od_y[0]

    def fix_datatype(self):
        dtype = self.img_atoms.dtype
        if dtype == np.dtype('uint8'):
            self.img_atoms = self.img_atoms.astype(np.int16)
            self.img_light = self.img_light.astype(np.int16)
            self.img_dark = self.img_dark.astype(np.int16)
        elif dtype == np.dtype('uint16'):
            self.img_atoms = self.img_atoms.astype(np.int32)
            self.img_light = self.img_light.astype(np.int32)
            self.img_dark = self.img_dark.astype(np.int32)

class ODviewer(QWidget):
    def __init__(self):
        super().__init__()
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
    
    def setup_layout(self):
        
        self.img_atoms_plot.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.img_light_plot.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.img_dark_plot.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.od_plot.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.sum_od_y_plot.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Minimum)
        self.sum_od_x_plot.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Minimum)

        self.layout = QVBoxLayout()

        images = QHBoxLayout()
        images.addWidget(self.img_atoms_plot)
        images.addWidget(self.img_light_plot)
        images.addWidget(self.img_dark_plot)
        # images.setStretch(0,0)
        self.layout.addLayout(images)

        OD_grid = QGridLayout()
        OD_grid.addWidget(self.od_plot,0,1,3,3)
        OD_grid.addWidget(self.sum_od_y_plot,0,4,3,1)
        OD_grid.addWidget(self.sum_od_x_plot,4,1,1,3)
        self.layout.addLayout(OD_grid)

        self.setLayout(self.layout)
        IMG_SIZE = 250
        OD_SIZE = 600
        self.img_atoms_plot.setFixedSize(IMG_SIZE,IMG_SIZE)
        self.img_light_plot.setFixedSize(IMG_SIZE,IMG_SIZE)
        self.img_dark_plot.setFixedSize(IMG_SIZE,IMG_SIZE)
        self.od_plot.setFixedSize(OD_SIZE,OD_SIZE)
        self.sum_od_y_plot.setFixedHeight(self.od_plot.height())
        self.sum_od_y_plot.setFixedWidth(150)
        self.sum_od_x_plot.setFixedWidth(self.od_plot.width())
        self.sum_od_x_plot.setFixedHeight(150)

class Plotter(QThread):
    def __init__(self,plotwindow:ODviewer,analyzer:Analyzer):
        super().__init__()
        self.plotwindow = plotwindow
        self.analyzer = analyzer

    def run(self):
        self.plotwindow.img_atoms_plot.plot(self.analyzer.img_atoms)
        self.plotwindow.img_light_plot.plot(self.analyzer.img_light)
        self.plotwindow.img_dark_plot.plot(self.analyzer.img_dark)
        self.plotwindow.od_plot.plot(self.analyzer.od)
        self.plotwindow.sum_od_x_plot.plot(self.analyzer.sum_od_x)
        self.plotwindow.sum_od_y_plot.plot(self.analyzer.sum_od_y)

    def clear(self):
        for k in vars(self.plotwindow).keys():
            obj = vars(self.plotwindow)[k]
            if issubclass(type(obj),PlotPanel):
                obj.clear()

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
        self.ydatalim = 0

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
    def plot(self,img):
        if self._plot_ref == None:
            self._plot_ref = self.axes.imshow(img)
            self.set_labels()
        else:
            self._plot_ref.set_data(img)
        self.draw()

class LinePlotPanel(PlotPanel):
    def plot(self,ydata):
        if self._plot_ref == None:
            self._plot_ref, = self.axes.plot(ydata)
            self.set_labels()
        else:
            self._plot_ref.set_ydata(ydata)
        self.fix_ylim(ydata)
        self.draw()

class RotatedLinePlotPanel(PlotPanel):
    def plot(self,ydata):
        xdata = np.arange(len(ydata))
        if self._plot_ref == None:
            self._plot_ref, = self.axes.plot(np.flip(ydata),xdata)
            self.set_labels()
        else:
            self._plot_ref.set_data(np.flip(ydata),xdata)
        self.fix_ylim(ydata,flip_axes=True)
        self.draw()