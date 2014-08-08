# Copyright 2013, Google Inc. All rights reserved.
# Use of this source code is governed by a BSD-style license that can
# be found in the LICENSE file.

import struct

from vtdb import dbexceptions
from vtdb import keyrange_constants


pack_keyspace_id = struct.Struct('!Q').pack

# Represent the SrvKeyspace object from the toposerver, and provide functions
# to extract sharding information from the same.
class Keyspace(object):
  name = None
  db_types = None
  partitions = None
  sharding_col_name = None
  sharding_col_type = None
  served_from = None

  # load this object from a SrvKeyspace object generated by vt
  def __init__(self, name, data):
    self.name = name
    self.db_types = data['TabletTypes']
    self.partitions = data.get('Partitions', {})
    self.sharding_col_name = data.get('ShardingColumnName', "")
    self.sharding_col_type = data.get('ShardingColumnType', keyrange_constants.KIT_UNSET)
    self.served_from = data.get('ServedFrom', None)

  def get_shards(self, db_type):
    if not db_type:
      raise ValueError('db_type is not set')
    try:
      return self.partitions[db_type]['Shards']
    except KeyError:
      return []

  def get_shard_count(self, db_type):
    if not db_type:
      raise ValueError('db_type is not set')
    shards = self.get_shards(db_type)
    return len(shards)

  def get_shard_max_keys(self, db_type):
    if not db_type:
      raise ValueError('db_type is not set')
    shards = self.get_shards(db_type)
    shard_max_keys = [shard['KeyRange']['End']
                      for shard in shards]
    return shard_max_keys

  def get_shard_names(self, db_type):
    if not db_type:
      raise ValueError('db_type is not set')
    names = []
    shards = self.get_shards(db_type)
    shard_max_keys = self.get_shard_max_keys(db_type)
    if len(shard_max_keys) == 1 and shard_max_keys[0] == keyrange_constants.MAX_KEY:
      return [keyrange_constants.SHARD_ZERO,]
    for i, max_key in enumerate(shard_max_keys):
      min_key = keyrange_constants.MIN_KEY
      if i > 0:
        min_key = shard_max_keys[i-1]
      shard_name = '%s-%s' % (min_key.encode('hex').upper(),
                              max_key.encode('hex').upper())
      names.append(shard_name)
    return names

  def keyspace_id_to_shard_name_for_db_type(self, keyspace_id, db_type):
    if not keyspace_id:
      raise ValueError('keyspace_id is not set')
    if not db_type:
      raise ValueError('db_type is not set')
    # Pack this into big-endian and do a byte-wise comparison.
    pkid = pack_keyspace_id(keyspace_id)
    shard_max_keys = self.get_shard_max_keys(db_type)
    shard_names = self.get_shard_names(db_type)
    if not shard_max_keys:
      raise ValueError('Keyspace is not range sharded', self.name)
    for shard_index, shard_max in enumerate(shard_max_keys):
      if pkid < shard_max:
        break
    return shard_names[shard_index]


def read_keyspace(topo_client, keyspace_name):
  try:
    data = topo_client.get_srv_keyspace('local', keyspace_name)
    if not data:
      raise dbexceptions.OperationalError('invalid empty keyspace',
                                          keyspace_name)
    return Keyspace(keyspace_name, data)
  except dbexceptions.OperationalError as e:
    raise e
  except Exception as e:
    raise dbexceptions.OperationalError('invalid keyspace', keyspace_name, e)
