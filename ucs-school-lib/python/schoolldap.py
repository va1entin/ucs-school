#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# UCS@school python lib
#
# Copyright 2007-2019 Univention GmbH
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

import re

import univention.uldap
from univention.config_registry import ConfigRegistry


ucr = ConfigRegistry()
ucr.load()


class SchoolSearchBase(object):
	"""Deprecated utility class that generates DNs of common school containers for a OU"""

	def __init__(self, availableSchools, school=None, dn=None, ldapBase=None):
		self._ldapBase = ldapBase or ucr.get('ldap/base')

		from ucsschool.lib.models import School
		self._school = school or availableSchools[0]
		self._schoolDN = dn or School.cache(self.school).dn

		# prefixes
		self._containerAdmins = ucr.get('ucsschool/ldap/default/container/admins', 'admins')
		self._containerStudents = ucr.get('ucsschool/ldap/default/container/pupils', 'schueler')
		self._containerStaff = ucr.get('ucsschool/ldap/default/container/staff', 'mitarbeiter')
		self._containerTeachersAndStaff = ucr.get('ucsschool/ldap/default/container/teachers-and-staff', 'lehrer und mitarbeiter')
		self._containerTeachers = ucr.get('ucsschool/ldap/default/container/teachers', 'lehrer')
		self._containerClass = ucr.get('ucsschool/ldap/default/container/class', 'klassen')
		self._containerRooms = ucr.get('ucsschool/ldap/default/container/rooms', 'raeume')
		self._examUserContainerName = ucr.get('ucsschool/ldap/default/container/exam', 'examusers')
		self._examGroupNameTemplate = ucr.get('ucsschool/ldap/default/groupname/exam', 'OU%(ou)s-Klassenarbeit')

		self.group_prefix_students = ucr.get('ucsschool/ldap/default/groupprefix/pupils', 'schueler-')
		self.group_prefix_teachers = ucr.get('ucsschool/ldap/default/groupprefix/teachers', 'lehrer-')
		self.group_prefix_admins = ucr.get('ucsschool/ldap/default/groupprefix/admins', 'admins-')
		self.group_prefix_staff = ucr.get('ucsschool/ldap/default/groupprefix/staff', 'mitarbeiter-')

	@classmethod
	def getOU(cls, dn):
		"""Return the school OU for a given DN.

			>>> SchoolSearchBase.getOU('uid=a,fou=bar,Ou=dc1,oU=dc,dc=foo,dc=bar')
			'dc1'
		"""
		school_dn = cls.getOUDN(dn)
		if school_dn:
			return univention.uldap.explodeDn(school_dn, True)[0]

	@classmethod
	def getOUDN(cls, dn):
		"""Return the School OU-DN part for a given DN.

			>>> SchoolSearchBase.getOUDN('uid=a,fou=bar,Ou=dc1,oU=dc,dc=foo,dc=bar')
			'Ou=dc1,oU=dc,dc=foo,dc=bar'
			>>> SchoolSearchBase.getOUDN('ou=dc1,ou=dc,dc=foo,dc=bar')
			'ou=dc1,ou=dc,dc=foo,dc=bar'
		"""
		match = cls._RE_OUDN.search(dn)
		if match:
			return match.group(1)
	_RE_OUDN = re.compile('(?:^|,)(ou=.*)$', re.I)

	@property
	def dhcp(self):
		return "cn=dhcp,%s" % self.schoolDN

	@property
	def policies(self):
		return "cn=policies,%s" % self.schoolDN

	@property
	def networks(self):
		return "cn=networks,%s" % self.schoolDN

	@property
	def school(self):
		return self._school

	@property
	def schoolDN(self):
		return self._schoolDN

	@property
	def users(self):
		return "cn=users,%s" % self.schoolDN

	@property
	def groups(self):
		return "cn=groups,%s" % self.schoolDN

	@property
	def workgroups(self):
		return "cn=%s,cn=groups,%s" % (self._containerStudents, self.schoolDN)

	@property
	def classes(self):
		return "cn=%s,cn=%s,cn=groups,%s" % (self._containerClass, self._containerStudents, self.schoolDN)

	@property
	def rooms(self):
		return "cn=%s,cn=groups,%s" % (self._containerRooms, self.schoolDN)

	@property
	def students(self):
		return "cn=%s,cn=users,%s" % (self._containerStudents, self.schoolDN)

	@property
	def teachers(self):
		return "cn=%s,cn=users,%s" % (self._containerTeachers, self.schoolDN)

	@property
	def teachersAndStaff(self):
		return "cn=%s,cn=users,%s" % (self._containerTeachersAndStaff, self.schoolDN)

	@property
	def staff(self):
		return "cn=%s,cn=users,%s" % (self._containerStaff, self.schoolDN)

	@property
	def admins(self):
		return "cn=%s,cn=users,%s" % (self._containerAdmins, self.schoolDN)

	@property
	def classShares(self):
		return "cn=%s,cn=shares,%s" % (self._containerClass, self.schoolDN)

	@property
	def shares(self):
		return "cn=shares,%s" % self.schoolDN

	@property
	def printers(self):
		return "cn=printers,%s" % self.schoolDN

	@property
	def computers(self):
		return "cn=computers,%s" % self.schoolDN

	@property
	def examUsers(self):
		return "cn=%s,%s" % (self._examUserContainerName, self.schoolDN)

	@property
	def globalGroupContainer(self):
		return "cn=ouadmins,cn=groups,%s" % (self._ldapBase,)

	@property
	def educationalDCGroup(self):
		return "cn=OU%s-DC-Edukativnetz,cn=ucsschool,cn=groups,%s" % (self.school, self._ldapBase)

	@property
	def educationalMemberGroup(self):
		return "cn=OU%s-Member-Edukativnetz,cn=ucsschool,cn=groups,%s" % (self.school, self._ldapBase)

	@property
	def administrativeDCGroup(self):
		return "cn=OU%s-DC-Verwaltungsnetz,cn=ucsschool,cn=groups,%s" % (self.school, self._ldapBase)

	@property
	def administrativeMemberGroup(self):
		return "cn=OU%s-Member-Verwaltungsnetz,cn=ucsschool,cn=groups,%s" % (self.school, self._ldapBase)

	@property
	def examGroupName(self):
		# replace '%(ou)s' strings in generic exam_group_name
		ucr_value_keywords = {'ou': self.school}
		return self._examGroupNameTemplate % ucr_value_keywords

	@property
	def examGroup(self):
		return "cn=%s,cn=ucsschool,cn=groups,%s" % (self.examGroupName, self._ldapBase)

	def isWorkgroup(self, groupDN):
		# a workgroup cannot lie in a sub directory
		if not groupDN.endswith(self.workgroups):
			return False
		return len(univention.uldap.explodeDn(groupDN)) - len(univention.uldap.explodeDn(self.workgroups)) == 1

	def isGroup(self, groupDN):
		return groupDN.endswith(self.groups)

	def isClass(self, groupDN):
		return groupDN.endswith(self.classes)

	def isRoom(self, groupDN):
		return groupDN.endswith(self.rooms)
