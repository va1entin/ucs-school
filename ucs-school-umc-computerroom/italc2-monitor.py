#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console module:
#   Control computers of pupils in a room
#
# Copyright 2012 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import inspect
import os
import sys
import notifier
import optparse

script_dir = os.path.abspath( os.path.dirname( inspect.getfile(inspect.currentframe() ) ) )
sys.path.insert( 0, os.path.join( script_dir, 'umc/python/computerroom' ) )

import italc2
import ucsschool.lib.schoolldap as usl

import univention.config_registry as ucr

def show_state():
	FORMAT = '%(name)-15s %(description)-15s %(user)-20s %(ScreenLock)-14s %(InputLock)-13s %(MessageBox)-8s %(DemoServer)-8s %(DemoClient)-8s %(Flags)5s'
	# clear screen and set position to HOME
	print '\033[2J\033[H'
	# print '##################'
	print FORMAT % { 'name' : 'Name', 'description' : 'Description', 'user' : 'User', 'ScreenLock' : 'Screen locked', 'InputLock' : 'Input locked', 'MessageBox' : 'Message', 'DemoServer' : 'Server', 'DemoClient' : 'Client', 'Flags' : 'Flags' }
	print 120*'-'
	for name, comp in m.items():
		info = { 'name' : name, 'description' : comp.description or '<none>', 'user' : comp.user.current is None and '<unknown>' or comp.user.current }
		info.update( comp.states )
		info[ 'Flags' ] = comp.flags.current is None and '<not set>' or comp.flags.current
		print FORMAT % info
	return True

if __name__ == '__main__':
	config = ucr.ConfigRegistry()
	config.load()

	notifier.init()

	parser = optparse.OptionParser()
	parser.add_option( '-s', '--school', dest = 'school', default = '711' )
	parser.add_option( '-r', '--room', dest = 'room', default = 'room01' )
	parser.add_option( '-u', '--username', dest = 'username', default = 'Administrator' )
	parser.add_option( '-p', '--password', dest = 'password', default = 'univention' )
	options, args = parser.parse_args()

	usl.set_credentials( 'uid=%s,cn=users,%s' % ( options.username, config.get( 'ldap/base' ) ), options.password )

	m = italc2.ITALC_Manager()
	m.school = options.school
	m.room = options.room

	show_state()
	notifier.timer_add( 1000, show_state )

	notifier.loop()
