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


def at(x, y, text):
    sys.stdout.write("\x1b7\x1b[%d;%df%s\x1b8" % (x, y, text))
    sys.stdout.flush()


def draw_text(line, col, text=None):

    def get_col_start(col: int):
        if col < 0 or col >= len(COLUMNS):
            return -1
        r = 0
        while col > 0:
            r += COLUMNS[col-1][0]+COLUMN_INTERVAL
            col -= 1
            # if col > 0:            r += COLUMN_INTERVAL
        return r

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


# consts
NETWORK_DISABLED = 0
NETWORK_TCP = 1
NETWORK_UDP = 2

mode_descr = ["⏳", "🐢🚀", "↻ ROT ↺"]
COLUMN_INTERVAL = 3
COLUMNS = [  # len | default name | align( Left = false, default; Right = true)
    [10, "MMSI"],
    [10, "NAME"],
    [10, "MODE"],
    [8, "TIME", True],
    #    [10, "PARAM", True],
    [10, "ANGLE", True],
    [10, "km/h", True],
    [10, "ΔX, ΔY", True],
    [25, "LON,LAT", True],
]

# work arrays
NMEA_LINES = []
timers = [  # VDM group ID | update interval | current value | msg counts
    [1, 3, 0, 0],
    [5, 5, 0, 0]
]


# read init values
json_file = open('init.json')
ini = j.load(json_file)
json_file.close()


NETWORK_MODE = NETWORK_DISABLED
if ini['network']['enabled']:
    if ini['network']['mode'].upper() == "TCP":
        NETWORK_MODE = NETWORK_TCP
    elif ini['network']['mode'].upper() == "UDP":
        NETWORK_MODE = NETWORK_UDP

if NETWORK_MODE == NETWORK_TCP:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((ini['network']['ip'], ini['network']['port']))
    sock.listen()
elif NETWORK_MODE == NETWORK_UDP:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
else:
    print("network disabled, check init.json for `network` section.")

DISPLAY_ENABLED = ini['display']['enabled']
if DISPLAY_ENABLED:
    NMEA_LINES_COUNT = ini['display']['lines']
    UPD_INTERVAL = ini['display']['interval']


# load area
MAX_DIST = ini['area']['limit']
CENTER = (ini['area']['lon'], ini['area']['lat'])

# load ships
ships = []
for x in ini['ships']:
    if x['active']:
        ships.append(ship(x, CENTER, MAX_DIST))
for s in ships:
    s.init_mode()

# nmea pass-trough message group ID
group = 1

# update timers (first output will be immediatelly)
for tmr_no in range(len(timers)):
    pass
    # timers[tmr_no][2]=timers[tmr_no][1]

try:
    while True:
        try:
            line_no = 0
            collect = []
            os.system('clear')

            if NETWORK_MODE == NETWORK_TCP:
                print(f"[.] Wait for connection at tcp://{ini['network']['ip']}:{ini['network']['port']}")
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
                        timers[tmr_no][3] += 1
                        timers[tmr_no][2] -= timers[tmr_no][1]
                    timers[tmr_no][2] += UPD_INTERVAL

                NMEA_LINES.extend(collect)
                if len(NMEA_LINES) > NMEA_LINES_COUNT:
                    NMEA_LINES = NMEA_LINES[len(NMEA_LINES)-NMEA_LINES_COUNT:]

                if DISPLAY_ENABLED:
                    os.system('clear')
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

                if len(collect) > 0:

                    if NETWORK_MODE != NETWORK_DISABLED:
                        packet = ""
                        for line in NMEA_LINES:
                            packet += line + NLBR
                        packet = bytes(packet, 'ascii')
                        if NETWORK_MODE == NETWORK_UDP:
                            sock.sendto(packet, (ini['network']['ip'], ini['network']['port']))
                        else:  # NETWORK_MODE == NETWORK_TCP:
                            conn.sendall(packet)

                    collect = []

                for s in ships:
                    s.cycle(UPD_INTERVAL)

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
    line_no += 1
    at(line_no, 0, '------ MAIN ERROR ------')
    line_no += 1
    err = traceback.format_exc().split('\n')
    for el in err:
        at(line_no, 0, el)
        line_no += 1
