import re
import time
# import xlsxwriter
import os
import math
from datetime import datetime
import random

re_float = re.compile(r'[-+]?([0-9]*[.])?[0-9]+([eE][-+]?\d+)?')
re_floatstr2int = re.compile(r'([-+]?[0-9]+)\.?[0-9]*')
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
        self.x, self.y = random.randint(-self.limit,
                                        self.limit), random.randint(-self.limit, self.limit)
        self.angle, self.speed = random.uniform(
            0.0, 359.0), random.uniform(0.0, self.maxspeed)
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
            # rotate speed three times slower than acceleration
            self.param_time = math.ceil(abs(delta/self._velocity/15))
            self.param_value = delta / self.param_time
            pass

    # detailed false for msg_id 1 / true for msg_id 5
    def get_vdm(self, group: str, msg_id: int):
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
            # speed, 1 metres per second (m/s) is equal to 1.9438452 knots
            bc.push(int(self.speed * 19.438452), 10)
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


def is_intersect(rect1, rect2):
    return ((rect1[0] < rect2[2]) and (rect1[2] > rect2[0]) and (rect1[3] > rect2[1]) and (rect1[1] < rect2[3]))


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
        y = math.log(math.tan(((90 + coords[1]) * math.pi) / 360)) / (math.pi / 180)
        y = (y * 20037508.34) / 180
    return [x, y]


def meters2latlon(pos):  # epsg3857 to Epsg4326
    x = pos[0]
    y = pos[1]
    x = (x * 180) / 20037508.34
    y = (y * 180) / 20037508.34
    y = (math.atan(math.pow(math.e, y * (math.pi / 180))) * 360) / math.pi - 90
    return [x, y]


# backward (in JS)
# function epsg3857toEpsg4326(pos) {
#     let x = pos[0]
#     let y = pos[1]
#     x = (x * 180) / 20037508.34
#     y = (y * 180) / 20037508.34
#     y = (Math.atan(Math.pow(Math.E, y * (Math.PI / 180))) * 360) / Math.PI - 90
#   return [x, y]; }


def is_int(s):
    try:
        i = int(s)
    except ValueError:
        return False
    else:
        return True


def is_float(s):
    matches = re_float.match(s)
    if matches == None:
        return False
    return (matches.span()[1] == len(s))


def floatstr2int(s):
    matches = re_floatstr2int.match(s)
    if matches == None:
        return False
    r = s[matches.regs[1][0]:matches.regs[1][1]]
    # i = int(r)
    return int(r)


def utc_ms(add_time: int = 0):
    return (time.time_ns()//1000000)+add_time


class gps_class():
    def __init__(self):
        # GSA
        self.modeAM, self.modeFIX = None, None
        self.used_sv = []
        self.pdop, self.hdop, self.vdop = None, None, None

        self.hog_true, self.hog_magnetic = None, None
        self.sog_knots, self.sog_km = None, None
        self.lat, self.lon, self.magnetic_variation = 0, 0, 0
        self.datetime = datetime(1, 1, 1)


class satellites_class():
    def __init__(self):
        # GSV
        self.sat_list = {}

    def modify(self, data):  # prn, elevation, azimuth, snr
        if len(data) != 4:
            return
        # zz = []
        # for x in data:            z = in
        data = [int(x) if x.isdigit() else None for x in data]
        if not (data[0] in self.sat_list):
            self.sat_list[data[0]] = {}
        self.sat_list[data[0]]['elevation'] = data[1]
        self.sat_list[data[0]]['azimuth'] = data[2]
        self.sat_list[data[0]]['snr'] = data[3]
        self.sat_list[data[0]]['last_access'] = utc_ms()


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

    def push_str(self, data: str,length :int):
        data = data.upper()
        str_len = len(data)
        if str_len > length:
            str_len = length
        it = 0
        while it < str_len:
            ch = data[it]
            index = self.NMEA_CHARS.find(ch)
            if index!=-1:
                self.push(index,6)
            it+=1
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

    def _add_cs(self,s: str):
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
                if pad>0:
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
    """
!AIVDM,2,1,9,B,53nFBv01SJ<thHp6220H4heHTf2222222222221?50:454o<`9QSlUDp,0*09
54;?OTQ2koq8mTuL000mTuLp0000000000000000103111T9o35CRkSm
!AIVDM,2,2,9,B,888888888888880,2*2E
!AIVDM,2,1,6,B,56:fS:D0000000000008v0<QD4r0`T4v3400000t0`D147?ps1P00000,0*3D
!AIVDM,2,2,6,B,000000000000008,2*29
!AIVDM,2,1,8,A,53Q6SR02=21U`@H?800l4E9<f1HTLt000000001?BhL<@4q30Glm841E,0*7C
!AIVDM,2,2,8,A,1DThUDQh0000000,2*4D
!AIVDM,1,1,,B,133UQ650000>gOhMGl0Sh1nH0d4D,0*33

['54;?OTQ2koq8mTuL000mTuLp0000000000000000103111T9o35CRkSm,0', 'kP0000000000008,0']

!AIVDM,2,1,3,B,55P5TL01VIaAL@7WKO@mBplU@<PDhh000000001S;AJ::4A80?4i@E53,0*3E
               54;?OTQ2koq8mTuL000mTuLp0000000000000000103111T9o35CRkSm,0
!AIVDM,2,2,3,B,1@0000000000000,2*55
               kP0000000000008

    def create_vdm(message_id, data, header='AI', group_id: int = 1):
        def get_checksum(s: str):
            cs = 0
            for c in s:
                cs ^= ord(c)
            return cs

        def collect_bits(bc):

            if not (message_id in VDM_DEFS):
                raise Exception(f'[MSG_ID:{message_id}] Not found in VDM_DEFS')
            if not (message_id in VDM_TYPES):
                raise Exception(f'[MSG_ID:{message_id}] Not found in VDM_TYPES')

            bc.add_bits(message_id, 6)

            for field in VDM_DEFS[message_id]:
                # print(f'Field: {field["name"]} ({field})')
                if field['start'] != bc.length:
                    raise Exception(f'[MSG_ID:{message_id}] No field with start at: {bc.length}')
                if not (field['name'] in data):
                    if 'default' in field:
                        value = field['default']
                    else:
                        raise Exception(f'[MSG_ID:{message_id}] No default value for {field["name"]}')
                else:
                    value = data[field['name']]
                # value_bitlen=helpers.bit_collector.get_len(value)
                # if value_bitlen > field['len']:
                #     raise Exception(f'[MSG_ID:{message_id}] Value for {field["name"]}={value} exceed maximum length. Maximum allowed {field["len"]}, got {value_bitlen}.')
                value_type = type(value)
                if field['type'] == NMEA_TYPE_INT:
                    bc.add_bits(value, field['len'])
                elif field['type'] == NMEA_TYPE_FLOAT:
                    bc.add_bits(round(value*field['exp']), field['len'])
                elif field['type'] == NMEA_TYPE_STRING:
                    if value_type != str:
                        raise Exception(f'[MSG_ID:{message_id}] {field["name"]}: string expected, got {value_type}')
                    value = value.upper()
                    l = len(value)
                    if l < field['len']:
                        value += '@' * (field['len']-l)
                        l = field['len']
                    else:
                        l = min(len(value), field['len'])

                    for c in range(l):
                        i = helpers.bit_collector.NMEA_CHARS.find(value[c])

                        if i == -1:
                            raise Exception(f'[MSG_ID:{message_id}] {field["name"]}: unsupported character `{value[c]}`')
                        bc.add_bits(i, 6)
                else:
                    raise Exception(f'[MSG_ID:{message_id}] Unknown field type ({field["type"]})')
            if bc.length != VDM_TYPES[message_id]['len']:
                raise Exception(f'[MSG_ID:{message_id}] Message len error, expected {VDM_TYPES[message_id]["len"]}, got {bc.length}')

        def create_str(bc):
            MAX_PAYLOAD = 336  # max bits in one message
            ptr = 0
            result = []
            collected = 0
            collect = r''
            while ptr < bc.length:
                b = bc.get_int(ptr, 6)
                c = b + 48
                if c > 87:
                    c += 8
                # print(f'{b}\t{c}\t{chr(c)}')
                collect += chr(c)
                ptr += 6
                collected += 6
                if collected >= MAX_PAYLOAD or ptr >= bc.length:
                    result.append(collect)
                    collected = 0
                    collect = r''
            return result

        def create_messages(messages: dict, header: str, channel: str = 'A', group_id: int = None):
            result = []
            messages_count = len(messages)
            for i in range(messages_count):
                s = header+'VDM'
                s = f'{s},{messages_count},{i+1},'
                if messages_count > 1:
                    s = f'{s}{messages_count}'
                s = f'{s},{channel},{messages[i]},0'

                cs = get_checksum(s)
                s = f'!{s}*{format(cs, "02X")}'
                print(s)
                result.append(s)

            return result
    
    bitcollector = helpers.bit_collector()
    collect_bits(bitcollector)
    messages = create_str(bitcollector)
    if len(messages) > 1 and group_id is None:
        raise Exception(f'[MSG_ID:{message_id}] For multiple message sequences you must provide GROUP_ID')
    nmea = create_messages(messages, header)
    # print(nmea)
    return nmea
"""


def create_vdm(message_id, data, header='AI', group_id: int = 1):
    def get_checksum(s: str):
        cs = 0
        for c in s:
            cs ^= ord(c)
        return cs

    def collect_bits(bc):

        if not (message_id in VDM_DEFS):
            raise Exception(f'[MSG_ID:{message_id}] Not found in VDM_DEFS')
        if not (message_id in VDM_TYPES):
            raise Exception(f'[MSG_ID:{message_id}] Not found in VDM_TYPES')

        bc.add_bits(message_id, 6)

        for field in VDM_DEFS[message_id]:
            # print(f'Field: {field["name"]} ({field})')
            if field['start'] != bc.length:
                raise Exception(f'[MSG_ID:{message_id}] No field with start at: {bc.length}')
            if not (field['name'] in data):
                if 'default' in field:
                    value = field['default']
                else:
                    raise Exception(f'[MSG_ID:{message_id}] No default value for {field["name"]}')
            else:
                value = data[field['name']]
            # value_bitlen=helpers.bit_collector.get_len(value)
            # if value_bitlen > field['len']:
            #     raise Exception(f'[MSG_ID:{message_id}] Value for {field["name"]}={value} exceed maximum length. Maximum allowed {field["len"]}, got {value_bitlen}.')
            value_type = type(value)
            if field['type'] == NMEA_TYPE_INT:
                bc.add_bits(value, field['len'])
            elif field['type'] == NMEA_TYPE_FLOAT:
                bc.add_bits(round(value*field['exp']), field['len'])
            elif field['type'] == NMEA_TYPE_STRING:
                if value_type != str:
                    raise Exception(f'[MSG_ID:{message_id}] {field["name"]}: string expected, got {value_type}')
                value = value.upper()
                l = len(value)
                if l < field['len']:
                    value += '@' * (field['len']-l)
                    l = field['len']
                else:
                    l = min(len(value), field['len'])

                for c in range(l):
                    i = helpers.bit_collector.NMEA_CHARS.find(value[c])

                    if i == -1:
                        raise Exception(f'[MSG_ID:{message_id}] {field["name"]}: unsupported character `{value[c]}`')
                    bc.add_bits(i, 6)
            else:
                raise Exception(f'[MSG_ID:{message_id}] Unknown field type ({field["type"]})')
        if bc.length != VDM_TYPES[message_id]['len']:
            raise Exception(f'[MSG_ID:{message_id}] Message len error, expected {VDM_TYPES[message_id]["len"]}, got {bc.length}')

    def create_str(bc):
        MAX_PAYLOAD = 336  # max bits in one message
        ptr = 0
        result = []
        collected = 0
        collect = r''
        while ptr < bc.length:
            b = bc.get_int(ptr, 6)
            c = b + 48
            if c > 87:
                c += 8
            # print(f'{b}\t{c}\t{chr(c)}')
            collect += chr(c)
            ptr += 6
            collected += 6
            if collected >= MAX_PAYLOAD or ptr >= bc.length:
                result.append(collect)
                collected = 0
                collect = r''
        return result

    def create_messages(messages: dict, header: str, channel: str = 'A', group_id: int = None):
        result = []
        messages_count = len(messages)
        for i in range(messages_count):
            s = header+'VDM'
            s = f'{s},{messages_count},{i+1},'
            if messages_count > 1:
                s = f'{s}{messages_count}'
            s = f'{s},{channel},{messages[i]},0'

            cs = get_checksum(s)
            s = f'!{s}*{format(cs, "02X")}'
            print(s)
            result.append(s)

        return result

    bitcollector = helpers.bit_collector()
    collect_bits(bitcollector)
    messages = create_str(bitcollector)
    if len(messages) > 1 and group_id is None:
        raise Exception(f'[MSG_ID:{message_id}] For multiple message sequences you must provide GROUP_ID')
    nmea = create_messages(messages, header)
    # print(nmea)
    return nmea

    def get_str(self,  start: int, length: int):

        result = ''
        while length > 0:
            code = self.get_int(start, 6)
            # print(code)
            if code == 0:  # or code==32:
                break
            result += bit_collector.NMEA_CHARS[code]
            start += 6
            length -= 1
        return result

    def decode_vdm(self, data, pad):
        # print(f'datalen={len(data)} (data={data})')
        for ch in data:
            code = ord(ch)-48
            if code > 40:
                code -= 8
            self.push(code, 6)
        while (pad > 0):
            self.push(0, 1)
            pad -= 1
        # self.length -= int(pad)
        # print(f'char={ch}\tcode={code}\tbufflen={self.length}')



def is_zero(v):
    return abs(v) < 1e-6
