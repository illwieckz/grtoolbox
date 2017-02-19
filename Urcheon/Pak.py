#! /usr/bin/env python3
#-*- coding: UTF-8 -*-

### Legal
#
# Author:  Thomas DEBESSE <dev@illwieckz.net>
# License: ISC
# 


from Urcheon import Action
from Urcheon import MapCompiler
from Urcheon import SourceTree
from Urcheon import Ui
import __main__ as m
import argparse
import logging
import multiprocessing
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from collections import OrderedDict


# TODO: replace with / os.path.sep when reading then replace os.path.sep to / when writing
# TODO: comment out missing files


class Builder():
	# testdir is the pk3dir, so the target here
	def __init__(self, source_dir, action_list, build_prefix=None, test_prefix=None, test_dir=None, game_name=None, map_profile=None, auto_actions=False, transient_dir=None, is_recursion=False, parallel=True):
		self.source_dir = source_dir
		self.action_list = action_list
		self.is_recursion = is_recursion
		self.parallel = parallel

		pak_config = SourceTree.Config(source_dir)
		self.test_dir = pak_config.getTestDir(build_prefix=build_prefix, test_prefix=test_prefix, test_dir=test_dir)

		if not game_name:
			game_name = pak_config.requireKey("game")

		self.game_name = game_name

		if not map_profile:
			map_config = MapCompiler.Config(source_dir, game_name=self.game_name)
			map_profile = map_config.requireDefaultProfile()
			self.map_profile = map_profile

		self.map_profile = map_profile


	def build(self, transient_dir=None):
		# TODO: check if not a directory
		if os.path.isdir(self.test_dir):
			logging.debug("found build dir: " + self.test_dir)
		else:
			logging.debug("create build dir: " + self.test_dir)
			os.makedirs(self.test_dir, exist_ok=True)

		logging.debug("reading build list from source dir: " + self.source_dir)

		for action in Action.Directory().directory:
			for file_path in self.action_list.active_action_dict[action.keyword]:
				# no need to use multiprocessing module to manage task contention, since each task will call its own process
				# using threads on one core is faster, and it does not prevent tasks to be able to use other cores

				# the is_recursion argument is just there to tell that action to not do specific stuff because recursion
				a = action(self.source_dir, self.test_dir, file_path, game_name=self.game_name, map_profile=self.map_profile, is_recursion=self.is_recursion)

				if not self.parallel:
					# explicitely requested (like in recursion)
					a.run()
				else:
					if not action.parallel:
						# action that can't be multithreaded
						a.run()
					else:
						thread = threading.Thread(target=a.run)

						while threading.active_count() > multiprocessing.cpu_count():
							pass

						thread.start()


class Packer():
	def __init__(self, source_dir, build_prefix=None, test_prefix=None, test_dir=None, pak_prefix=None, pak_file=None):
		pak_config = SourceTree.Config(source_dir)
		self.test_dir = pak_config.getTestDir(build_prefix=build_prefix, test_prefix=test_prefix, test_dir=test_dir)
		self.pak_file = pak_config.getPakFile(build_prefix=build_prefix, pak_prefix=pak_prefix, pak_file=pak_file)

	def createSubdirs(self, pak_file):
		pak_subdir = os.path.dirname(pak_file)
		if pak_subdir == "":
			pak_subdir = "."

		if os.path.isdir(pak_subdir):
			logging.debug("found pak subdir: " +  pak_subdir)
		else:
			logging.debug("create pak subdir: " + pak_subdir)
			os.makedirs(pak_subdir, exist_ok=True)

	def pack(self):
		if not os.path.isdir(self.test_dir):
			Ui.error("test pakdir not built")

		Ui.print("Packing " + self.test_dir + " to: " + self.pak_file)
		self.createSubdirs(self.pak_file)
		logging.debug("opening: " + self.pak_file)

		# remove existing file (do not write in place) to force the game engine to reread the file
		if os.path.isfile(self.pak_file):
			logging.debug("remove existing package: " + self.pak_file)
			os.remove(self.pak_file)

		pak = zipfile.ZipFile(self.pak_file, "w", zipfile.ZIP_DEFLATED)

		orig_dir = os.getcwd()
		# can't call --build and --package because of that:
		os.chdir(self.test_dir)
		for dirname, subdirname_list, file_name_list in os.walk('.'):
			for file_name in file_name_list:
				file_path = os.path.join(dirname, file_name)[len(os.path.curdir + os.path.sep):]
				Ui.print("adding file to package: " + file_path)
				pak.write(file_path)

		logging.debug("closing: " + self.pak_file)
		pak.close()

		Ui.print("Package written: " + self.pak_file)


class Cleaner():
	def __init__(self, source_dir, build_prefix=None, test_prefix=None, test_dir=None, pak_prefix=None, pak_file=None):
		pak_config = SourceTree.Config(source_dir)
		self.test_dir = pak_config.getTestDir(build_prefix=build_prefix, test_prefix=test_prefix, test_dir=test_dir)
		self.pak_prefix = pak_config.getPakPrefix(build_prefix=build_prefix, pak_prefix=pak_prefix)
		self.pak_name = pak_config.requireKey("name")

	def cleanTest(self):
		for dir_name, subdir_name_list, file_name_list in os.walk(self.test_dir):
			for file_name in file_name_list:
				that_file = dir_name + os.path.sep + file_name
				Ui.print("removing: " + that_file)
				os.remove(that_file)
				self.removeEmptyDir(dir_name)
			for dir_name in subdir_name_list:
				that_dir = dir_name + os.path.sep + dir_name
				self.removeEmptyDir(that_dir)
			self.removeEmptyDir(dir_name)
		self.removeEmptyDir(self.test_dir)

	def cleanPak(self):
		for dir_name, subdir_name_list, file_name_list in os.walk(self.pak_prefix):
			for file_name in file_name_list:
				if file_name.startswith(self.pak_name) and file_name.endswith(".pk3"):
					pak_file = dir_name + os.path.sep + file_name
					Ui.print("removing: " + pak_file)
					os.remove(pak_file)
					self.removeEmptyDir(dir_name)
		self.removeEmptyDir(self.pak_prefix)

	def cleanMap(self):
		for dir_name, subdir_name_list, file_name_list in os.walk(self.test_dir):
			for file_name in file_name_list:
				if dir_name.split("/")[-1:] == ["maps"] and file_name.endswith(os.path.extsep + "bsp"):
					bsp_file = dir_name + os.path.sep + file_name
					Ui.print("removing: " + bsp_file)
					os.remove(bsp_file)
					self.removeEmptyDir(dir_name)

				if dir_name.split("/")[-1:] == ["maps"] and file_name.endswith(os.path.extsep + "map"):
					map_file = dir_name + os.path.sep + file_name
					Ui.print("removing: " + map_file)
					os.remove(map_file)
					self.removeEmptyDir(dir_name)

				if dir_name.split("/")[-2:-1] == ["maps"] and file_name.startswith(os.path.extsep + "lm_"):
					lightmap_file = dir_name + os.path.sep + file_name
					Ui.print("removing: " + lightmap_file)
					os.remove(lightmap_file)
					self.removeEmptyDir(dir_name)

				if dir_name.split("/")[-1:] == ["maps"] and file_name.endswith(os.path.extsep + "navMesh"):
					navmesh_file = dir_name + os.path.sep + file_name
					Ui.print("removing: " + navmesh_file)
					os.remove(navmesh_file)
					self.removeEmptyDir(dir_name)

				if dir_name.split("/")[-1:] == ["minimaps"]:
					minimap_file = dir_name + os.path.sep + file_name
					Ui.print("removing: " + minimap_file)
					os.remove(minimap_file)
					self.removeEmptyDir(dir_name)

	def removeEmptyDir(self, dir_name):
		if os.path.isdir(dir_name):
			if os.listdir(dir_name) == []:
				os.rmdir(dir_name)


def main(stage=None):

	if stage:
		prog_name = os.path.basename(m.__file__) + " " + stage
	else:
		prog_name = os.path.basename(m.__file__)

	description = "%(prog)s is a pak builder for my lovely granger."

	args = argparse.ArgumentParser(description=description, prog=prog_name)
	args.add_argument("-D", "--debug", dest="debug", help="print debug information", action="store_true")
	args.add_argument("-v", "--verbose", dest="verbose", help="print verbose information", action="store_true")
	args.add_argument("-g", "--game", dest="game_name", metavar="GAMENAME", help="use game profile %(metavar)s")
	args.add_argument("-sd", "--source-dir", dest="source_dir", metavar="DIRNAME", default=".", help="build from directory %(metavar)s, default: %(default)s")
	args.add_argument("-bp", "--build-prefix", dest="build_prefix", metavar="DIRNAME", help="build in prefix %(metavar)s, example: build")
	args.add_argument("-tp", "--test-prefix", dest="test_prefix", metavar="DIRNAME", help="build test pakdir in prefix %(metavar)s, example: build/test")
	args.add_argument("-pp", "--pak-prefix", dest="pak_prefix", metavar="DIRNAME", help="build release pak in prefix %(metavar)s, example: build/pkg")
	args.add_argument("-td", "--test-dir", dest="test_dir", metavar="DIRNAME", help="build test pakdir as directory %(metavar)s")
	args.add_argument("-pf", "--pak-file", dest="pak_file", metavar="FILENAME", help="build release pak as file %(metavar)s")
	args.add_argument("-mp", "--map-profile", dest="map_profile", metavar="PROFILE", help="build map with profile %(metavar)s, default: %(default)s")
	args.add_argument("-u", "--update-actions", dest="update", help="compute actions, write down list", action="store_true")
	args.add_argument("-a", "--auto-actions", dest="auto_actions", help="compute actions at build time and do not store the list", action="store_true")

	group = args.add_mutually_exclusive_group()
	args.add_argument("-c", "--clean", dest="clean", help="clean all previous build", action="store_true")
	args.add_argument("-cm", "--clean_map", dest="clean_map", help="clean previous map build", action="store_true")
	args.add_argument("-ct", "--clean_test", dest="clean_test", help="clean previous test build", action="store_true")
	args.add_argument("-cp", "--clean_pak", dest="clean_pak", help="clean previous pak build", action="store_true")
	group.add_argument("-b", "--build", dest="build", help="build source pakdir", action="store_true")
	group.add_argument("-p", "--package", dest="package", help="compress release pak", action="store_true")

	args = args.parse_args()

	if args.debug:
		logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
		logging.debug("Debug logging activated")
		logging.debug("args: " + str(args))

	if args.verbose:
		Ui.verbosely = True

	action_list = None
	if args.update:
		action_list = Action.List(args.source_dir, args.game_name)
		action_list.updateActions()

	if args.build:
		if not action_list:
			action_list = Action.List(args.source_dir, args.game_name)
			action_list.readActions(auto_actions=args.auto_actions)
		builder = Builder(args.source_dir, action_list, build_prefix=args.build_prefix, test_prefix=args.test_prefix, test_dir=args.test_dir, game_name=args.game_name, map_profile=args.map_profile, auto_actions=args.auto_actions)
		builder.build()

	if args.package:
		packer = Packer(args.source_dir, build_prefix=args.build_prefix, test_prefix=args.test_prefix, test_dir=args.test_dir, pak_prefix=args.pak_prefix, pak_file=args.pak_file)
		packer.pack()

	if args.clean:
		cleaner = Cleaner(args.source_dir, build_prefix=args.build_prefix, test_prefix=args.test_prefix, test_dir=args.test_dir, pak_prefix=args.pak_prefix, pak_file=args.pak_file)
		cleaner.cleanTest()
		cleaner.cleanPak()

	if args.clean_map:
		cleaner = Cleaner(args.source_dir, build_prefix=args.build_prefix, test_prefix=args.test_prefix, test_dir=args.test_dir, pak_prefix=args.pak_prefix, pak_file=args.pak_file)
		cleaner.cleanMap()

	if args.clean_test:
		cleaner = Cleaner(args.source_dir, build_prefix=args.build_prefix, test_prefix=args.test_prefix, test_dir=args.test_dir, pak_prefix=args.pak_prefix, pak_file=args.pak_file)
		cleaner.cleanTest()

	if args.clean_pak:
		cleaner = Cleaner(args.source_dir, build_prefix=args.build_prefix, test_prefix=args.test_prefix, test_dir=args.test_dir, pak_prefix=args.pak_prefix, pak_file=args.pak_file)
		cleaner.cleanPak()


if __name__ == "__main__":
	main()
