import re
import time
# import xlsxwriter
import os
import math
from datetime import datetime
import random

tb, sb, mb = [], [0], [0]
c, b = 32, 1
while c > 0:
    tb.append(b)
    sb.append(b)
    mb.append(b-1)
    b <<= 1
    c -= 1
test_bit = tuple(tb)
sign_bit = tuple(sb)
mask_bit = tuple(mb)
del b, c, sb, mb, tb

NLBR = chr(13)+chr(10)
LON = 0
LAT = 1
# PI = math.pi
π = math.pi
# PIM2 = math.pi*2

MODE_WAIT = 0
MODE_SPEED = 1
MODE_ROTATE = 2


def to_deg(rad: float):
    return math.fmod(rad*180.0 / π, 360)


def to_rad(deg: float):
    return math.fmod(deg * π / 180.0, 2*π)


def to_polar(x, y=None):
    if y == None:
        if not isinstance(x, list):
            raise ValueError("If only one argument passed to <to_polar> it must be list")
        else:
            y = x[1]
            x = x[0]

    if x == 0:
        if y < 0:
            a = π/2*3
        else:
            a = π/2
    else:
        a = math.atan(y / x)
        if x < 0:
            a += π
        elif y < 0:
            a += π*2
    return [a, math.sqrt(x * x + y * y)]


def sign(a):
    if a > 0:
        return 1
    elif a < 0:
        return -1
    else:
        return 0


class ship():

    def __init__(self, json, center_deg, limit):
        # read JSON
        self.active = json['active'] if 'active' in json else 0
        self.w = json['width'] if 'width' in json else 10
        self.h = json['height'] if 'height' in json else 3
        self.draught = json['draught'] if 'draught' in json else 2
        self.own = json['own'] if 'own' in json else False
        self.mmsi = json['mmsi'] if 'mmsi' in json else 0
        self.shipname = json['shipname'] if 'shipname' in json else 'Unknown'
        self.maxspeed = json['maxspeed'] if 'maxspeed' in json else 'maxspeed'
        self.type = json['type'] if 'type' in json else 0

        # setup init pos, speed, angle
        self.limit = limit
        self.center_met = latlon2meter(center_deg)
        self.delta_met = [random.randint(-self.limit,    self.limit), random.randint(-self.limit, self.limit)]
        self.eval_deg()
        self.angle = random.uniform(0.0, π*2)

        self.maxspeed *= 1000/3600  # recalculate from km/h to m/s
        # self.maxspeed *= 25 dbg
        self.speed = random.uniform(0.0, self.maxspeed)

        # some empiric values for evaluate accelerate
        self.velocity = 0.05  # m/s²
        self.rotate_speed = to_rad(20)/60  # rotate rate = degree / minute

        self.mode, self.param_time, self.param_value = 0, 0, 0

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

            if self.param_time == 0:
                self.init_mode()
            else:
                done = True

            # calculate new position according speed and angle!!
            td = used_seconds * self.speed
            self.delta_met[LON] += td * math.cos(self.angle)
            self.delta_met[LAT] += td * math.sin(self.angle)
            self.eval_deg()

            # if out of range = make vessel flow to center some time
            if abs(self.delta_met[LON]) > self.limit or abs(self.delta_met[LAT]) > self.limit:
                self.mode = 0
                self.speed = self.maxspeed
                self.angle = to_polar(self.delta_met)[0]
                self.angle += π  # invert angle

                self.param_time = random.randint(20, 30)

    def init_mode(self):
        self.mode = random.randint(0, 2)
        # self.mode = 2
        if self.mode == 0:  # wait
            self.param_time = random.randint(10, 20)
        elif self.mode == 1:  # speed change
            speed_delta = random.uniform(0, self.maxspeed) - self.speed
            self.param_time = math.ceil(abs(speed_delta)/self.velocity)
            self.param_value = self.velocity / self.param_time
        elif self.mode == 2:  # rotate
            rotate_delta = random.uniform(-π, +π)
            self.param_time = math.ceil(abs(rotate_delta) / self.rotate_speed)
            self.param_value = rotate_delta / self.param_time

    def angle_deg(self):
        return to_deg(self.angle)

    def eval_deg(self):
        self.deg = meters2latlon([self.center_met[LON]+self.delta_met[LON], self.center_met[LAT]+self.delta_met[LAT]])

    # detailed false for msg_id 1 / true for msg_id 5
    def get_vdm(self, group: str, msg_id: int):
        #    (self, talker: str, group_id: int, channel: str):
        bc = bit_collector()
        now = datetime.now()
        if msg_id == 1 or msg_id == 2 or msg_id == 3:

            bc.push(1, 6)  # Message Type
            bc.push(0, 2)  # Repeat Indicator
            bc.push(self.mmsi, 30)  #
            bc.push(0, 4)  # nav status
            bc.push(0, 8)  # turn
            # speed, 1 metres per second (m/s) is equal to 1.9438452 knots
            bc.push(int(self.speed * 19.438452), 10)
            bc.push(0, 1)  # accuracy
            bc.push(int(self.deg[LON]*600000), 28)  # lon
            bc.push(int(self.deg[LAT]*600000), 27)  # lat
            bc.push(int(self.angle_deg()*10), 12)  # cog
            bc.push(int(self.angle_deg()), 9)  # hog
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
            bc.push_str(self.shipname[:7], 7)
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


def sign(a):
    if a > 0:
        return 1
    elif a < 0:
        return -1
    else:
        return 0


def latlon2meter(coords):  # in format (lon,lat)
    x = (coords[0] * 20037508.34) / 180
    if abs(coords[1]) >= 85.051129:
        # The value 85.051129° is the latitude at which the full projected map becomes a square
        y = sign(coords[1]) * abs(coords[1])*111.132952777
    else:
        y = math.log(math.tan(((90 + coords[1]) * π) / 360)) / (π / 180)
        y = (y * 20037508.34) / 180
    return [x, y]


def meters2latlon(pos):  # epsg3857 to Epsg4326
    x = pos[0]
    y = pos[1]
    x = (x * 180) / 20037508.34
    y = (y * 180) / 20037508.34
    y = (math.atan(math.pow(math.e, y * (π / 180))) * 360) / π - 90
    return [x, y]


def is_int(s):
    try:
        i = int(s)
    except ValueError:
        return False
    else:
        return True


def is_float(s):
    re_float = re.compile(r'[-+]?([0-9]*[.])?[0-9]+([eE][-+]?\d+)?')

    matches = re_float.match(s)
    if matches == None:
        return False
    return (matches.span()[1] == len(s))


def floatstr2int(s):
    re_floatstr2int = re.compile(r'([-+]?[0-9]+)\.?[0-9]*')
    matches = re_floatstr2int.match(s)
    if matches == None:
        return False
    r = s[matches.regs[1][0]:matches.regs[1][1]]
    # i = int(r)
    return int(r)


def utc_ms(add_time: int = 0):
    return (time.time_ns()//1000000)+add_time


class bit_collector():
    NMEA_CHARS = '@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_ !"#$%&\\()*+,-./0123456789:;<=>?'

    @staticmethod
    def get_len(v):
        if type(v) == int:
            if v == 0:
                return 0
            else:
                if v < 0:
                    v = ~v + 1
                return math.ceil(math.log(v, 2))
        elif type(v) == float:
            pass
        else:
            raise Exception(f'bit_collector.get_len: Unknown type({type(v)})')

    def twos_comp(self, val, bits):
        """compute the 2's complement of int value val"""
        if (val & sign_bit[bits]) != 0:
            val -= test_bit[bits]
        return val

    def __init__(self):
        self._buff_len = 150  # bytes
        self.buff = bytearray(self._buff_len)
        self.clear()

    def clear(self):
        self.length = 0
        for c in range(self._buff_len):
            self.buff[c] = 0

    def push(self, data: int, length: int):
        src_bit = 1 << (length-1)
        dst_bit = 1 << ((self.length & 7) ^ 7)
        while src_bit != 0:
            if data & src_bit:
                self.buff[self.length >> 3] |= dst_bit
            src_bit >>= 1
            dst_bit >>= 1
            if dst_bit == 0:
                dst_bit = 0x80
            self.length += 1

    def push_str(self, data: str, length: int):
        data = data.upper()
        str_len = len(data)
        if str_len > length:
            str_len = length
        it = 0
        while it < str_len:
            ch = data[it]
            index = self.NMEA_CHARS.find(ch)
            if index != -1:
                self.push(index, 6)
            it += 1
        while it < length:
            self.push(32, 6)
            it += 1

    def get_int(self, start: int, length: int, signed: bool = False):
        result = 0
        length_counter = length

        while length_counter > 0:
            result <<= 1
            if self.buff[start >> 3] & test_bit[start & 7 ^ 7]:
                result |= 1
            length_counter -= 1
            start += 1

        if signed:
            result = self.twos_comp(result, length)
        # sign = bits[length-1]

        # if signed and (result & test_bit[length-1]) != 0:            result = -(result ^ (bits[length]-1))
        return result

    def _add_cs(self, s: str):
        cs = 0
        for c in s:
            cs ^= ord(c)
        return f'{s}*{cs:02X}'

    def create_vdm(self, talker: str, group: int, channel: str):

        MAX_PAYLOAD = 336  # max bits in one message
        data = []

        start, collected, accum = 0, 0, ''
        while start < self.length:
            rest_bits = min(6, self.length-start)
            b = self.get_int(start, 6)
            c = b + 48
            if c > 87:
                c += 8
            accum += chr(c)
            start += rest_bits
            collected += rest_bits
            if collected >= MAX_PAYLOAD or start >= self.length:
                pad = collected % 6
                if pad > 0:
                    pad = 6 - pad
                accum += f',{pad}'
                data.append(accum)
                accum = ''
                collected = 0

        msg_count = len(data)
        for c in range(msg_count):
            hdr = f'{talker}VDM,'  # talker + sentence
            hdr = hdr + f'{msg_count},'  # messages count
            hdr = hdr + f'{c+1},'  # current index
            hdr = hdr + (f'{group},' if msg_count > 1 else ',')  # group index
            hdr = hdr + f'{channel},'
            data[c] = hdr + data[c]
            data[c] = '!'+self._add_cs(data[c])

        if msg_count > 1:
            group = (group + 1) % 9
        return {
            'data': data,
            'group': group

        }


def is_zero(v):
    return abs(v) < 1e-6
