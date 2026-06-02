from kexp.config.ip import DATA_DIR
from waxa.browser import launch as launch_browser


def launch():
    return launch_browser(DATA_DIR)


if __name__ == "__main__":
    launch()
