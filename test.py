"""
https://github.com/JohnDMcMaster/uvscada/tree/master/scopetek
https://github.com/walac/pyusb/blob/master/docs/tutorial.rst



"""

import sys
import usb.core
dev = usb.core.find(idVendor=0x547)
if dev is None:
    print "No cameras found!"
    sys.exit(-1)

cfg = dev[0]
iface = cfg[(0,0)]
ep = iface[0]


permission_error_msg = """Permission denied to access camera.

To fix this on Linux:
1. Edit /etc/udev/rules.d/50-scopetek.rules, add the following (you may need to choose a different group):
     SUBSYSTEMS=="usb", ATTRS{idVendor}=="0547", GROUP="plugdev", MODE="0666"
2. Restart udev:
     sudo udevadm control --reload
3. Unplug/replug the device and try again.
"""

try:
    cfg.set()
except usb.core.USBError as err:
    if err.errno == 13:
        print permission_error_msg
        sys.exit(-1)


