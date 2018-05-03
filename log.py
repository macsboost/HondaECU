#!/usr/bin/env python

from __future__ import division, print_function
from twisted.internet import reactor
from twisted.internet.task import cooperate, coiterate, LoopingCall

from pylibftdi import Device
from struct import unpack
import argparse
import platform
import datetime
import time
import os

import tables
from tables import *
from HondaECU import *

import sdnotify

n = sdnotify.SystemdNotifier()

get_time = time.time
if platform.system() == 'Windows':
	get_time = time.clock
getTime = get_time

def getDateTimeStamp():
	d = datetime.datetime.now().timetuple()
	return "%d%02d%02d%02d%02d%02d" % (d[0], d[1], d[2], d[3], d[4], d[5])

class HDS_TAB(IsDescription):
	timestamp = Float64Col()
	hds_rpm = UInt16Col()
	hds_tps_volt = UInt8Col()
	hds_tps = UInt8Col()
	hds_ect_volt = UInt8Col()
	hds_ect = UInt8Col()
	hds_iat_volt = UInt8Col()
	hds_iat = UInt8Col()
	hds_map_volt = UInt8Col()
	hds_map = UInt8Col()
	hds_unk1 = UInt8Col()
	hds_unk2 = UInt8Col()
	hds_battery_volt = UInt8Col()
	hds_speed = UInt8Col()
	hds_ign = UInt16Col()

class HDS_TAB10(HDS_TAB):
	"""
	Honda CBR 1000RR from 2004 to 2007
	Honda CBR 600RR from 2003 to 2007
	"""
	hds_unk3 = UInt8Col()

class HDS_TAB11(HDS_TAB):
	"""
	Honda CBR 1000RR from 2008
	Honda CBR 1000RR HRC from 2014
	Honda CBR 600RR from 2008
	Honda CBR 600RR HRC from 2013 (D11 ECU)
	"""
	hds_inj = UInt16Col()
	hds_unk4 = UInt16Col()

hds_tables = {
	10: [0x10, HDS_TAB10, ">H12BHB"],
	11: [0x11, HDS_TAB11, ">H12BHHH"]
}

if __name__ == '__main__':

	parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument('--debug', action='store_true', help="turn on debugging output")
	parser.add_argument('--logfile', type=str, default='/var/log/HondaECU/honda_kline_log.h5', help="log filename")
	args = parser.parse_args()

	if os.path.isabs(args.logfile):
		args.logfile = args.logfile
	else:
		args.logfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.logfile)

	h5 = open_file(args.logfile, mode="a", title="Honda KLine Engine Log")

	ecu = HondaECU()
	ecu.setup()

	if not ecu.init(debug=args.debug):
		sys.exit(-1)

	ecu.send_command([0x72],[0x00, 0xf0], debug=args.debug)

	hds_table = 10
	info = ecu.send_command([0x72], [0x71, 0x11], debug=args.debug)
	if len(info[2][2:]) == 20:
		hds_table = 11

	grp = '/HDS_TAB%d' % (hds_table)
	if not grp in h5:
		group = h5.create_group("/", 'HDS_TAB%d' % (hds_table), 'Honda Diagnostics System Table %d' % (hds_table))

	ds = getDateTimeStamp()
	log = h5.create_table(grp, "session%s" % (ds), hds_tables[hds_table][1], "Session timestamp %s" % (ds))

	def get_table(ecu, args, n):
		def task():
			while True:
				info = ecu.send_command([0x72], [0x71, hds_tables[hds_table][0]], debug=args.debug)
				if info:
					data = unpack(hds_tables[hds_table][2], info[2][2:])
					d = log.row
					d['timestamp'] = time.time()
					d['hds_rpm'] = data[0]
					d['hds_tps_volt'] = data[1]
					d['hds_tps'] = data[2]
					d['hds_ect_volt'] = data[3]
					d['hds_ect'] = data[4]
					d['hds_iat_volt'] = data[5]
					d['hds_iat'] =data[6]
					d['hds_map_volt'] = data[7]
					d['hds_map'] = data[8]
					d['hds_unk1'] = data[9]
					d['hds_unk2'] = data[10]
					d['hds_battery_volt'] = data[11]
					d['hds_speed'] = data[12]
					d['hds_ign'] = data[13]
					if hds_table == 10:
						d['hds_unk3'] = data[14]
					else:
						d['hds_inj'] = data[14]
						d['hds_unk4'] = data[15]
					d.append()
					log.flush()
					n.notify("WATCHDOG=1")
					yield
		return cooperate(task())

	def flushLog(h5):
		h5.flush()

	t = get_table(ecu, args, n)

	lc = LoopingCall(flushLog, h5)
	lc.start(10)

	n.notify("READY=1")
	reactor.run()