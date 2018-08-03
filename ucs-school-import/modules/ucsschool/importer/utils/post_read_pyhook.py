# -*- coding: utf-8 -*-
#
# Univention UCS@school
"""
Base class for all Python based Post-Read-Pyhooks.
"""
# Copyright 2016-2018 Univention GmbH
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

from ucsschool.importer.utils.import_pyhook import ImportPyHook


class PostReadPyHook(ImportPyHook):
	"""
	Hook that is called directly after data has been read from CSV/...

	The base class' :py:meth:`__init__()` provides the following attributes:

	* self.lo          # LDAP object
	* self.logger      # Python logging instance

	If multiple hook classes are found, hook functions with higher
	priority numbers run before those with lower priorities. None disables
	a function.
	"""
	priority = {
		'entry_read': None,
	}

	def entry_read(self, entry_count, input_data, input_dict):
		"""
		Run code after an entry has been read and saved in
		input_data and input_dict. This hook may alter input_data
		and input_dict to modify the input data.

		:param int entry_count: index of the data entry (e.g. line of the CSV file)
		:param list[str] input_data: input data as raw as possible (e.g. raw CSV columns). The input_data may be changed.
		:param input_dict: input data mapped to column names. The input_dict may be changed.
		:type input_dict: dict[str, str]
		:return: None
		"""
		return None