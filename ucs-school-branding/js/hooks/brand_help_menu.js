/*
 * Copyright 2014-2018 Univention GmbH
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
/*global define,require*/

define([
    "dojo/_base/lang",
    "dojo/topic",
    "umc/menu",
    "umc/i18n!umc/hooks/ucs-school-branding"
], function(lang, topic, menu, _) {

    console.log("Branding ucsschool");

    // Copied from default_menu_entries hook. Maybe merge into tools?
    var _openPage = function(url, key, query) {
        query = typeof query === 'string' ? query : '';
        topic.publish('/umc/actions', 'menu', 'help', key);
        var w = window.open(url + query);
        w.focus();
    };
    
    menu.addEntry({
        parentMenuId: 'umcMenuHelp',
        label: _('UCS@school Online-Documentation'),
        priority: 120,
        onClick: lang.hitch(this, _openPage, _('http://docs.univention.de/en/ucsschool.html'), 'website')
    });

});