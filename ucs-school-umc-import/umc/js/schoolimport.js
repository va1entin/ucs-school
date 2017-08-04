/*
 * Copyright 2017 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */
/*global define*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/on",
	"dojo/topic",
	"dojo/promise/all",
	"dojo/Deferred",
	"dojox/html/entities",
	"umc/dialog",
	"umc/store",
	"umc/tools",
	"umc/widgets/Page",
	"umc/widgets/Form",
	"umc/widgets/Module",
	"umc/widgets/Wizard",
	"umc/widgets/StandbyMixin",
	"umc/widgets/ComboBox",
	"umc/widgets/Uploader",
	"umc/widgets/ProgressBar",
	"umc/widgets/Text",
	"umc/widgets/Grid",
	"umc/widgets/HiddenInput",
	"umc/i18n!umc/modules/schoolimport"
], function(declare, lang, array, on, topic, all, Deferred, entities, dialog, store, tools, Page, Form, Module, Wizard, StandbyMixin, ComboBox, Uploader, ProgressBar, Text, Grid, HiddenInput, _) {

	var ImportWizard = declare("umc.modules.schoolimport.ImportWizard", [Wizard], {

		autoValidate: true,

		postMixInProperties: function() {
			this.pages = this.getPages();
			this.initialQuery = new Deferred();
			this.initialQuery.then(lang.hitch(this, function() {
				if (!this.getPage('overview')._grid.getAllItems().length) {
					this._next('overview');
				}
			}));
			this._progressBar = new ProgressBar();
			this.inherited(arguments);
		},

		getPages: function() {
			return [{
				name: 'overview',
				headerText: _('All finished imports.'),
				headerTextRegion: 'main',
				helpText: _('The list shows all completed imports.... You can download password and summary... Reload... '),
				helpTextRegion: 'main'
			},{
				name: 'start',
				headerText: _('Perform new import'),
				helpText: _('Please select the school and a user type for the import ...'),
				widgets: [{
					type: ComboBox,
					name: 'school',
					label: _('School'),
					description: _('Select the school where the import should be done.'),
					autoHide: true,
					required: true,
					dynamicValues: 'schoolimport/schools'
				},{
					type: ComboBox,
					name: 'usertype',
					label: _('User type'),
					description: _('Select the user type.'),
					autoHide: true,
					required: true,
					dynamicValues: 'schoolimport/usertypes'
				}]
			},{
				name: 'select-file',
				headerText: _('Select import database.'),
				helpText: _('Select CSV file ... '),
				widgets: [{
					type: Uploader,
					name: 'file',
					label: _('Upload file'),
					labelPosition: 'right',
					command: 'schoolimport/upload-file',
					onUploadStarted: lang.hitch(this, function() {
						this._progressBar.reset();
						this.standby(true, this._progressBar);
					}),
					onUploaded: lang.hitch(this, 'startDryRun'),
					onError: lang.hitch(this, function() {
						this.standby(false);
					})
				}, {
					type: HiddenInput,
					name: 'filename',
				}]
			},{
				name: 'dry-run-overview',
				headerText: _('Overview about the import changes'),
				helpText: _('The following changes will be applied to the domain when continuing the import.'),
				widgets: [{
					name: 'summary',
					type: Text,
					content: ''
				}]
			},{
				name: 'import-started',
				headerText: _('The import was started successfully.'),
				helpTextRegion: 'main',
				helpTextAllowHTML: false,
			},{
				name: 'error',  // FIXME: implement
				headerText: _('An error occurred.'),
				helpText: _('error')
			},/*{
				name: '',
				headerText: '',
				helpText: '',
				widgets: []
			}*/];
		},

		getUploaderParams: function() {
			return {
				usertype: this.getWidget('start', 'usertype').get('value'),
				school: this.getWidget('start', 'school').get('value'),
				filename: this.getWidget('select-file', 'filename').get('value') || undefined
			};
		},

		startDryRun: function(response) {
			this.getWidget('select-file', 'filename').set('value', response.result.filename);
			tools.umcpProgressCommand(this._progressBar, 'schoolimport/dry-run/start', this.getUploaderParams()).then(lang.hitch(this, function(result) {
				this.getWidget('dry-run-overview', 'summary').set('content', entities.encode(result.summary));
				this.standby(false);
				this._next('select-file');
			}), lang.hitch(this, function() {
				this.standby(false);
				this.switchPage('error');
			}));
		},

		isPageVisible: function(pageName) {
			if (pageName === 'error') {
				return false;
			}
			return this.inherited(arguments);
		},

		next: function(pageName) {
			var nextPage = this.inherited(arguments);
			if (pageName === 'import-started') {
				nextPage = 'overview';
			}
			if (nextPage === 'import-started') {
				return this.standbyDuring(tools.umcpCommand('schoolimport/import/start', this.getUploaderParams())).then(lang.hitch(this, function(response) {
					this.getPage(nextPage).set('helpText', _('A new import of %(role)s users at school %(school)s has been started. The import has the ID %(id)s.', {'id': response.result.id, 'role': response.result.user_type, 'school': response.result.school}));
					return nextPage;
				}), lang.hitch(this, function() {
					return 'error';
				}));
			}
			if (nextPage === 'overview') {
				this.buildImportsGrid(this.getPage(nextPage));
			}
			return nextPage;
		},

		getFooterButtons: function(pageName) {
			var buttons = this.inherited(arguments);
			array.forEach(buttons, lang.hitch(this, function(button) {
				if (pageName === 'overview' && button.name === 'next') {
					button.label = _('Start a new import');
				}
				if (pageName === 'dry-run-overview' && button.name === 'next') {
					button.label = _('Start import');
				}
				if (pageName === 'import-started' && button.name === 'next') {
					button.label = _('View finished imports');
				}
			}));
			return array.filter(buttons, function(button) {
				if (pageName === 'select-file' && button.name === 'finish') {
					return false;
				}
				return true;
			});
		},

		hasNext: function(pageName) {
			if (~array.indexOf(['select-file', 'error'], pageName)) {
				return false;
			}
			if (pageName === 'import-started') {
				return true;
			}
			return this.inherited(arguments);
		},

		hasPrevious: function(pageName) {
			if (~array.indexOf(['import-started', 'dry-run-overview', 'error'], pageName)) {
				return false;
			}
			return this.inherited(arguments);
		},

		canFinish: function(values, pageName) {
			if (pageName === 'error') {
				return true;
			}
			return false;  // the wizard is a loop which starts at the beginning
		},

		buildImportsGrid: function(parentWidget) {
			if (parentWidget._grid) {
				parentWidget.removeChild(parentWidget._grid);
				parentWidget._grid.destroyRecursive();
			}

			var grid = new Grid({
				moduleStore: store('id', 'schoolimport/jobs', this.moduleFlavor),
				actions: [{
					name: 'reload',
					label: _('Reload'),
					isContextAction: false,
					callback: function() { grid.filter({query: ''}); }
				}, {
					name: 'start',
					label: _('Start a new import'),
					isContextAction: false,
					callback: lang.hitch(this, function() {
						this._next('overview');
					})
				}],
				columns: [{
					name: 'id',
					label: _('Job ID')
				}, {
					name: 'date',
					label: _('Started at'),
					formatter: function(value) {
						return value; // FIXME:
					}
				}, {
					name: 'school',
					label: _('School')
				}, {
					name: 'creator',
					label: _('Creator')
				}, {
					name: 'user_type',
					label: _('User type')
				}, {
					name: 'status',
					label: _('Status')
				}, {
					name: 'download-summary',
					label: _('Download summary'),
					formatter: function(value, item) {
						return new Text({
							content: _('<a href="/univention/command/schoolimport/job/summary.csv?job=%s" target="_blank">Download summary</>', encodeURIComponent(item.id))
						});
					}
				}, {
					name: 'download-passwords',
					label: _('Download passwords'),
					formatter: function(value, item) {
						return new Text({
							content: _('<a href="/univention/command/schoolimport/job/passwords.csv?job=%s" target="_blank">Download passwords</>', encodeURIComponent(item.id))
						});
					}
				}]
			});

			grid.filter({query: ''});
			grid.on('filterDone', lang.hitch(this, function() {
				if (!this.initialQuery.isFulfilled()) {
					this.initialQuery.resolve();
				}
			}));

			parentWidget.addChild(grid);
			parentWidget._grid = grid;
		},

		ready: function() {
			// FIXME: https://forge.univention.org/bugzilla/show_bug.cgi?id=45061
			return all(array.map(array.filter(this._pages, function(page) { return page._form; }), function(page) {
				return page._form.ready();
			}));
		}
	});

	return declare("umc.modules.schoolimport", [Module], {
		unique: true,
		standbyOpacity: 1,

		postMixInProperties: function() {
			this.inherited(arguments);
			this._wizard = new ImportWizard({ 'class': 'umcCard' });
			this.standbyDuring(this._wizard.ready().then(lang.hitch(this, function() { return this._wizard.initialQuery; })));
		},

		buildRendering: function() {
			this.inherited(arguments);

			this.addChild(this._wizard);

			this._wizard.on('finished', lang.hitch(this, function() {
				topic.publish('/umc/tabs/close', this);
			}));
			this._wizard.on('cancel', lang.hitch(this, function() {
				topic.publish('/umc/tabs/close', this);
			}));
		}
	});
});
