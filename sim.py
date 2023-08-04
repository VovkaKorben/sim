
"""
ship mode
0 just wait stopped (second)
1 speed change (speed) - can be decreasing or increasing
2 rotate (angle)
"""
from datetime import datetime
import sys
import os
import json as j
# import nmea
import helpers
import random
import time
import math
import socket
import traceback

MODE_UDP = 1
MODE_TCP = 2


MODE = MODE_TCP
# IP = "192.168.1.4"
IP = "192.168.1.10"
# IP = "127.0.0.1"
PORT = 17777

DYNA_SHOW = False
USE_NETWORK = True

UPD_INTERVAL = 0.1 # in seconds
MSG1_DELAY = 2  # send msg type 1 each 3 seconds
MSG5_DELAY = 5  # send msg type 5 each 10 seconds

MAX_DIST = 300  # in meters
CENTER = (5.315458423270774,60.39705229794781)  # home
LON = 0
LAT = 1
PI = math.pi
PIM2 = math.pi*2
mode_descr = ["WAIT","SPEED","ROTATE"]


def to_polar(x, y):

    if x == 0:
        if y < 0:
            a = 270.0
        else:
            a = 90.0
    else:
        a = math.atan(y / x) / math.pi * 180.0
        if x < 0:
            a += 180.0
        elif y < 0:
            a += 360.0
    return [a, math.sqrt(x * x + y * y)]


def sign(a):
    if a > 0:
        return 1
    elif a < 0:
        return -1
    else:
        return 0


def at(x, y, text):
    sys.stdout.write("\x1b7\x1b[%d;%df%s\x1b8" % (x, y, text))
    sys.stdout.flush()


class fake_gps():
    def __init__(self):
        self.sat = []
        for satno in range(24):
            orb_index = satno // 4
            sat_on_orbit = satno % 4
            lon = orb_index * PI / 3
            lat = (orb_index % 3) * 2
            lat += orb_index // 3
            lat += sat_on_orbit*6
            lat = lat * PI / 12
            self.sat.append([lon, lat])
            print(f"{satno:>3}\t{lon:.3f}\t{lat:.3f}")
        pass

    def cycle(self, seconds: int):
        SPEED = PI / (6*60*60)  # radians per second
        for satno in range(24):
            self.sat[satno][LAT] += SPEED * seconds
            if self.sat[satno][LAT] >= PIM2:
                self.sat[satno][LAT] -= PIM2

    def get_sat(self, pos):

        result = []
        for satno in range(0, 24, 3):
            result.append({
                'prn': satno,
                'snr': 50,
                'elev': satno*22,
                'az': satno*11
            })
        return result

    def get_gsv(self):
        sat = self.get_sat(None)
        result = []

class ship():

    def __init__(self, json, limit):
        self.limit = limit
        self.own = json['own'] if 'own' in json else False
        self.mmsi = json['mmsi'] if 'mmsi' in json else 0
        self.shipname = json['shipname'] if 'shipname' in json else 'Unknown'
        self.maxspeed = json['maxspeed'] if 'maxspeed' in json else 'maxspeed'
        self.maxspeed *= 1000/60/60
        self.type = json['type'] if 'type' in json else 0
        self.x, self.y = random.randint(-self.limit, self.limit), random.randint(-self.limit, self.limit)
        self.angle, self.speed = random.uniform(0.0, 359.0), random.uniform(0.0, self.maxspeed)
        self.w = json['width'] if 'width' in json else 10
        self.h = json['height'] if 'height' in json else 3
        self.draught = json['draught'] if 'draught' in json else 2
        # some empiric values for evaluate accelerate
        # whan more weight ship - than slower it accelerate
        # mass = self.w * self.h * self.draught * 4
        mspeed = self.maxspeed / 60/60  # in m/s
        self._velocity = self.maxspeed / 100  # 1 / mass * mspeed * 1000
        self.mode, self.param_time, self.param_value = 0, 0, 0
        self.active = json['active'] if 'active' in json else 0
        # print(f"{self.shipname}\t{mass}\t{mspeed}\t{self._velocity}")
        
        # print(self.active)

    def cycle(self, seconds: int):
        done = False
        while not done:
            # timer counting at all, but values changes appropriate with mode
            used_seconds = min(self.param_time, seconds)
            self.param_time -= used_seconds
            seconds -= used_seconds

            if self.mode == 0:  # no action for `wait` command
                pass
            elif self.mode == 1:  # speed change
                self.speed += used_seconds * self.param_value
            elif self.mode == 2:  # rotate
                self.angle += used_seconds * self.param_value
                if self.angle < 0:
                    self.angle += 360.0
                elif self.angle >= 360.0:
                    self.angle -= 360.0

            if self.param_time == 0:
                self.init_mode()
            else:
                done = True

            # calculate new position according speed and angle!!
            # polar to decart
            ta = self.angle * math.pi / 180.0
            td = used_seconds * self.speed
            self.x += td * math.cos(ta)
            self.y += td * math.sin(ta)
            # if out of range = make vessel flow to center some time
            if abs(self.x) > self.limit or abs(self.y) > self.limit:
                self.mode = 0
                self.speed = self.maxspeed
                self.angle = to_polar(self.x, self.y)[0]
                self.angle = self.angle-180.0
                if self.angle < 0:
                    self.angle += 360.0
                self.param_time = random.randint(20, 30)

    def init_mode(self):
        self.mode = random.randint(0, 2)
        # self.mode = 2
        if self.mode == 0:  # wait
            self.param_time = random.randint(10, 20)
        elif self.mode == 1:  # speed change
            delta = random.uniform(0, self.maxspeed) - self.speed
            self.param_time = math.ceil(abs(delta/self._velocity))
            self.param_value = delta / self.param_time
            pass
        elif self.mode == 2:  # rotate
            delta = random.uniform(-160.0, +160.0)
            self.param_time = math.ceil(abs(delta/self._velocity/15))  # rotate speed three times slower than acceleration
            self.param_value = delta / self.param_time
            pass

    def get_vdm(self, group: str, msg_id: int):  # detailed false for msg_id 1 / true for msg_id 5
        #    (self, talker: str, group_id: int, channel: str):
        bc = helpers.bit_collector()
        now = datetime.now()
        if msg_id == 1 or msg_id == 2 or msg_id == 3:
            # calc lon lat
            latlon = helpers.latlon2meter(CENTER)
            latlon[LON] += self.x
            latlon[LAT] += self.y
            latlon = helpers.meters2latlon(latlon)
            bc.push(1, 6)  # Message Type
            bc.push(0, 2)  # Repeat Indicator
            bc.push(self.mmsi, 30)  #
            bc.push(0, 4)  # nav status
            bc.push(0, 8)  # turn
            bc.push(int(self.speed * 19.438452), 10)  # speed, 1 metres per second (m/s) is equal to 1.9438452 knots
            bc.push(0, 1)  # accuracy
            bc.push(int(latlon[LON]*600000), 28)  # lon
            bc.push(int(latlon[LAT]*600000), 27)  # lat
            bc.push(int(self.angle*10), 12)  # cog
            bc.push(int(self.angle), 9)  # hog
            bc.push(now.second, 6)  # seconds
            bc.push(0, 2)  # maneuver = Not available (default)
            bc.push(0, 3)  # spare
            bc.push(0, 1)  # raim
            bc.push(0, 19)  # radio
        elif msg_id == 5:
            bc.push(5, 6)  # Message Type
            bc.push(0, 2)  # Repeat Indicator
            bc.push(self.mmsi, 30)  # mmsi
            bc.push(0, 2)  # AIS Version
            bc.push(self.mmsi, 30)  # IMO Number = mmsi
            bc.push_str(self.shipname[:4], 7)
            bc.push_str(self.shipname, 20)
            bc.push(self.type, 8)  #
            bc.push(int(self.h*0.7), 9)  #
            bc.push(int(self.h*0.3), 9)  #
            bc.push(int(self.w*0.5), 6)  #
            bc.push(int(self.w*0.5), 6)  #
            bc.push(0, 4)  # epfd
            bc.push(now.month, 4)  # month
            bc.push(now.day, 5)  # day
            bc.push(now.hour, 5)  # hour
            bc.push(now.minute, 6)  # minute
            bc.push(int(self.draught*10), 8)  # Draught
            bc.push_str('unknown', 20)  # Destination
            bc.push(1, 1)  # dte
            bc.push(0, 1)  # spare

        return bc.create_vdm('AI', group, 'A')


"""
gps = fake_gps()
gps.cycle(100)
gps.get_sat(CENTER)
"""
if USE_NETWORK:
    if MODE == MODE_TCP:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((IP, PORT))
        sock.listen()
    elif MODE == MODE_UDP:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    else:
        print("check MODE variable, it can be MODE_TCP or MODE_UDP.")
        quit()

if DYNA_SHOW:
    os.system('cls')

# read init values
ships = []
f = open('init.json')
ships_init = j.load(f)
c = 0
for x in ships_init['ships']:
    # ships.append(ship(x, MAX_DIST if c == 0 else MAX_DIST*2))
    ships.append(ship(x, MAX_DIST))
    c += 1
for s in ships:
    s.init_mode()
f.close()
group = 1

tmr1, tmr5 = 0, 0
while True:
    try:
        collect = ""
        if USE_NETWORK:
            
            if MODE == MODE_TCP:
                
                print(f"[.] Wait for connection at tcp://{IP}:{PORT}")
                conn, addr = sock.accept()
            
                print(f"[I] Connected by {addr}")
        
        while True:
            if DYNA_SHOW:
                c = 1
                for s in ships:
                    if s.active:
                        at(c, 1, f"{s.shipname}")
                        
                        
                        at(c, 12, f"MODE: {mode_descr[s.mode]} (TIME:{s.param_time:>5.1f})  {s.param_value:>6.3f}        ")
                        # at(c, 35, f"TIME:   ")
                        # at(c, 50, f"PARAM:   ")
                        # at(c+1, 5, f"SPEED:  ")
                        # at(c+1, 25, f"ANGLE:  ")
                        at(c+1, 12, f"XY: {s.x:>10.3f}, {s.y:>10.3f}     ")
                        at(c+2, 12, f"SA: {s.speed:>10.3f}, {s.angle:>10.3f}        ")
                        # at(c+1, 55, f"Y: {s.y:>10.3f}  ")
                        c += 4
            for s in ships:
                s.cycle(UPD_INTERVAL)
            
            # foreign ships
            tmr1 += UPD_INTERVAL
            while tmr1 >= MSG1_DELAY:
                for s in ships:
                    # if not s.own:
                    if s.active:
                        result = s.get_vdm(group, 1)
                        group = result['group']
                        for sentence in result['data']:
                            collect += sentence+helpers.NLBR
                tmr1 -= MSG1_DELAY
            tmr5 += UPD_INTERVAL
            while tmr5 >= MSG5_DELAY:
                for s in ships:
                    # if not s.own:
                    if s.active:
                        result = s.get_vdm(group, 5)
                        group = result['group']
                        for sentence in result['data']:
                            collect += sentence+helpers.NLBR
                tmr5 -= MSG5_DELAY
            
            # own vessel
            for s in ships:
                if s.own:
                    pass

            
                
            if USE_NETWORK:
                
                if collect != "":
                    print(collect)
                    collect = bytes(collect, 'ascii')
                    if MODE == MODE_UDP:
                        sock.sendto(collect, (IP, PORT))
                    elif MODE == MODE_TCP:
                        conn.sendall(collect)
                    collect = ""

            time.sleep(UPD_INTERVAL)
    except ConnectionResetError:
        print("[E] ConnectionResetError")
    except ConnectionAbortedError:
        print("[E] ConnectionAbortedError")
    except KeyboardInterrupt:
        print('\nInterrupted\n')
        sock.close()
        try:
            sys.exit(130)
        except SystemExit:
            os._exit(130)
    except:
        print('------ MAIN ERROR ------')
        print(traceback.format_exc())
    


