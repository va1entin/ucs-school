#!/usr/share/ucs-test/runner python
## desc: Check if there are shares with NFS option on
## roles: [domaincontroller_master]
## tags: [apptest, ucsschool]
## exposure: dangerous
## packages: [ucs-school-import]
## bugs: [38641, 42504]

import univention.testing.ucsschool as utu
import univention.testing.utils as utils
from ucsschool.lib.models import School, Share


def main():
	with utu.UCSTestSchool() as schoolenv:
		lo = schoolenv.open_ldap_connection()
		nfs_shares = list()
		for school in School.get_all(lo):
			for share in Share.get_all(lo, school.name):
				share_udm = share.get_udm_object(lo)
				if "nfs" in share_udm.options:
					nfs_shares.append((school.name, share.name))

		utils.fail("Found NFS shares:\n* {}".format("\n* ".join(["school: %r share: %r" % nfs_share for nfs_share in nfs_shares])))


if __name__ == '__main__':
	main()
