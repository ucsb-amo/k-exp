from PyQt6.QtCore import QThread, pyqtSignal
from queue import Queue, Empty

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
            # Drain any backlog so we always render the most recent frame.
            # Prevents latency accumulation when the GUI/GPU can't keep up
            # with the publish rate.
            while True:
                try:
                    to_plot = self.plotting_queue.get_nowait()
                except Empty:
                    break
            self.plot_data_signal.emit(to_plot)
