/*
 * Copyright 2015-2019 Univention GmbH
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
	"umc/widgets/MultiObjectSelect",
	"umc/widgets/TextBox",
	"umc/widgets/ComboBox",
	"umc/modules/schoolgroups/DetailPage",
	"umc/i18n!umc/modules/schoolgroups"
], function(declare, lang, array, MultiObjectSelect, TextBox, ComboBox, DetailPage, _) {

	return declare("umc.modules.schoolgroups.TeacherDetailPage", [DetailPage], {
		multiWidgetName: 'classes',
		getWidgets: function() {
			return [{
				type: ComboBox,
				name: 'school',
				label: _('School'),
				staticValues: []
			}, {
				type: TextBox,
				name: 'name',
				label: _('Teacher'),
				disabled: true
			}, this.getMultiSelectWidget()];
		},

		getMultiSelectWidget: function() {
			return lang.mixin(this.inherited(arguments), {
				label: _('Classes'),
				description: _('List of classes which the selected teacher is member of'),
				formatter: function(items) {
					array.forEach(items, function(schoolClass) {
						if (typeof(schoolClass) === 'object' && schoolClass.hasOwnProperty('label') && schoolClass.hasOwnProperty('school')) {
							if (! schoolClass.hasOwnProperty('shortName')) {
								schoolClass.shortName = schoolClass.label;
							}
							schoolClass.label = schoolClass.shortName + ' (' + schoolClass.school + ')';
						}
					});
					return items;
				},
				queryCommand: lang.hitch(this, function(options) {
					var school = this._form.getWidget(this.multiWidgetName)._detailDialog._form.getWidget('school').get('value');
					return this.umcpCommand('schoolgroups/classes', options).then(function(data) {
						array.forEach(data.result, function(schoolClass) {
							schoolClass.school = school;
						});
						return data.result;
					});
				})
			});
		},

		getMultiSelectGroup: function() {
			return null;
		},

		load: function() {
			// Loading a teacher into this form sets the school to the teachers primary school.
			var currentSchoolChoice = this._form.getWidget('school').get('value');
			this.inherited(arguments).then(lang.hitch(this, function(){
				this._form.getWidget('school').set('value', currentSchoolChoice);
			}));
		},
	});
});
