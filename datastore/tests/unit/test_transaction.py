# Copyright 2014 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

import mock


class TestTransaction(unittest.TestCase):

    @staticmethod
    def _get_target_class():
        from google.cloud.datastore.transaction import Transaction

        return Transaction

    def _make_one(self, client, **kw):
        return self._get_target_class()(client, **kw)

    def test_ctor_defaults(self):
        project = 'PROJECT'
        client = _Client(project)
        xact = self._make_one(client)
        self.assertEqual(xact.project, project)
        self.assertIs(xact._client, client)
        self.assertIsNone(xact.id)
        self.assertEqual(xact._status, self._get_target_class()._INITIAL)
        self.assertEqual(xact._mutations, [])
        self.assertEqual(len(xact._partial_key_entities), 0)

    def test_current(self):
        from google.cloud.proto.datastore.v1 import datastore_pb2

        project = 'PROJECT'
        id_ = 678
        ds_api = _make_datastore_api(xact_id=id_)
        client = _Client(project, datastore_api=ds_api)
        xact1 = self._make_one(client)
        xact2 = self._make_one(client)
        self.assertIsNone(xact1.current())
        self.assertIsNone(xact2.current())
        with xact1:
            self.assertIs(xact1.current(), xact1)
            self.assertIs(xact2.current(), xact1)
            with _NoCommitBatch(client):
                self.assertIsNone(xact1.current())
                self.assertIsNone(xact2.current())
            with xact2:
                self.assertIs(xact1.current(), xact2)
                self.assertIs(xact2.current(), xact2)
                with _NoCommitBatch(client):
                    self.assertIsNone(xact1.current())
                    self.assertIsNone(xact2.current())
            self.assertIs(xact1.current(), xact1)
            self.assertIs(xact2.current(), xact1)
        self.assertIsNone(xact1.current())
        self.assertIsNone(xact2.current())

        ds_api.rollback.assert_not_called()
        commit_method = ds_api.commit
        self.assertEqual(commit_method.call_count, 2)
        mode = datastore_pb2.CommitRequest.TRANSACTIONAL
        commit_method.assert_called_with(project, mode, [], transaction=id_)

        begin_txn = ds_api.begin_transaction
        self.assertEqual(begin_txn.call_count, 2)
        begin_txn.assert_called_with(project)

    def test_begin(self):
        project = 'PROJECT'
        id_ = 889
        ds_api = _make_datastore_api(xact_id=id_)
        client = _Client(project, datastore_api=ds_api)
        xact = self._make_one(client)
        xact.begin()
        self.assertEqual(xact.id, id_)
        ds_api.begin_transaction.assert_called_once_with(project)

    def test_begin_tombstoned(self):
        project = 'PROJECT'
        id_ = 1094
        ds_api = _make_datastore_api(xact_id=id_)
        client = _Client(project, datastore_api=ds_api)
        xact = self._make_one(client)
        xact.begin()
        self.assertEqual(xact.id, id_)
        ds_api.begin_transaction.assert_called_once_with(project)

        xact.rollback()
        client._datastore_api.rollback.assert_called_once_with(project, id_)
        self.assertIsNone(xact.id)

        self.assertRaises(ValueError, xact.begin)

    def test_begin_w_begin_transaction_failure(self):
        project = 'PROJECT'
        id_ = 712
        ds_api = _make_datastore_api(xact_id=id_)
        ds_api.begin_transaction = mock.Mock(side_effect=RuntimeError, spec=[])
        client = _Client(project, datastore_api=ds_api)
        xact = self._make_one(client)

        with self.assertRaises(RuntimeError):
            xact.begin()

        self.assertIsNone(xact.id)
        ds_api.begin_transaction.assert_called_once_with(project)

    def test_rollback(self):
        project = 'PROJECT'
        id_ = 239
        ds_api = _make_datastore_api(xact_id=id_)
        client = _Client(project, datastore_api=ds_api)
        xact = self._make_one(client)
        xact.begin()
        xact.rollback()
        client._datastore_api.rollback.assert_called_once_with(project, id_)
        self.assertIsNone(xact.id)
        ds_api.begin_transaction.assert_called_once_with(project)

    def test_commit_no_partial_keys(self):
        from google.cloud.proto.datastore.v1 import datastore_pb2

        project = 'PROJECT'
        id_ = 1002930
        ds_api = _make_datastore_api(xact_id=id_)
        client = _Client(project, datastore_api=ds_api)
        xact = self._make_one(client)
        xact.begin()
        xact.commit()

        mode = datastore_pb2.CommitRequest.TRANSACTIONAL
        client._datastore_api.commit.assert_called_once_with(
            project, mode, [], transaction=id_)
        self.assertIsNone(xact.id)
        ds_api.begin_transaction.assert_called_once_with(project)

    def test_commit_w_partial_keys(self):
        from google.cloud.proto.datastore.v1 import datastore_pb2

        project = 'PROJECT'
        kind = 'KIND'
        id1 = 123
        key = _make_key(kind, id1, project)
        id2 = 234
        ds_api = _make_datastore_api(key, xact_id=id2)
        client = _Client(project, datastore_api=ds_api)
        xact = self._make_one(client)
        xact.begin()
        entity = _Entity()
        xact.put(entity)
        xact.commit()

        mode = datastore_pb2.CommitRequest.TRANSACTIONAL
        ds_api.commit.assert_called_once_with(
            project, mode, xact.mutations, transaction=id2)
        self.assertIsNone(xact.id)
        self.assertEqual(entity.key.path, [{'kind': kind, 'id': id1}])
        ds_api.begin_transaction.assert_called_once_with(project)

    def test_context_manager_no_raise(self):
        from google.cloud.proto.datastore.v1 import datastore_pb2

        project = 'PROJECT'
        id_ = 912830
        ds_api = _make_datastore_api(xact_id=id_)
        client = _Client(project, datastore_api=ds_api)
        xact = self._make_one(client)
        with xact:
            self.assertEqual(xact.id, id_)
            ds_api.begin_transaction.assert_called_once_with(project)

        mode = datastore_pb2.CommitRequest.TRANSACTIONAL
        client._datastore_api.commit.assert_called_once_with(
            project, mode, [], transaction=id_)
        self.assertIsNone(xact.id)
        self.assertEqual(ds_api.begin_transaction.call_count, 1)

    def test_context_manager_w_raise(self):

        class Foo(Exception):
            pass

        project = 'PROJECT'
        id_ = 614416
        ds_api = _make_datastore_api(xact_id=id_)
        client = _Client(project, datastore_api=ds_api)
        xact = self._make_one(client)
        xact._mutation = object()
        try:
            with xact:
                self.assertEqual(xact.id, id_)
                ds_api.begin_transaction.assert_called_once_with(project)
                raise Foo()
        except Foo:
            self.assertIsNone(xact.id)
            client._datastore_api.rollback.assert_called_once_with(
                project, id_)

        client._datastore_api.commit.assert_not_called()
        self.assertIsNone(xact.id)
        self.assertEqual(ds_api.begin_transaction.call_count, 1)


def _make_key(kind, id_, project):
    from google.cloud.proto.datastore.v1 import entity_pb2

    key = entity_pb2.Key()
    key.partition_id.project_id = project
    elem = key.path.add()
    elem.kind = kind
    elem.id = id_
    return key


class _Entity(dict):

    def __init__(self):
        super(_Entity, self).__init__()
        from google.cloud.datastore.key import Key

        self.key = Key('KIND', project='PROJECT')


class _Client(object):

    def __init__(self, project, datastore_api=None, namespace=None):
        self.project = project
        if datastore_api is None:
            datastore_api = _make_datastore_api()
        self._datastore_api = datastore_api
        self.namespace = namespace
        self._batches = []

    def _push_batch(self, batch):
        self._batches.insert(0, batch)

    def _pop_batch(self):
        return self._batches.pop(0)

    @property
    def current_batch(self):
        return self._batches and self._batches[0] or None


class _NoCommitBatch(object):

    def __init__(self, client):
        from google.cloud.datastore.batch import Batch

        self._client = client
        self._batch = Batch(client)

    def __enter__(self):
        self._client._push_batch(self._batch)
        return self._batch

    def __exit__(self, *args):
        self._client._pop_batch()


def _make_commit_response(*keys):
    from google.cloud.proto.datastore.v1 import datastore_pb2

    mutation_results = [
        datastore_pb2.MutationResult(key=key) for key in keys]
    return datastore_pb2.CommitResponse(mutation_results=mutation_results)


def _make_datastore_api(*keys, **kwargs):
    commit_method = mock.Mock(
        return_value=_make_commit_response(*keys), spec=[])

    xact_id = kwargs.pop('xact_id', 123)
    txn_pb = mock.Mock(
        transaction=xact_id, spec=['transaction'])
    begin_txn = mock.Mock(return_value=txn_pb, spec=[])

    return mock.Mock(
        commit=commit_method, begin_transaction=begin_txn,
        spec=['begin_transaction', 'commit', 'rollback'])
