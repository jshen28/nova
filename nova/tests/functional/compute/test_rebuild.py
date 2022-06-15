# Copyright 2022 Inspur, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import mock
from oslo_serialization import jsonutils
from oslo_utils.fixture import uuidsentinel as uuids

from nova import context
from nova import exception
from nova import objects
from nova import test
from nova.tests import fixtures as nova_fixtures
from nova.tests.functional import integrated_helpers


class RebuildInstanceCinderFailure(integrated_helpers._IntegratedTestBase):
    # Default self.api to the self.admin_api as live migration is admin only
    ADMIN_API = True
    api_major_version = 'v2.1'
    microversion = 'latest'

    def setUp(self):
        super(RebuildInstanceCinderFailure, self).setUp()

    def test_rebuild_instance_cinder_failure(self):
        server = self.api.post_server({
            'server': {
                'flavorRef': 1,
                'imageRef': '155d900f-4e14-4e4c-a73d-069cbf4541e6',
                'name': 'rebuild-instance-cinder-failure',
                'networks': 'none',
                'block_device_mapping_v2': [
                    {'boot_index': 0,
                     # uuid from nova/tests/fixtures/cinder.py:49
                     'uuid': "6ca404f3-d844-4169-bb96-bc792f37de98",
                     'source_type': 'volume',
                     'destination_type': 'volume'},
                    {'boot_index': 1,
                     'uuid': uuids.broken_volume,
                     'source_type': 'volume',
                     'destination_type': 'volume'}]}})
        server = self._wait_for_state_change(server, 'ACTIVE')
        post = {
            "rebuild": {
                "imageRef": '155d900f-4e14-4e4c-a73d-069cbf4541e6'
            }
        }

        compute = self.computes['compute']
        raises = 0
        call_count = 0

        def mock_delete(*args):
            global call_count
            global raises
            orig_del = compute.volume_api.attachment_delete
            orig_del(*args)
            call_count += 1
            if call_count == 2:
                raises = 1
                raise exception.CinderConnectionFailed(
                    reason='Fake Cinder error')

        with mock.patch(
                'nova.volume.cinder.API.attachment_delete') as mock_del:
            mock_del.side_effect = mock_delete
            # test_rebuild_instance_with_scheduler_group_failure requires
            # cast to return some value altough it shouldn't. so just
            # try catch the post failure
            try:
                self.api.post_server_action(server['id'], post)
            except Exception:
                pass
            self._wait_for_state_change(server, 'ERROR')

        # rebuild second time
        self.api.post_server_action(server['id'], post)
        self._wait_for_state_change(server, 'ACTIVE')
