#!/usr/bin/python2.7
#
# Univention Management Console
#  Automatic UCS@school user import
#
# Copyright 2017 Univention GmbH
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

import os.path
import string
import shutil
import random
import time

import notifier.threads

from univention.management.console.log import MODULE
#from univention.management.console.config import ucr
from univention.management.console.modules.decorators import simple_response, file_upload, require_password
from univention.management.console.modules.mixins import ProgressMixin
import univention.admin.syntax

from ucsschool.lib.schoolldap import SchoolBaseModule
from ucsschool.http_api.client import Client

from univention.lib.i18n import Translation

_ = Translation('ucs-school-umc-import').translate
CACHE_IMPORT_FILES = '/var/cache/ucs-school-umc-import/'


def random_string():
	return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(15))


class Instance(SchoolBaseModule, ProgressMixin):

	def init(self):
		self.client = Client(self.username, self.password, log_level=Client.LOG_RESPONSE)

	@require_password
	@simple_response
	def schools(self):
		schools = (x['displayName'] for x in self.client.get_schools())
		return [dict(id=school, label=school) for school in schools]

	@require_password
	@simple_response
	def user_types(self):
		return [dict(id=id, label=label) for id, label in univention.admin.syntax.ucsschoolTypes.choices]

	@require_password
	@file_upload
	def upload_file(self, request):
		filename = request.options[0]['tmpfile']
		destination = os.path.join(CACHE_IMPORT_FILES, random_string())
		shutil.move(filename, destination)
		self.finished(request.id, {'filename': os.path.basename(destination)})

	@require_password
	@simple_response
	def dry_run(self, filename, usertype, school):
		progress = self.new_progress(total=100)
		thread = notifier.threads.Simple('dry run', notifier.Callback(self._dry_run, filename, usertype, school, progress), notifier.Callback(self.__thread_error_handling, progress))
		thread.run()
		return dict(progress.poll(), id=progress.id)

	def _dry_run(self, filename, usertype, school, progress):
		progress.progress(True, _('Validating import.'))
		progress.current = 20.0
		progress.job = None
		import_file = os.path.join(CACHE_IMPORT_FILES, os.path.basename(filename))
		try:
			school_url = self.client.get_schools(school)['url']  # FIXME: API expects a URI
			importjob = self.client.create_importjob(filename=import_file, source_uid=usertype, school=school_url, dryrun=True)
		except:  # FIXME: error handling
			raise

		jobid = importjob['url'].strip('/').split('/')[-1]
		progress.progress(True, _('Dry run.'))
		progress.current = 50.0

		finished = False
		while not finished:
			time.sleep(0.5)
			job = self.client.get_importjobs(jobid)
			finished = job['status'] == 'Finished'
		return job

	def __thread_error_handling(self, thread, result, progress):
		# caution! if an exception happens in this function the module process will die!
		MODULE.error('Thread result: %s' % (result,))
		if isinstance(result, BaseException):
			progress.exception(thread.exc_info)
			return
		progress.finish_with_result(result)

	@require_password
	def start_import(self, request):
		thread = notifier.threads.Simple('import', notifier.Callback(self._start_import, request), notifier.Callback(self.__thread_finished_callback, request))
		thread.run()

	def _start_import(self, request):
		school = request.options['school']
		filename = request.options['filename']
		usertype = request.options['usertype']
		import_file = os.path.join(CACHE_IMPORT_FILES, os.path.basename(filename))
		school_url = self.client.get_schools(school)  # FIXME: API expects a URI
		try:
			self.client.create_importjob(filename=import_file, source_uid=usertype, school=school_url, dryrun=False)
		except:  # FIXME: error handling
			raise
		os.remove(import_file)

	@require_password
	@simple_response
	def poll_dry_run(self, progress_id):
		progress = self.get_progress(progress_id)
		return progress.poll()

	def get_progress(self, progress_id):
		return self._progress_objs[progress_id]

	@require_password
	@simple_response
	def jobs(self):
		return [{
			'id': job['url'],  # FIXME: no ID property exists
			'school': job['school'],  # FIXME: contains URL
			'creator': job['principal'],
			'user_type': job['source_uid'],
			'date': job['date_created'],  # FIXME: locale aware format
			'status': job['status'],  # FIXME: parse the state
		} for job in self.client.get_importjobs() if not job['dryrun']]