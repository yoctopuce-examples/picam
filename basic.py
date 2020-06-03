from picamera import PiCamera
import datetime
from yoctopuce.yocto_api import *
from yoctopuce.yocto_weighscale import *


camera = PiCamera()

errmsg = YRefParam()

# Setup the API to use local USB devices
if YAPI.RegisterHub("usb", errmsg) != YAPI.SUCCESS:
    sys.exit("init error" + errmsg.value)

# retreive any genericSensor sensor
sensor = YWeighScale.FirstWeighScale()
if sensor is None:
    die('No Yocto-Bridge connected on USB')

# On startup, enable excitation and tare weigh scale
print("Resetting tare weight...");
sensor.set_excitation(YWeighScale.EXCITATION_AC);
YAPI.Sleep(3000);
sensor.tare();

unit = sensor.get_unit();

print("Main loop ready");
while sensor.isOnline():
    weight = sensor.get_currentValue()
    if weight > 5:
        print("Object on the scale take a 5s video of it");
        starttime = datetime.datetime.now().strftime("%H.%M.%S_%Y-%m-%d")
        video_file = "videos/" + starttime + ".h264"
        log_file = "videos/" + starttime + ".txt"
        camera.start_recording(video_file)
        with open(log_file, "a") as myfile:
            myfile.write("recording in " + video_file+"\n")
        count = 0
        while weight > 5 and count < 30:
            weight = sensor.get_currentValue()
            prefix = datetime.datetime.now().strftime("%H.%M.%S_%Y-%m-%d:")
            recmsg = "%scurrent weight=%d %s" % (prefix,weight, unit)
            camera.annotate_text = recmsg
            print(recmsg)
            with open(log_file, "a") as myfile:
                myfile.write(recmsg+"\n")
            count += 1
            YAPI.Sleep(1000)
        camera.stop_recording()
    YAPI.Sleep(100)

YAPI.FreeAPI()
