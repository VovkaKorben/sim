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
from helpers import ship, NLBR, bit_collector, LON, LAT, to_deg
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
USE_NETWORK = False

UPD_INTERVAL = 0.1  # in seconds
# MSG1_DELAY = 2  # send msg type 1 each 3 seconds
# MSG5_DELAY = 5  # send msg type 5 each 10 seconds

MAX_DIST = 300  # in meters
CENTER = (29.0, 62.0)  # home

mode_descr = ["⏳", "🐢🚀", "↻ ROT ↺"]
NMEA_LINES = []
COLUMN_INTERVAL = 3
# len | default name | align( Left = false, default; Right = true)
COLUMNS = [[10, "MMSI"],
           [10, "NAME"],
           [10, "MODE"],
           [8, "TIME", True],
        #    [10, "PARAM", True],
           [10, "ANGLE", True],
           [10, "km/h", True],
           [10, "ΔX, ΔY", True],
           [25, "LON,LAT", True],
           ]
# VDM group ID | update interval | current value (added dynamically)
timers = [
    [1, 3],
    [5, 5]
]


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

# read init values
ships = []
f = open('init.json')
ships_init = j.load(f)

for x in ships_init['ships']:
    if x['active']:
        ships.append(ship(x, CENTER, MAX_DIST))
for s in ships:
    s.init_mode()
f.close()
group = 1

# update timers (first output will be immediatelly)
for tmr_no in range(len(timers)):
    # timers[tmr_no].append(timers[tmr_no][1])
    timers[tmr_no].append(0.0)

try:
    while True:
        try:
            line_no = 0
            collect = []
            os.system('clear')

            if USE_NETWORK:

                if MODE == MODE_TCP:

                    print(f"[.] Wait for connection at tcp://{IP}:{PORT}")
                    conn, addr = sock.accept()

                    print(f"[I] Connected by {addr}")

            while True:

                # process message timers
                for tmr_no in range(len(timers)):

                    while timers[tmr_no][2] >= timers[tmr_no][1]:
                        for s in ships:
                            result = s.get_vdm(group, timers[tmr_no][0])
                            group = result['group']
                            collect.extend(result['data'])
                        timers[tmr_no][2] -= timers[tmr_no][1]
                    timers[tmr_no][2] += UPD_INTERVAL

                if len(collect) > 0:

                    NMEA_LINES.extend(collect)
                    if len(NMEA_LINES) > NMEA_LINES_COUNT:
                        NMEA_LINES = NMEA_LINES[len(NMEA_LINES)-NMEA_LINES_COUNT:]

                    if USE_NETWORK:
                        packet = ""
                        for line in NMEA_LINES:
                            packet += line + NLBR
                        packet = bytes(packet, 'ascii')
                        if MODE == MODE_UDP:
                            sock.sendto(packet, (IP, PORT))
                        elif MODE == MODE_TCP:
                            conn.sendall(packet)

                    collect = []

                if DYNA_SHOW:

                    line_no = 1

                    # header
                    for col_no in range(len(COLUMNS)):
                        draw_text(line_no, col_no)
                    line_no += 1

                    # ships data
                    for s in ships:
                        draw_text(line_no, 0, s.mmsi)
                        draw_text(line_no, 1, s.shipname)
                        draw_text(line_no, 2, mode_descr[s.mode])
                        draw_text(line_no, 3, "{:.1f}".format(s.param_time))
                        # draw_text(line_no, 4, "{:.3f}".format(s.param_value))
                        draw_text(line_no, 4, "{:.1f}".format(to_deg(s.angle)))
                        draw_text(line_no, 5, "{:.3f}".format(s.speed*3.6))
                        draw_text(line_no, 6, "{:+.0f}, {:+.0f}".format(s.delta_met[LON], s.delta_met[LAT]))
                        draw_text(line_no, 7, "{:.7f}, {:.7f}".format(s.deg[LON], s.deg[LAT]))
                        line_no += 1

                    # draw last N NMEA messages
                    line_no += 1
                    for line in NMEA_LINES:
                        at(line_no, 0, line)
                        line_no += 1

                for s in ships:
                    s.cycle(UPD_INTERVAL)

                time.sleep(UPD_INTERVAL)
                os.system('clear')
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
    line_no += 1
    at(line_no, 0, '------ MAIN ERROR ------')
    line_no += 1
    err = traceback.format_exc().split('\n')
    for el in err:
        at(line_no, 0, el)
        line_no += 1
