#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console module:
#  UCS@school Import helper
#
# Copyright 2014 Univention GmbH
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

from datetime import datetime, date
import traceback
import ldap.filter
import csv
import random
import string
import ldap

import univention.admin.uldap as udm_uldap
from univention.admin.filter import conjunction, expression
from univention.admin.uexceptions import noObject
from univention.config_registry import ConfigRegistry
import univention.admin.modules as udm_modules

from univention.management.console.log import MODULE
from univention.lib.i18n import Translation

from ucsschool.lib.schoolldap import SchoolSearchBase

_ = Translation('ucs-school-umc-csv-import').translate

ucr = ConfigRegistry()
ucr.load()

def generate_random(length=30):
	chars = string.ascii_letters + string.digits
	return ''.join(random.choice(chars) for x in range(length))

class DNHandling(object):
	cache = {}

	@classmethod
	def get(cls, school):
		if school not in cls.cache:
			cls.cache[school] = cls(school)
		return cls.cache[school]

	def __init__(self, school):
		self.search_base = SchoolSearchBase([], school)

	def get_school_dn(self):
		return self.search_base.schoolDN

	def get_group_container(self):
		return self.search_base.groups

	def get_classes_container(self):
		return self.search_base.classes

	def get_students_container(self):
		return self.search_base.students

	def get_teachers_container(self):
		return self.search_base.teachers

	def get_staff_container(self):
		return self.search_base.staff

	def get_teachers_and_staff_container(self):
		return self.search_base.teachersAndStaff

	def get_group_dn(self, group_name):
		return 'cn=%s,%s' % (group_name, self.get_group_container())

	def get_class_dn(self, class_name):
		return 'cn=%s,%s' % (class_name, self.get_classes_container())

	def is_school_class(self, group_dn):
		parent_dn = ','.join(ldap.explode_dn(group_dn)[1:])
		return self.get_classes_container() == parent_dn

	def get_shares_container(self):
		return self.search_base.classShares

	def get_share_dn(self, share_name):
		return 'cn=%s,%s' % (share_name, self.get_shares_container())

class User(object):
	columns = ['action', 'username', 'firstname', 'lastname', 'birthday', 'email', 'password', 'line']
	column_labels = {
		'username' : (_('Username'), 'Username'),
		'firstname' : (_('First name'), 'First name'),
		'lastname' : (_('Last name'), 'Last name'),
		'birthday' : (_('Birthday'), 'Birthday'),
		'email' : (_('Email'), 'Email'),
		# no password!
		# no line!
		# no action!
	}
	required_columns = ['action', 'username', 'firstname', 'lastname']
	should_not_change_columns = ['firstname', 'lastname', 'birthday', 'email']

	additional_columns = [] # may be overwritten
	additional_column_labels = {} # may be overwritten
	additional_required_columns = [] # may be overwritten
	additional_should_not_change_columns = [] # may be overwritten

	supports_school_classes = False

	def __init__(self, lo, school, date_format, attrs):
		self._udm_obj_searched = False
		self._udm_obj = None
		self._error_msg = None
		if school:
			school = ldap.filter.escape_filter_chars(school)
		self.school = school
		self.date_format = date_format
		for column in self.get_columns():
			value = attrs.get(column)
			if column in ['birthday']:
				value = self.format_date(value)
			if isinstance(value, basestring):
				value = ldap.filter.escape_filter_chars(value)
			setattr(self, column, value)
		self.username = self.guess_username(lo)
		if 'action' not in attrs:
			if self.exists(lo):
				self.action = 'modify'
			else:
				self.action = 'create'
		self.errors = {}
		self.warnings = {}

	def unformat_date(self, value):
		try:
			date_obj = datetime.strptime(value, self.date_format)
			if '%y' in self.date_format:
				# date format has only 2 year digits
				# so 01.01.40 -> 2040-01-01 which is not wanted
				if date_obj > datetime.now():
					date_obj = date(date_obj.year - 100, date_obj.month, date_obj.day)
			return date_obj.strftime('%Y-%m-%d')
		except (TypeError, ValueError):
			return value

	def format_date(self, value):
		try:
			return datetime.strptime(value, '%Y-%m-%d').strftime(self.date_format)
		except (TypeError, ValueError):
			return value

	def exists(self, lo):
		return self.get_udm_object(lo) is not None

	def exists_but_not_in_school(self, lo):
		if self.exists(lo):
			return ('ou=%s,' % self.school) not in self.get_udm_object(lo).dn
		return False

	def guess_username(self, lo):
		# already provided. use this one
		if self.username:
			return self.username

		# search database
		hints = []
		if self.lastname:
			hints.append(expression('lastname', self.lastname))
			if self.firstname:
				hints.append(expression('firstname', self.firstname))
			if self.birthday:
				hints.append(expression('birthday', self.unformat_date(self.birthday)))
		if hints:
			ldap_filter = conjunction('&', hints)
			try:
				udm_obj = udm_modules.lookup('users/user', None, lo, scope='sub', base=ucr.get('ldap/base'), filter=str(ldap_filter))[0]
			except IndexError:
				pass
			else:
				return udm_obj['username']

		# generate a reasonable one
		firstname = ''
		if self.firstname:
			firstname = self.firstname.split()[0].lower() + '.'
		lastname = ''
		if self.lastname:
			lastname = self.lastname.split()[-1].lower()
		return firstname + lastname

	def merge_additional_group_changes(self, lo, changes, group_cache, all_found_classes, without_school_classes=False):
		if self.action not in ['create', 'modify']:
			return
		udm_obj = self.get_udm_object(lo)
		udm_obj.open()
		dn = udm_obj.dn
		all_groups = self.groups_for_ucs_school(lo, group_cache, all_found_classes, without_school_classes=without_school_classes)
		my_groups = self.groups_used(lo, group_cache)
		for group in all_groups:
			if group in my_groups:
				continue
			group_change = changes.setdefault(group, {'add' : [], 'remove' : []})
			group_change['remove'].append(dn)
		for group in my_groups:
			group_change = changes.setdefault(group, {'add' : [], 'remove' : []})
			group_change['add'].append(dn)

	def get_specific_groups(self):
		return []

	@classmethod
	def bulk_group_change(cls, lo, school, group_changes):
		for group_dn, group_changes in group_changes.iteritems():
			MODULE.process('Changing group memberships for %s' % group_dn)
			MODULE.info('Changes: %r' % group_changes)

			# do not use the group cache. get a fresh instance from database
			group_obj = cls.get_or_create_group(group_dn, lo, school, {})
			group_obj.open()
			group_users = group_obj['users'][:]
			MODULE.info('Members already present: %s' % ', '.join(group_users))

			for remove in group_changes['remove']:
				if remove in group_users:
					MODULE.info('Removing %s from %s' % (remove, group_dn))
					group_users.remove(remove)
			for add in group_changes['add']:
				if add not in group_users:
					MODULE.info('Adding %s to %s' % (add, group_dn))
					group_users.append(add)
			group_obj['users'] = group_users
			group_obj.modify()

	@classmethod
	def is_header(cls, line, dialect):
		real_column = 0
		if line:
			reader = csv.reader([line], dialect)
			columns = reader.next()
			for column in columns:
				found_column = cls.find_column(column, 0)
				if not found_column.startswith('unused'):
					real_column += 1
		# at least 2: Prevent false positives because of someone
		# called Mr. Line
		return real_column > 1

	@classmethod
	def get_columns(cls):
		columns = []
		columns.extend(cls.columns)
		columns.extend(cls.additional_columns)
		return columns

	@classmethod
	def get_column_labels(cls):
		column_labels = {}
		column_labels.update(cls.column_labels)
		column_labels.update(cls.additional_column_labels)
		return column_labels

	@classmethod
	def get_required_columns(cls):
		required_columns = []
		required_columns.extend(cls.required_columns)
		required_columns.extend(cls.additional_required_columns)
		return required_columns

	@classmethod
	def get_should_not_change_columns(cls):
		should_not_change_columns = []
		should_not_change_columns.extend(cls.should_not_change_columns)
		should_not_change_columns.extend(cls.additional_should_not_change_columns)
		return should_not_change_columns

	@classmethod
	def find_column(self, column, i):
		for column_name, column_labels in self.get_column_labels().iteritems():
			if column in column_labels:
				return column_name
		return 'unused%d' % i

	@classmethod
	def get_columns_for_assign(cls):
		columns = [{'name' : 'unused', 'label' : _('Unused')}]
		columns.extend(cls.get_columns_for_frontend(cls.get_columns()))
		return columns

	@classmethod
	def get_columns_for_spreadsheet(cls, column_names):
		columns = [{'name' : 'action', 'label' : _('Action')}]
		columns.extend(cls.get_columns_for_frontend(column_names))
		columns.append({'name' : 'line', 'label' : _('Line')})
		return columns

	@classmethod
	def get_columns_for_frontend(cls, column_names):
		columns = []
		for column in column_names:
			if column in cls.get_column_labels():
				columns.append({'name' : column, 'label' : cls.get_column_label(column)})
		return columns

	@classmethod
	def get_column_label(cls, column):
		try:
			return cls.get_column_labels()[column][0]
		except (KeyError, IndexError):
			return column

	def validate(self, lo):
		self.errors.clear()
		self.warnings.clear()
		for column in self.get_required_columns():
			if getattr(self, column) is None:
				self.add_error(column, _('"%s" is required. Please provide this information.') % self.get_column_label(column))
		if self.exists(lo):
			if self.action == 'create':
				self.add_error('action', _('The user already exists and cannot be created. Please change the username to one that does not yet exist or change the action to be taken.'))
			if self.exists_but_not_in_school(lo):
				self.add_error('username', _('The username is already used somewhere outside the school. It may not be taken twice and has to be changed.'))
			elif self.action == 'modify':
				# do not do this if the user exists somewhere
				udm_obj = self.get_udm_object(lo)
				from_udm_obj = self.from_udm_obj(udm_obj, lo, self.school, self.date_format)
				for column in self.get_should_not_change_columns():
					new_value = getattr(self, column)
					old_value = getattr(from_udm_obj, column)
					if new_value and old_value:
						if new_value != old_value:
							self.add_warning(column, _('The value changed from %(old)s. This seems unlikely.') % {'old' : old_value})
		else:
			if self.action == 'modify':
				self.add_error('action', _('The user does not yet exist and cannot be modified. Please change the username to one that exists or change the action to be taken.'))
			if self.action == 'delete':
				self.add_error('action', _('The user does not yet exist and cannot be deleted. Please change the username to one that exists or change the action to be taken.'))

	def add_warning(self, attribute, warning_message):
		warnings = self.warnings.setdefault(attribute, [])
		if warning_message not in warnings:
			warnings.append(warning_message)

	def add_error(self, attribute, error_message):
		errors = self.errors.setdefault(attribute, [])
		if error_message not in errors:
			errors.append(error_message)

	def commit(self, lo, group_cache):
		self.validate(lo)
		self._error_msg = None
		if self.errors:
			for field, errors in self.errors.iteritems():
				self._error_msg = errors[0]
			return False
		try:
			if self.action == 'create':
				self.commit_create(lo, group_cache)
			elif self.action == 'modify':
				self.commit_modify(lo, group_cache)
			elif self.action == 'delete':
				self.commit_delete(lo)
		except Exception as exc:
			MODULE.warn('Something went wrong. %s' % traceback.format_exc())
			self._error_msg = str(exc)
			return False
		else:
			return True

	def get_user_base(self):
		return self.get_user_base_for_school(self.school)

	@classmethod
	def get_user_base_for_school(cls, school):
		return None

	@classmethod
	def get_class_group_base(self, school):
		return DNHandling.get(school).get_classes_container()

	def get_group_dn(self, group_name):
		return DNHandling.get(self.school).get_group_dn(group_name)

	def get_class_dn(self, class_name):
		return DNHandling.get(self.school).get_class_dn(class_name)

	def primary_group(self, lo, group_cache):
		dn = self.get_group_dn('Domain Users %s' % self.school)
		return self.get_or_create_group(dn, lo, self.school, group_cache).dn

	def commit_create(self, lo, group_cache):
		pos = udm_uldap.position(ucr.get('ldap/base'))
		pos.setDn(self.get_user_base())
		udm_obj = udm_modules.get('users/user').object(None, lo, pos)
		udm_obj.open()
		udm_obj['username'] = self.username
		udm_obj['password'] = self.password or generate_random()
		udm_obj['primaryGroup'] = self.primary_group(lo, group_cache)
		self._alter_udm_obj(udm_obj, lo, group_cache)
		udm_obj.create()
		return udm_obj

	def commit_modify(self, lo, group_cache):
		udm_obj = self.get_udm_object(lo)
		udm_obj.open()
		self._alter_udm_obj(udm_obj, lo, group_cache)
		udm_obj.modify()
		rdn = lo.explodeDn(udm_obj.dn)[0]
		dest = '%s,%s' % (rdn, self.get_user_base())
		if dest != udm_obj.dn:
			udm_obj.move(dest)
		return udm_obj

	def _alter_udm_obj(self, udm_obj, lo, group_cache):
		udm_obj['firstname'] = self.firstname
		udm_obj['lastname'] = self.lastname
		birthday = self.birthday
		if birthday:
			birthday = self.unformat_date(birthday)
			udm_obj['birthday'] = birthday
		if self.email:
			udm_obj['mailPrimaryAddress'] = self.email
		# not done here. instead in bulk_group_change() for performance reasons
		# and to avoid problems with overwriting unrelated groups
		# udm_obj['groups'] = ...

	def commit_delete(self, lo):
		udm_obj = self.get_udm_object(lo)
		if udm_obj:
			udm_obj.remove()
		return udm_obj

	def get_error_msg(self):
		if self._error_msg is None:
			return None
		markup_username = '<strong>%s</strong>' % self.username
		if self.action == 'create':
			first_sentence = _('%s could not be created.') % markup_username
		elif self.action == 'delete':
			first_sentence = _('%s could not be deleted.') % markup_username
		else:
			first_sentence = _('%s could not be changed.') % markup_username
		return first_sentence + ' ' + self._error_msg

	def get_udm_object(self, lo):
		if self.username is None:
			return None
		if self._udm_obj_searched is False:
			try:
				self._udm_obj = udm_modules.lookup('users/user', None, lo, scope='sub', base=ucr.get('ldap/base'), filter='uid=%s' % self.username)[0]
			except IndexError:
				return None
			self._udm_obj_searched = True
		return self._udm_obj

	def to_dict(self):
		attrs = dict([column, getattr(self, column) or ''] for column in self.get_columns())
		attrs['errors'] = self.errors
		attrs['warnings'] = self.warnings
		return attrs

	def groups_for_ucs_school(self, lo, group_cache, all_found_classes, without_school_classes=False):
		group_dns = []
		group_dns.append(self.get_group_dn('Domain Users %s' % self.school))
		group_dns.append(self.get_group_dn('schueler-%s' % self.school))
		group_dns.append(self.get_group_dn('lehrer-%s' % self.school))
		group_dns.append(self.get_group_dn('mitarbeiter-%s' % self.school))

		if not without_school_classes:
			for school_class_group in all_found_classes:
				group_dns.append(school_class_group.dn)

		for group_dn in group_dns:
			self.get_or_create_group(group_dn, lo, self.school, group_cache)

		return group_dns

	def groups_used(self, lo, group_cache):
		group_dns = []
		group_dns.append(self.get_group_dn('Domain Users %s' % self.school))
		group_dns.extend(self.get_specific_groups())

		for group_dn in group_dns:
			self.get_or_create_group(group_dn, lo, self.school, group_cache)

		return group_dns

	@classmethod
	def from_udm_obj(cls, user_obj, lo, school, date_format, columns=None, **kwargs):
		attrs = {
			'username' : user_obj['username'],
			'firstname' : user_obj['firstname'],
			'lastname' : user_obj['lastname'],
			'birthday' : user_obj['birthday'],
			'email' : user_obj['mailPrimaryAddress'],
		}
		if columns:
			attrs = dict((key, value) for key, value in attrs.iteritems() if key in columns)
		MODULE.info('Now adding kwargs: %r' % kwargs)
		attrs.update(kwargs)
		return cls(lo, school, date_format, attrs)

	@classmethod
	def get_or_create_group(cls, group_dn, lo, school, group_cache):
		if group_cache is None:
			group_cache = {}
		if group_dn not in group_cache:
			MODULE.info('getting group %s' % group_dn)
			if lo is not None:
				try:
					group_obj = udm_modules.lookup('groups/group', None, lo, scope='base', base=group_dn)[0]
				except noObject:
					MODULE.process('Group "%s" not found. Creating...' % group_dn)
					group_parts = lo.explodeDn(group_dn)
					group_name = lo.explodeDn(group_parts[0], 1)[0]
					group_container = ','.join(group_parts[1:])
					pos = udm_uldap.position(ucr.get('ldap/base'))
					pos.setDn(group_container)
					group_obj = udm_modules.get('groups/group').object(None, lo, pos)
					group_obj.open()
					group_obj['name'] = group_name
					group_obj.create()

					# get it fresh from the database (needed for group_obj._exists ...)
					group_obj = udm_modules.lookup('groups/group', None, lo, scope='base', base=group_dn)[0]

					dn_handler = DNHandling.get(school)
					if dn_handler.is_school_class(group_dn):
						share_container = dn_handler.get_shares_container()
						share_dn = dn_handler.get_share_dn(group_name)
						MODULE.process('A share for this group needs to be present: (%s)' % share_dn)
						try:
							udm_modules.lookup('shares/share', None, lo, scope='base', base=share_dn)
						except noObject:
							gid = group_obj['gidNumber']
							pos.setDn(share_container)
							share_obj = udm_modules.get('shares/share').object(None, lo, pos)
							share_obj.open()
							share_obj['name'] = group_name
							share_obj['host'] = cls.get_server_fqdn(school, lo)
							share_obj['path'] = '/home/groups/klassen/%s' % group_name
							share_obj['writeable'] = '1'
							share_obj['sambaWriteable'] = '1'
							share_obj['sambaBrowseable'] = '1'
							share_obj['sambaForceGroup'] = '+%s' % group_name
							share_obj['sambaCreateMode'] = '0770'
							share_obj['sambaDirectoryMode'] = '0770'
							share_obj['owner'] = '0'
							share_obj['group'] = gid
							share_obj['directorymode'] = '0770'
							share_obj.create()
							MODULE.process('Share created on "%s"' % share_obj['host'])
						else:
							MODULE.info('Share found. Nothing to do')
				group_cache[group_dn] = group_obj
		return group_cache[group_dn]

	@classmethod
	def get_server_fqdn(cls, school, lo):
		domainname = ucr.get('domainname')
		school_dn = DNHandling.get(school).get_school_dn()

		# fetch serverfqdn from OU
		result = lo.get(school_dn, ['ucsschoolClassShareFileServer'])
		if result:
			server_domain_name = lo.get(result['ucsschoolClassShareFileServer'][0], ['associatedDomain'])
			if server_domain_name:
				server_domain_name = server_domain_name['associatedDomain'][0]
			else:
				server_domain_name = domainname
			result = lo.get(result['ucsschoolClassShareFileServer'][0], ['cn'])
			if result:
				return "%s.%s" % (result['cn'][0], server_domain_name)

		# get alternative server (defined at ou object if a dc slave is responsible for more than one ou)
		ou_attr_ldap_access_write = lo.get(school_dn, ['univentionLDAPAccessWrite'])
		alternative_server_dn = None
		if len(ou_attr_ldap_access_write) > 0:
			alternative_server_dn = ou_attr_ldap_access_write["univentionLDAPAccessWrite"][0]
			if len(ou_attr_ldap_access_write) > 1: # TODO FIXME This doesn't look correct to me - ou_attr_ldap_access_write is a dict and not a list!
				MODULE.warn('more than one corresponding univentionLDAPAccessWrite found at ou=%s' % school)

		# build fqdn of alternative server and set serverfqdn
		if alternative_server_dn:
			alternative_server_attr = lo.get(alternative_server_dn,['uid'])
			if len(alternative_server_attr) > 0:
				alternative_server_uid = alternative_server_attr['uid'][0]
				alternative_server_uid = alternative_server_uid.replace('$','')
				if len(alternative_server_uid) > 0:
					return "%s.%s" % (alternative_server_uid, domainname)

		# fallback
		return "dc%s-01.%s"%(school.lower(), domainname)

class Student(User):
	additional_columns = ['school_class']
	additional_column_labels = {
		'school_class' : (_('Class'), 'Class'),
	}
	supports_school_classes = True

	@classmethod
	def from_udm_obj(cls, user_obj, lo, school, date_format, columns=None, **kwargs):
		school_class = None
		dn_handler = DNHandling.get(school)
		MODULE.info('Get school class for %s' % user_obj['username'])
		if columns is None or 'school_class' in columns:
			user_obj.open()
			for group in user_obj['groups']:
				MODULE.info('Group %s' % group)
				if dn_handler.is_school_class(group):
					MODULE.info('Is school class!')
					school_class_name = lo.explodeDn(group, 1)[0]
					school_class = school_class_name.split('-')[-1]
					break
			MODULE.info('Result: %r' % school_class)
			kwargs['school_class'] = school_class
		return super(Student, cls).from_udm_obj(user_obj, lo, school, date_format, columns, **kwargs)

	@classmethod
	def get_user_base_for_school(cls, school):
		return DNHandling.get(school).get_students_container()

	def get_specific_groups(self):
		groups = []
		groups.append(self.get_group_dn('schueler-%s' % self.school))
		if self.school_class:
			groups.append(self.get_class_dn('%s-%s' % (self.school, self.school_class)))
		return groups

class Teacher(User):
	additional_columns = ['school_class']
	additional_column_labels = {
		'school_class' : (_('Class'), 'Class'),
	}
	supports_school_classes = True

	@classmethod
	def from_udm_obj(cls, user_obj, lo, school, date_format, columns=None, **kwargs):
		school_classes = []
		dn_handler = DNHandling.get(school)
		if columns is None or 'school_class' in columns:
			user_obj.open()
			for group in user_obj['groups']:
				if dn_handler.is_school_class(group):
					school_class_name = lo.explodeDn(group, 1)[0]
					school_class = school_class_name.split('-')[-1]
					school_classes.append(school_class)
			kwargs['school_class'] = ','.join(school_classes)
		return super(Teacher, cls).from_udm_obj(user_obj, lo, school, date_format, columns, **kwargs)

	@classmethod
	def get_user_base_for_school(cls, school):
		return DNHandling.get(school).get_teachers_container()

	def get_specific_groups(self):
		groups = []
		groups.append(self.get_group_dn('lehrer-%s' % self.school))
		if self.school_class:
			for school_class in self.school_class.split(','):
				groups.append(self.get_class_dn(('%s-%s' % (self.school, school_class))))
		return groups

class Staff(User):
	@classmethod
	def get_user_base_for_school(cls, school):
		return DNHandling.get(school).get_staff_container()

	def get_specific_groups(self):
		groups = []
		groups.append(self.get_group_dn('mitarbeiter-%s' % self.school))
		return groups

class TeacherAndStaff(Teacher):
	@classmethod
	def get_user_base_for_school(cls, school):
		return DNHandling.get(school).get_teachers_and_staff_container()

	def get_specific_groups(self):
		groups = super(TeacherAndStaff, self).get_specific_groups()
		groups.append(self.get_group_dn('mitarbeiter-%s' % self.school))
		return groups

