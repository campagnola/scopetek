import pyqtgraph as pg
from scopetek import Scopetek, StreamThread

# Initialize camera
cam = Scopetek()
# Set camera parameters
cam.setup(resolution=(640,480), fast=True, exposure=30e-3, gain=1)
cam.auto_white_balance()

imv = pg.image()

stream = StreamThread(cam)
stream.start()

timer = pg.QtCore.QTimer()
def update():
    if not imv.isVisible():
        stream.stop()
        timer.stop()
        cam.stop()
        return
    
    # Empty out the entire queue; drop frames as needed.
    frames = stream.get_all()
    if len(frames) == 0:
        return
    
    imv.window().setWindowTitle('%0.1f FPS' % cam._fps)
    imv.setImage(frames[-1].image()[1:-1, 1:-2].transpose(1, 0, 2), autoRange=False)

        
timer.timeout.connect(update)
timer.start(30)
