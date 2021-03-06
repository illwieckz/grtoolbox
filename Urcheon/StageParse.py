#! /usr/bin/env python3
#-*- coding: UTF-8 -*-

### Legal
#
# Author:  Thomas DEBESSE <dev@illwieckz.net>
# License: ISC
#

import __main__ as m
import argparse
import sys
import os
from collections import OrderedDict


class StageParse():
	def __init__(self, description=None):
		self.prog_name = os.path.basename(m.__file__)
		self.stage_dict = OrderedDict()
		self.stage = None

		self.description = description
		if self.description:
			self.description = description.replace("%(prog)s", self.prog_name)

	def addStage(self, stage_name, help=None):
		self.stage_dict[stage_name] = help
		setattr(self, stage_name, False)

	def printHelp(self, bad_stage=False, no_stage=False, lone_stage=False):
		print("usage: " + self.prog_name + " [-h] <stage> [stage arguments]")

		if bad_stage:
			print("")
			print(self.prog_name + ": error: unrecognized argument: " + bad_stage)
			sys.exit()

		if no_stage:
			print("")
			print(self.prog_name + ": error: missing stage")
			print("")
			print("  try: " + self.prog_name + " -h")
			sys.exit()

		if self.description:
			print("")
			print(self.description)

		print("")
		print("optional argument:")
		print("  -h, --help\tshow this help message and exit")

		if len(self.stage_dict.keys()) != 0:
			print("")
			print("stages:")
			for stage_name in self.stage_dict.keys():
				if self.stage_dict[stage_name]:
					len_column = len(" " + stage_name)
					if len_column < 23:
						print("{:<24}".format("  " + stage_name) + self.stage_dict[stage_name])
					else:
						print("  " + stage_name)
						print("{:<24}".format("") + self.stage_dict[stage_name])

				else:
					print("  " + stage_name)

		print("")
		print("stage options:")
		print("  try: " + self.prog_name + " stage -h")

		sys.exit()

	def parseArgs(self):
		if len(sys.argv) == 1:
			self.printHelp(no_stage=True)

		arg = sys.argv[1]

		if arg == "-h" or arg == "--help":
			self.printHelp()

		stage = arg

		if stage in self.stage_dict.keys():
			setattr(self, stage, True)
			self.stage = stage
		else:
			self.printHelp(bad_stage=stage)

		return self
