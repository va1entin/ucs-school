#!/usr/bin/python2.7

#
# Remove isOxUser flag from Examuser
#
# Depends: ucs-school-umc-exam
#
# Copyright 2017-2019 Univention GmbH
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

from ucsschool.exam.exam_user_pyhook import ExamUserPyHook


class NoOXExamUserPyHook(ExamUserPyHook):
	priority = {
		"pre_create": 10,
	}

	def pre_create(self, user_dn, al):
		"""
		Deactivate OX user flag.
		"""
		for num, (k, v) in enumerate(al):
			if k == 'isOxUser' and v == ['OK']:
				al[num] = (k, ['Not'])
				break
		return al
