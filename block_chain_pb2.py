# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: block_chain.proto
# Protobuf Python Version: 5.29.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    0,
    '',
    'block_chain.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


import common_pb2 as common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x11\x62lock_chain.proto\x12\nblockchain\x1a\x0c\x63ommon.proto\"8\n\x0fWhisperResponse\x12\x0e\n\x06status\x18\x01 \x01(\t\x12\x15\n\rerror_message\x18\x02 \x01(\t\"p\n\x05\x42lock\x12\n\n\x02id\x18\x01 \x01(\x03\x12\x0c\n\x04hash\x18\x02 \x01(\t\x12\x15\n\rprevious_hash\x18\x03 \x01(\t\x12!\n\x06\x61udits\x18\x04 \x03(\x0b\x32\x11.common.FileAudit\x12\x13\n\x0bmerkle_root\x18\x05 \x01(\t\"H\n\x11\x42lockVoteResponse\x12\x0c\n\x04vote\x18\x01 \x01(\x08\x12\x0e\n\x06status\x18\x02 \x01(\t\x12\x15\n\rerror_message\x18\x03 \x01(\t\"<\n\x13\x42lockCommitResponse\x12\x0e\n\x06status\x18\x02 \x01(\t\x12\x15\n\rerror_message\x18\x03 \x01(\t\"\x1d\n\x0fGetBlockRequest\x12\n\n\x02id\x18\x01 \x01(\x03\"[\n\x10GetBlockResponse\x12 \n\x05\x62lock\x18\x01 \x01(\x0b\x32\x11.blockchain.Block\x12\x0e\n\x06status\x18\x02 \x01(\t\x12\x15\n\rerror_message\x18\x03 \x01(\t\"x\n\x10HeartbeatRequest\x12\x14\n\x0c\x66rom_address\x18\x01 \x01(\t\x12\x1e\n\x16\x63urrent_leader_address\x18\x02 \x01(\t\x12\x17\n\x0flatest_block_id\x18\x03 \x01(\x03\x12\x15\n\rmem_pool_size\x18\x04 \x01(\x03\":\n\x11HeartbeatResponse\x12\x0e\n\x06status\x18\x01 \x01(\t\x12\x15\n\rerror_message\x18\x02 \x01(\t\"7\n\x16TriggerElectionRequest\x12\x0c\n\x04term\x18\x01 \x01(\x03\x12\x0f\n\x07\x61\x64\x64ress\x18\x02 \x01(\t\"\\\n\x17TriggerElectionResponse\x12\x0c\n\x04vote\x18\x01 \x01(\x08\x12\x0c\n\x04term\x18\x02 \x01(\x03\x12\x0e\n\x06status\x18\x03 \x01(\t\x12\x15\n\rerror_message\x18\x04 \x01(\t\"*\n\x17NotifyLeadershipRequest\x12\x0f\n\x07\x61\x64\x64ress\x18\x01 \x01(\t\"A\n\x18NotifyLeadershipResponse\x12\x0e\n\x06status\x18\x01 \x01(\t\x12\x15\n\rerror_message\x18\x02 \x01(\t2\xaf\x04\n\x11\x42lockChainService\x12\x45\n\x13WhisperAuditRequest\x12\x11.common.FileAudit\x1a\x1b.blockchain.WhisperResponse\x12@\n\x0cProposeBlock\x12\x11.blockchain.Block\x1a\x1d.blockchain.BlockVoteResponse\x12\x41\n\x0b\x43ommitBlock\x12\x11.blockchain.Block\x1a\x1f.blockchain.BlockCommitResponse\x12\x45\n\x08GetBlock\x12\x1b.blockchain.GetBlockRequest\x1a\x1c.blockchain.GetBlockResponse\x12L\n\rSendHeartbeat\x12\x1c.blockchain.HeartbeatRequest\x1a\x1d.blockchain.HeartbeatResponse\x12Z\n\x0fTriggerElection\x12\".blockchain.TriggerElectionRequest\x1a#.blockchain.TriggerElectionResponse\x12]\n\x10NotifyLeadership\x12#.blockchain.NotifyLeadershipRequest\x1a$.blockchain.NotifyLeadershipResponseBv\n,com.codecatalyst.auditchain.proto.blockchainB\x0f\x42lockChainProtoZ5github.com/sameersah/auditchain/proto_gen/block_chainb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'block_chain_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  _globals['DESCRIPTOR']._loaded_options = None
  _globals['DESCRIPTOR']._serialized_options = b'\n,com.codecatalyst.auditchain.proto.blockchainB\017BlockChainProtoZ5github.com/sameersah/auditchain/proto_gen/block_chain'
  _globals['_WHISPERRESPONSE']._serialized_start=47
  _globals['_WHISPERRESPONSE']._serialized_end=103
  _globals['_BLOCK']._serialized_start=105
  _globals['_BLOCK']._serialized_end=217
  _globals['_BLOCKVOTERESPONSE']._serialized_start=219
  _globals['_BLOCKVOTERESPONSE']._serialized_end=291
  _globals['_BLOCKCOMMITRESPONSE']._serialized_start=293
  _globals['_BLOCKCOMMITRESPONSE']._serialized_end=353
  _globals['_GETBLOCKREQUEST']._serialized_start=355
  _globals['_GETBLOCKREQUEST']._serialized_end=384
  _globals['_GETBLOCKRESPONSE']._serialized_start=386
  _globals['_GETBLOCKRESPONSE']._serialized_end=477
  _globals['_HEARTBEATREQUEST']._serialized_start=479
  _globals['_HEARTBEATREQUEST']._serialized_end=599
  _globals['_HEARTBEATRESPONSE']._serialized_start=601
  _globals['_HEARTBEATRESPONSE']._serialized_end=659
  _globals['_TRIGGERELECTIONREQUEST']._serialized_start=661
  _globals['_TRIGGERELECTIONREQUEST']._serialized_end=716
  _globals['_TRIGGERELECTIONRESPONSE']._serialized_start=718
  _globals['_TRIGGERELECTIONRESPONSE']._serialized_end=810
  _globals['_NOTIFYLEADERSHIPREQUEST']._serialized_start=812
  _globals['_NOTIFYLEADERSHIPREQUEST']._serialized_end=854
  _globals['_NOTIFYLEADERSHIPRESPONSE']._serialized_start=856
  _globals['_NOTIFYLEADERSHIPRESPONSE']._serialized_end=921
  _globals['_BLOCKCHAINSERVICE']._serialized_start=924
  _globals['_BLOCKCHAINSERVICE']._serialized_end=1483
# @@protoc_insertion_point(module_scope)
