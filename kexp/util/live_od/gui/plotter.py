from PyQt6.QtCore import QThread, pyqtSignal
from queue import Queue

class LiveODPlotter(QThread):
    plot_data_signal = pyqtSignal(object)
    def __init__(self, plotwindow, plotting_queue: Queue):
        super().__init__()
        self.plotwindow = plotwindow
        self.plotting_queue = plotting_queue
        self.plot_data_signal.connect(self.plotwindow.handle_plot_data)
    def run(self):
        while True:
            to_plot = self.plotting_queue.get()
            self.plot_data_signal.emit(to_plot)
