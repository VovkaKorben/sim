# ID NAME     MODE
# 1 TARDIS
"""
ship mode
0 no-action timer (second)
1 speed change (speed) - can be decreasing or increasing
2 rotate (angle)
"""
from datetime import datetime
import sys
import os
import json as j
# import nmea
from helpers import ship, NLBR, bit_collector
import helpers

import time
import math
import socket
import traceback

MODE_UDP = 1
MODE_TCP = 2


# MODE = MODE_TCP
MODE = MODE_UDP
IP = "192.168.1.10"
PORT = 17777
NMEA_LINES_COUNT = 10

DYNA_SHOW = True
USE_NETWORK = True

UPD_INTERVAL = 0.1  # in seconds
MSG1_DELAY = 2  # send msg type 1 each 3 seconds
MSG5_DELAY = 5  # send msg type 5 each 10 seconds

MAX_DIST = 300  # in meters
CENTER = (29.0, 62.0)  # home
LON = 0
LAT = 1
PI = math.pi
PIM2 = math.pi*2
mode_descr = ["WAIT", "SPEED", "ROTATE"]
NMEA_LINES = []
COLUMN_INTERVAL = 3
# len | default name | align( Left = false, default; Right = true)
COLUMNS = [[9, "MMSI"],
           [12, "NAME"],
           [9, "MODE"],
           [10, "TIME", True],
           [10, "PARAM", True],
           [22, "LONLAT"],
           ]
COLUMNS = [[10, "MMSI"],
           [10, "NAME"],
           [10, "MODE"],
           [10, "TIME", True],
           [10, "PARAM", True],
           [10, "LONLAT"],
           ]


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


def get_col_start(col: int):
    if col < 0 or col >= len(COLUMNS):
        return -1
    r = 0
    while col > 0:
        r += COLUMNS[col-1][0]+COLUMN_INTERVAL
        col -= 1
        # if col > 0:            r += COLUMN_INTERVAL
    return r


def draw_text(line, col, text=None):
    if col < 0 or col >= len(COLUMNS):
        return
    if text == None:
        text = COLUMNS[col][1]
    else:
        text = str(text)
    start = get_col_start(col)

    align = False
    if len(COLUMNS[col]) > 2 and COLUMNS[col][2] == True:
        align = True

    if len(text) > COLUMNS[col][0]:
        text = text[:COLUMNS[col][0]-1] + "^"

    if align:
        start += COLUMNS[col][0]-len(text)
    at(line, start, text)


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
    os.system('clear')

# read init values
ships = []
f = open('init.json')
ships_init = j.load(f)
line_no = 0
for x in ships_init['ships']:
    # ships.append(ship(x, MAX_DIST if c == 0 else MAX_DIST*2))
    ships.append(ship(x, MAX_DIST))
    line_no += 1
for s in ships:
    s.init_mode()
f.close()
group = 1

tmr1, tmr5 = 0, 0
while True:
    try:
        collect = []
        if USE_NETWORK:

            if MODE == MODE_TCP:

                print(f"[.] Wait for connection at tcp://{IP}:{PORT}")
                conn, addr = sock.accept()

                print(f"[I] Connected by {addr}")

        while True:
            if DYNA_SHOW:
                line_no = 1

                # header
                for col_no in range(len(COLUMNS)):  # = [[1,"MMSI"],[10,"NAME"],[20,"MODE"]]
                    draw_text(line_no, col_no)
                line_no += 1

                for s in ships:
                    if s.active:
                        draw_text(line_no, 0, s.mmsi)
                        draw_text(line_no, 1, s.shipname)
                        draw_text(line_no, 2, mode_descr[s.mode])
                        draw_text(line_no, 3, "{:.1f}".format(s.param_time))
                        draw_text(line_no, 4, "{:.3f}".format(s.param_value))

                        # at(line_no, 12,                           f"MODE: {mode_descr[s.mode]} (TIME:{s.param_time:>5.1f})  {s.param_value:>6.3f}        ")
                        # at(c, 35, f"TIME:   ")
                        # at(c, 50, f"PARAM:   ")
                        # at(c+1, 5, f"SPEED:  ")
                        # at(c+1, 25, f"ANGLE:  ")
                        # at(line_no+1, 12,                           f"XY: {s.x:>10.3f}, {s.y:>10.3f}     ")
                        # at(line_no+2, 12,                           f"SA: {s.speed:>10.3f}, {s.angle:>10.3f}        ")
                        # at(c+1, 55, f"Y: {s.y:>10.3f}  ")
                        line_no += 1
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

            if len(collect) > 0:

                if DYNA_SHOW:
                    line_no += 1
                    NMEA_LINES.extend(collect)
                    if len(NMEA_LINES) > NMEA_LINES_COUNT:
                        NMEA_LINES = NMEA_LINES[len(NMEA_LINES)-NMEA_LINES_COUNT:]
                    for line in NMEA_LINES:
                        at(0, line_no, line)
                        line_no += 1

                if USE_NETWORK:
                    packet = ""
                    for line in NMEA_LINES:
                        packet += line + NLBR
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
