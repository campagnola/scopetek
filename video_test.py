import pyqtgraph as pg
from scopetek import Scopetek

# Initialize camera
cam = Scopetek()
# Set camera parameters
cam.setup(resolution=(640,480), fast=True, exposure=131e-3, gain=1)

imv = pg.image()

    
while True:
    frame = cam.readframe()
    rgb = cam.bayer_to_rgb(frame)
    imv.setImage(rgb.transpose(1, 0, 2))
    
    pg.QtGui.QApplication.processEvents()
    if not imv.isVisible():
        cam.stop()
        break
