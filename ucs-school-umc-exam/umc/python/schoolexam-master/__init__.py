#!/usr/bin/python2.7
#
# UCS@School UMC module schoolexam-master
#  UMC module delivering backend services for ucs-school-umc-exam
#
# Copyright 2013-2019 Univention GmbH
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
'''
UCS@School UMC module schoolexam-master
UMC module delivering backend services for ucs-school-umc-exam
'''

import datetime
import os.path
import traceback
import re
import os
from ldap.filter import filter_format
from collections import defaultdict

from univention.management.console.config import ucr
from univention.management.console.log import MODULE
from univention.management.console.modules import UMC_Error
from univention.management.console.modules.decorators import sanitize
from univention.management.console.modules.sanitizers import StringSanitizer, DNSanitizer, ListSanitizer
from ucsschool.lib.schoolldap import LDAP_Connection, SchoolBaseModule, ADMIN_WRITE, USER_READ
from ucsschool.lib.roles import role_teacher_computer, create_ucsschool_role_string
from ucsschool.lib.models import School, ComputerRoom, Student, ExamStudent, MultipleObjectsError, SchoolComputer
from ucsschool.lib.models.utils import add_module_logger_to_schoollib
from ucsschool.importer.utils.import_pyhook import ImportPyHookLoader
from ucsschool.exam.exam_user_pyhook import ExamUserPyHook

import univention.admin.uexceptions
import univention.admin.modules

from univention.lib.i18n import Translation
_ = Translation('ucs-school-umc-exam-master').translate
univention.admin.modules.update()

CREATE_USER_PRE_HOOK_DIR = '/usr/share/ucs-school-exam-master/pyhooks/create_exam_user_pre/'


class Instance(SchoolBaseModule):
	_pre_create_hooks = None

	def __init__(self):
		SchoolBaseModule.__init__(self)

		self._examUserPrefix = ucr.get('ucsschool/ldap/default/userprefix/exam', 'exam-')
		self._examGroupExcludeRegEx = None
		try:
			value = ucr.get('ucsschool/exam/group/ldap/blacklist/regex', '')
			if value.strip():
				self._examGroupExcludeRegEx = re.compile(value, re.I)
		except Exception as ex:
			MODULE.error('Failed to get/compile regexp provided by ucsschool/exam/group/ldap/blacklist/regex: %s' % (ex,))

		# cache objects
		self._udm_modules = dict()
		self._examGroup = None
		self._examUserContainerDN = None
		self.exam_user_pre_create_hooks = None

	def examGroup(self, ldap_admin_write, ldap_position, school):
		'''fetch the examGroup object, create it if missing'''
		if not self._examGroup:
			search_base = School.get_search_base(school)
			examGroup = search_base.examGroup
			examGroupName = search_base.examGroupName
			if 'groups/group' in self._udm_modules:
				module_groups_group = self._udm_modules['groups/group']
			else:
				module_groups_group = univention.admin.modules.get('groups/group')
				univention.admin.modules.init(ldap_admin_write, ldap_position, module_groups_group)
				self._udm_modules['groups/group'] = module_groups_group

			# Determine exam_group_dn
			try:
				ldap_filter = '(objectClass=univentionGroup)'
				ldap_admin_write.searchDn(ldap_filter, examGroup, scope='base')
				self._examGroup = module_groups_group.object(None, ldap_admin_write, ldap_position, examGroup)
				# self._examGroup.create() # currently not necessary
			except univention.admin.uexceptions.noObject:
				try:
					position = univention.admin.uldap.position(ldap_position.getBase())
					position.setDn(ldap_admin_write.parentDn(examGroup))
					self._examGroup = module_groups_group.object(None, ldap_admin_write, position)
					self._examGroup.open()
					self._examGroup['name'] = examGroupName
					self._examGroup['sambaGroupType'] = self._examGroup.descriptions['sambaGroupType'].base_default[0]
					self._examGroup.create()
				except univention.admin.uexceptions.base:
					raise UMC_Error(_('Failed to create exam group\n%s') % traceback.format_exc())

		return self._examGroup

	def examUserContainerDN(self, ldap_admin_write, ldap_position, school):
		'''lookup examUserContainerDN, create it if missing'''
		if not self._examUserContainerDN:
			search_base = School.get_search_base(school)
			examUsers = search_base.examUsers
			examUserContainerName = search_base._examUserContainerName
			try:
				ldap_admin_write.searchDn('(objectClass=organizationalRole)', examUsers, scope='base')
			except univention.admin.uexceptions.noObject:
				try:
					module_containers_cn = univention.admin.modules.get('container/cn')
					univention.admin.modules.init(ldap_admin_write, ldap_position, module_containers_cn)
					position = univention.admin.uldap.position(ldap_position.getBase())
					position.setDn(ldap_admin_write.parentDn(examUsers))
					exam_user_container = module_containers_cn.object(None, ldap_admin_write, position)
					exam_user_container.open()
					exam_user_container['name'] = examUserContainerName
					exam_user_container.create()
				except univention.admin.uexceptions.base:
					raise UMC_Error(_('Failed to create exam container\n%s') % traceback.format_exc())

			self._examUserContainerDN = examUsers

		return self._examUserContainerDN

	@sanitize(
		userdn=StringSanitizer(required=True),
		room=StringSanitizer(required=True),
		description=StringSanitizer(default=''),
		school=StringSanitizer(default='')
	)
	@LDAP_Connection(USER_READ, ADMIN_WRITE)
	def create_exam_user(self, request, ldap_user_read=None, ldap_admin_write=None, ldap_position=None):
		'''Create an exam account cloned from a given user account.
		The exam account is added to a special exam group to allow GPOs and other restrictions
		to be enforced via the name of this group.
		The group has to be created earlier, e.g. by create_ou (ucs-school-import).
		'''

		school = request.options['school']
		userdn = request.options['userdn']
		room_dn = request.options['room']
		try:
			user = Student.from_dn(userdn, None, ldap_admin_write)
		except univention.admin.uexceptions.noObject:
			raise UMC_Error(_('Student %r not found.') % (userdn,))
		except univention.admin.uexceptions.ldapError:
			raise
		try:
			room = ComputerRoom.from_dn(room_dn, None, ldap_user_read)
		except univention.admin.uexceptions.noObject:
			raise UMC_Error('Room %r not found.' % (room_dn,))
		except univention.admin.uexceptions.ldapError:
			raise

		user_orig = user.get_udm_object(ldap_admin_write)

		# uid and DN of exam_user
		exam_user_uid = "".join((self._examUserPrefix, user_orig['username']))
		exam_user_dn = "uid=%s,%s" % (exam_user_uid, self.examUserContainerDN(ldap_admin_write, ldap_position, user.school or school))

		try:
			exam_user = ExamStudent.get_only_udm_obj(ldap_admin_write, filter_format('uid=%s', (exam_user_uid,)))
			if exam_user is None:
				raise univention.admin.uexceptions.noObject(exam_user_uid)
			exam_user = ExamStudent.from_udm_obj(exam_user, None, ldap_admin_write)
		except (univention.admin.uexceptions.noObject, MultipleObjectsError):
			pass  # we need to create the exam user
		else:
			if school not in exam_user.schools:
				exam_user.schools.append(school)
				exam_user.modify(ldap_admin_write)
			MODULE.warn(_('The exam account does already exist for: %s') % exam_user_uid)
			self.finished(request.id, dict(
				success=True,
				userdn=userdn,
				examuserdn=exam_user.dn,
			))
			return

		# Check if it's blacklisted
		for prohibited_object in univention.admin.handlers.settings.prohibited_username.lookup(None, ldap_admin_write, ''):
			if exam_user_uid in prohibited_object['usernames']:
				raise UMC_Error(_('Requested exam username %s is not allowed according to settings/prohibited_username object %s') % (exam_user_uid, prohibited_object['name']))

		# Allocate new uid
		alloc = []
		try:
			uid = univention.admin.allocators.request(ldap_admin_write, ldap_position, 'uid', value=exam_user_uid)
			alloc.append(('uid', uid))
		except univention.admin.uexceptions.noLock:
			univention.admin.allocators.release(ldap_admin_write, ldap_position, 'uid', exam_user_uid)
			MODULE.warn(_('The exam account does already exist for: %s') % exam_user_uid)
			self.finished(request.id, dict(
				success=True,
				userdn=userdn,
				examuserdn=exam_user_dn,
			), success=True)
			return

		# Ok, we have a valid target uid, so start cloning the user
		# deepcopy(user_orig) does not help much, as we cannot use users.user.object.create()
		# because it currently cannot be convinced to preserve the password. So we do it manually:
		try:
			# Allocate new uidNumber
			uidNum = univention.admin.allocators.request(ldap_admin_write, ldap_position, 'uidNumber')
			alloc.append(('uidNumber', uidNum))

			# Allocate new sambaSID
			# code copied from users.user.object.__generate_user_sid:
			userSid = None
			if user_orig.s4connector_present:
				# In this case Samba 4 must create the SID, the s4 connector will sync the
				# new sambaSID back from Samba 4.
				userSid = 'S-1-4-%s' % uidNum
			else:
				try:
					userSid = univention.admin.allocators.requestUserSid(ldap_admin_write, ldap_position, uidNum)
				except:
					pass
			if not userSid or userSid == 'None':
				num = uidNum
				while not userSid or userSid == 'None':
					num = str(int(num) + 1)
					try:
						userSid = univention.admin.allocators.requestUserSid(ldap_admin_write, ldap_position, num)
					except univention.admin.uexceptions.noLock:
						num = str(int(num) + 1)
				alloc.append(('sid', userSid))

			# Determine description attribute for exam_user
			exam_user_description = request.options.get('description')
			if not exam_user_description:
				exam_user_description = _('Exam for user %s') % user_orig['username']

			def getBlacklistSet(ucrvar):
				"""
				>>> set([ x.replace('||','|') for x in re.split('(?<![|])[|](?![|])', '|My|new|Value|with|Pipe||symbol') if x ])
				set(['with', 'new', 'My', 'Value', 'Pipe|symbol'])
				"""
				return set([x.replace('||', '|') for x in re.split('(?<![|])[|](?![|])', ucr.get(ucrvar, '')) if x])

			blacklisted_attributes = getBlacklistSet('ucsschool/exam/user/ldap/blacklist')

			# Now create the addlist, fixing up attributes as we go
			al = []
			foundUniventionObjectFlag = False
			for (key, value) in user_orig.oldattr.items():
				# ignore blacklisted attributes
				if key in blacklisted_attributes:
					continue
				# ignore blacklisted attribute values
				keyBlacklist = getBlacklistSet('ucsschool/exam/user/ldap/blacklist/%s' % key)
				value = [x for x in value if x not in keyBlacklist]
				if not value:
					continue
				# handle special cases
				if key == 'uid':
					value = [exam_user_uid]
				elif key == 'objectClass':
					value += ['ucsschoolExam']
				elif key == 'ucsschoolSchool' and school:  # for backwards compatibility with UCS@school < 4.1R2 school might not be set
					value = [school]
				elif key == 'homeDirectory':
					user_orig_homeDirectory = value[0]
					_tmp_split_path = user_orig_homeDirectory.rsplit(os.path.sep, 1)
					if len(_tmp_split_path) != 2:
						english_error_detail = "Failed parsing homeDirectory of original user: %s" % (user_orig_homeDirectory,)
						message = _('ERROR: Creation of exam user account failed\n%s') % (english_error_detail,)
						raise UMC_Error(message)
					exam_user_unixhome = '%s.%s' % (exam_user_uid, datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
					value = [os.path.join(_tmp_split_path[0], 'exam-homes', exam_user_unixhome)]
				elif key == 'sambaHomePath':
					user_orig_sambaHomePath = value[0]
					value = [user_orig_sambaHomePath.replace(user_orig['username'], exam_user_uid)]
				elif key == 'krb5PrincipalName':
					user_orig_krb5PrincipalName = value[0]
					value = ["%s%s" % (exam_user_uid, user_orig_krb5PrincipalName[user_orig_krb5PrincipalName.find("@"):])]
				elif key == 'uidNumber':
					value = [uidNum]
				elif key == 'sambaSID':
					value = [userSid]
				elif key == 'description':
					value = [exam_user_description]
					exam_user_description = None  # that's done
				elif key == 'univentionObjectFlag':
					foundUniventionObjectFlag = True
					if 'temporary' not in value:
						value += ['temporary']
				al.append((key, value))
				al.append(('sambaUserWorkstations', ','.join([c.name for c in room.get_computers(ldap_admin_write)])))

			if not foundUniventionObjectFlag and 'univentionObjectFlag' not in blacklisted_attributes:
				al.append(('univentionObjectFlag', ['temporary']))

			if exam_user_description and 'description' not in blacklisted_attributes:
				al.append(('description', [exam_user_description]))

			# call hook scripts
			al = self.run_pre_create_hooks(exam_user_dn, al, ldap_admin_write)

			# And create the exam_user
			ldap_admin_write.add(exam_user_dn, al)

		except BaseException:  # noqa
			for i, j in alloc:
				univention.admin.allocators.release(ldap_admin_write, ldap_position, i, j)
			MODULE.error('Creation of exam user account failed: %s' % (traceback.format_exc(),))
			raise

		# finally confirm allocated IDs
		univention.admin.allocators.confirm(ldap_admin_write, ldap_position, 'uid', exam_user_uid)
		univention.admin.allocators.confirm(ldap_admin_write, ldap_position, 'sid', userSid)
		univention.admin.allocators.confirm(ldap_admin_write, ldap_position, 'uidNumber', uidNum)

		self.finished(request.id, dict(
			success=True,
			userdn=userdn,
			examuserdn=exam_user_dn,
		))

	@sanitize(
		users=ListSanitizer(DNSanitizer(required=True), required=True),
		school=StringSanitizer(required=True)
	)
	@LDAP_Connection(USER_READ, ADMIN_WRITE)
	def add_exam_users_to_groups(self, request, ldap_user_read=None, ldap_admin_write=None, ldap_position=None):
		"""
		Add previously created exam users to groups.
		"""
		groups = defaultdict(dict)
		exam_group = self.examGroup(ldap_admin_write, ldap_position, request.options['school'])

		for user_dn in request.options['users']:
			try:
				ori_student = Student.from_dn(user_dn, None, ldap_admin_write)
				exam_user_uid = ''.join((self._examUserPrefix, ori_student.name))
				exam_student = ExamStudent.get_only_udm_obj(ldap_admin_write, filter_format('uid=%s', (exam_user_uid,)))
			except univention.admin.uexceptions.noObject as exc:
				raise UMC_Error(_('Student %(user_dn)r or exam user not found: %(exc)r.') % {'user_dn': user_dn, 'exc': exc})
			except univention.admin.uexceptions.ldapError:
				raise

			udm_ori_student = ori_student.get_udm_object(ldap_admin_write)
			groups[udm_ori_student['primaryGroup']].setdefault('dns', set()).add(exam_student.dn)
			groups[udm_ori_student['primaryGroup']].setdefault('uids', set()).add(exam_student['username'])
			for grp in udm_ori_student.info.get('groups', []):
				groups[grp].setdefault('dns', set()).add(exam_student.dn)
				groups[grp].setdefault('uids', set()).add(exam_student['username'])

			groups[exam_group.dn].setdefault('dns', set()).add(exam_student.dn)
			groups[exam_group.dn].setdefault('uids', set()).add(exam_student['username'])

			if 'groups/group' not in self._udm_modules:
				self._udm_modules['groups/group'] = univention.admin.modules.get('groups/group')
				univention.admin.modules.init(ldap_admin_write, ldap_position, self._udm_modules['groups/group'])
			module_groups_group = self._udm_modules['groups/group']

		for group_dn, users in groups.items():
			if self._examGroupExcludeRegEx and self._examGroupExcludeRegEx.search(group_dn):
				MODULE.info('create_exam_user(): ignoring group %r as requested via regexp' % (group_dn,))
				continue
			grpobj = module_groups_group.object(None, ldap_admin_write, ldap_position, group_dn)
			MODULE.info('Adding users %r to group %r...' % (users['uids'], group_dn))
			grpobj.fast_member_add(users['dns'], users['uids'])

		self.finished(request.id, None)

	@sanitize(
		userdn=StringSanitizer(required=True),
		school=StringSanitizer(default=''),
	)
	@LDAP_Connection(USER_READ, ADMIN_WRITE)
	def remove_exam_user(self, request, ldap_user_read=None, ldap_admin_write=None):
		'''Remove an exam account cloned from a given user account.
		The exam account is removed from the special exam group.'''

		userdn = request.options['userdn']
		school = request.options['school']
		try:
			user = ExamStudent.from_dn(userdn, None, ldap_user_read)
		except univention.admin.uexceptions.noObject:
			raise UMC_Error(_('Exam student %r not found.') % (userdn,))
		except univention.admin.uexceptions.ldapError:
			raise

		try:
			schools = None
			if school:
				schools = list(set(user.schools) - set([school]))
			if schools:
				MODULE.warn('User %s will not be removed as he currently participates in another exam.' % (user.dn,))
				user.schools = schools
				user.modify(ldap_admin_write)
			else:
				user.remove(ldap_admin_write)
		except univention.admin.uexceptions.ldapError as exc:
			raise UMC_Error(_('Could not remove exam user %r: %s') % (userdn, exc,))

		self.finished(request.id, {}, success=True)

	@sanitize(
		roomdn=StringSanitizer(required=True),
		school=StringSanitizer(default=''),
	)
	@LDAP_Connection(USER_READ, ADMIN_WRITE)
	def set_computerroom_exammode(self, request, ldap_user_read=None, ldap_admin_write=None, ldap_position=None):
		'''Add all member hosts except teacher_computers of a given computer room to the special exam group.'''

		roomdn = request.options['roomdn']
		try:
			room = ComputerRoom.from_dn(roomdn, None, ldap_user_read)
		except univention.admin.uexceptions.noObject:
			raise UMC_Error('Room %r not found.' % (roomdn,))
		except univention.admin.uexceptions.ldapError:
			raise

		teacher_pc_role = create_ucsschool_role_string(role_teacher_computer, room.school)
		exam_hosts = list()
		for host in room.hosts:
			host_obj = SchoolComputer.from_dn(host, None, ldap_user_read) # Please remove with Bug #49611
			host_obj = SchoolComputer.from_dn(host, None, ldap_user_read)
			if teacher_pc_role not in host_obj.ucsschool_roles:
				exam_hosts.append(host)
		# Add all host members of room to examGroup
		host_uid_list = [univention.admin.uldap.explodeDn(uniqueMember, 1)[0] + '$' for uniqueMember in exam_hosts]
		examGroup = self.examGroup(ldap_admin_write, ldap_position, room.school)
		examGroup.fast_member_add(exam_hosts, host_uid_list)  # adds any uniqueMember and member listed if not already present

		self.finished(request.id, {}, success=True)

	@sanitize(
		roomdn=StringSanitizer(required=True),
		school=StringSanitizer(default=''),
	)
	@LDAP_Connection(USER_READ, ADMIN_WRITE)
	def unset_computerroom_exammode(self, request, ldap_user_read=None, ldap_admin_write=None, ldap_position=None):
		'''Remove all member hosts of a given computer room from the special exam group.'''

		roomdn = request.options['roomdn']
		try:
			room = ComputerRoom.from_dn(roomdn, None, ldap_user_read)
		except univention.admin.uexceptions.noObject:
			raise UMC_Error('Room %r not found.' % (roomdn,))
		except univention.admin.uexceptions.ldapError:
			raise

		# Remove all host members of room from examGroup
		host_uid_list = [univention.admin.uldap.explodeDn(uniqueMember, 1)[0] + '$' for uniqueMember in room.hosts]
		examGroup = self.examGroup(ldap_admin_write, ldap_position, room.school)
		examGroup.fast_member_remove(room.hosts, host_uid_list)  # removes any uniqueMember and member listed if still present

		self.finished(request.id, {}, success=True)

	def run_pre_create_hooks(self, exam_user_dn, al, ldap_admin_write):
		if not self.exam_user_pre_create_hooks:
			add_module_logger_to_schoollib()
			pyhook_loader = ImportPyHookLoader(CREATE_USER_PRE_HOOK_DIR)
			hooks = pyhook_loader.init_hook(ExamUserPyHook, lo=ldap_admin_write, dry_run=False)
			self.exam_user_pre_create_hooks = hooks.get('pre_create', [])

		for hook in self.exam_user_pre_create_hooks:
			al = hook(exam_user_dn, al)

		return al
