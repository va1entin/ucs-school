#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention Management Console module:
#   Get csv class lists
#
# Copyright 2018 Univention GmbH
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

import csv
import StringIO

from univention.lib.i18n import Translation
from univention.management.console.modules.sanitizers import StringSanitizer
from univention.management.console.modules.decorators import sanitize


from ucsschool.lib.schoolldap import LDAP_Connection, SchoolBaseModule, SchoolSanitizer

_ = Translation('ucs-school-umc-lists').translate


class Instance(SchoolBaseModule):

	@sanitize(
		school=SchoolSanitizer(required=True),
		class_=StringSanitizer(required=True, allow_none=False),
	)
	@LDAP_Connection()
	def csv_list(self, request, ldap_user_read=None, ldap_position=None):
		school = request.options['school']
		class_ = request.options['class_']
		users = []
		for user in self._users(ldap_user_read, school, group=class_, user_type='student'):
			users.append({
				'username': user.get('username'),
				'vorname': user.get('firstname'),
				'nachname': user.get('lastname'),
				'klasse': class_,
			})
		csvfile = StringIO.StringIO()
		fieldnames = ['vorname', 'nachname', 'klasse', 'username']
		writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
		writer.writeheader()
		for user in users:
			writer.writerow(user)
		csvfile.seek(0)
		csv_data = csvfile.read()
		csvfile.close()
		result = {'name': school + ';' + class_ + '.csv', 'csv': csv_data}
		self.finished(request.id, result)
