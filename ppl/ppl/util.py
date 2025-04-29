from datetime import datetime

logActive = False

def ts_print(msg=""):
    global logActive
    if logActive:
        ts_str = datetime.strftime(datetime.now(), "%H:%M:%S")
        print(ts_str, msg)

def enableLog(enable):
    global logActive
    logActive = enable