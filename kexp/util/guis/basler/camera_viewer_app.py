"""The Camera Viewer (beacon.camera.viewer.app) with this lab's "Copy
assignment line" wording installed. ``camera_viewer.bat`` runs this."""


def main() -> None:
    from kexp.util.guis.basler.assignment_line import install
    install()
    from beacon.camera.viewer.app import main as viewer_main
    viewer_main()


if __name__ == "__main__":
    main()
