#!/usr/bin/env python3

import argparse
import asyncio
import grpc
import time
import yaml
import os
import json

import block_chain_pb2
import block_chain_pb2_grpc
import common_pb2
import common_pb2_grpc
import file_audit_pb2
import file_audit_pb2_grpc

from modules.block import Block
from modules.merkle import MerkleTree
from modules.signature import verify_signature

from google.protobuf import empty_pb2
from google.protobuf.json_format import MessageToDict
from google.protobuf.json_format import ParseDict
# from block_chain_pb2 import Block


BLOCK_SIZE = 1
AUDIT_REQUESTS_MAP = {}


class FullNode():
    def __init__(self, args, config):
        self.request_queue = asyncio.Queue()
        self.mem_pool = []
        self.port = args.port
        #self.blocks = self.load_blocks_from_disk() # TODO (aishwarya): this should be on disk
        self.blocks = []
        self.leader = args.is_leader
        self.neighbors = [server['address'] for server in config['servers']]


    def create_block(self, audits, merkle_tree):
        if len(self.blocks) == 0:
            previous_hash = ""
            index = 0
        else:
            last_block = self.blocks[-1]
            previous_hash = last_block.hash
            index = last_block.index+1

        new_block = Block(index=index,
                          previous_hash=previous_hash,
                          audits=audits,
                          merkle_root=merkle_tree.root)

        self.blocks.append(new_block)
        return new_block

    def verify_previous_block_hash(self, block):
        # Check for the last stored hash and prev hash from the request
        if len(self.blocks) == 0:
            previous_block_hash = ""
        else:
            previous_block_hash = self.blocks[-1].hash

        if previous_block_hash != block.previous_hash:
            print(f"verify_previous_block_hash previous hash {block.previous_hash} in block does not match {previous_block_hash}")
            return False

        return True



    def append_block(self, new_block):
        print(f"Block appended: {new_block.hash}")
        self.blocks.append(new_block)


    def append_to_mem_pool(self,req):
        print(f"Request added to mem pool: {req.req_id}")
        self.mem_pool.append(req)


    def remove_from_mem_pool(self, req):
        print(f"Request removed from mem pool: {req.req_id}")
        self.mem_pool.remove(req)


    async def broadcast_whisper_audits(self, request):
        for neighbor in self.neighbors:
            try:
                async with grpc.aio.insecure_channel(neighbor) as channel:
                    stub = block_chain_pb2_grpc.BlockChainServiceStub(channel)
                    response = await stub.WhisperAuditRequest(request)
                    print(f"whisper_audits response received from {neighbor}: {response}")
            except Exception as e:
                print(f"An error occurred while whispering to {neighbor}: {e}")


    def resolve_request_futures(self, new_block, grpc_block):
        for audit in grpc_block.audits:
            if audit.req_id in AUDIT_REQUESTS_MAP:
                future = AUDIT_REQUESTS_MAP[audit.req_id]
                future.set_result(new_block)
                del AUDIT_REQUESTS_MAP[audit.req_id]


    async def broadcast_commit_block(self, new_block, grpc_block):
        for neighbor in self.neighbors:
            try:
                async with grpc.aio.insecure_channel(neighbor) as channel:
                    stub = block_chain_pb2_grpc.BlockChainServiceStub(channel)

                    response = await stub.CommitBlock(grpc_block)
                    print(f"broadcast_commit_block response received from {neighbor}: {response}")
            except Exception as e:
                print(f"broadcast_commit_block an error occurred while committing block to {neighbor}: {e}")


    async def broadcast_block_proposal(self, grpc_block):
        votes = 1

        for neighbor in self.neighbors:
            try:
                async with grpc.aio.insecure_channel(neighbor) as channel:
                    stub = block_chain_pb2_grpc.BlockChainServiceStub(channel)

                    response = await stub.ProposeBlock(grpc_block)
                    print(f"broadcast_block_proposal response received from {neighbor}: {response}")

                    if response.vote:
                        votes += 1
            except Exception as e:
                print(f"broadcast_block_proposal an error occurred while proposing block to {neighbor}: {e}")

        return votes


    async def commit_block(self, block):
        # Remove from MemPool
        for audit in block.audits:
            if audit not in self.mem_pool:
                print(f"commit_block audit {audit} was not in mem_pool!")
                continue

            self.remove_from_mem_pool(audit)

        new_block = Block(index=block.id,
                          hash=block.hash,
                          previous_hash=block.previous_hash,
                          audits=block.audits,
                          merkle_root=block.merkle_root)

        self.append_block(new_block)

        self.resolve_request_futures(new_block, block)
        #print(f"Committing block {block.block_number}")
        self.save_block_to_disk(block)


    async def propose_block(self):
        block_audits = []

        for audit_request_index in range(BLOCK_SIZE):
            block_audits.append(self.mem_pool[audit_request_index])

        # create merkle tree
        merkle_tree = MerkleTree(block_audits)

        # Create new block in the chain
        new_block = self.create_block([audit.req_id for audit in block_audits], merkle_tree)

        grpc_block = block_chain_pb2.Block(
                                  id=new_block.index,
                                  hash=new_block.hash,
                                  previous_hash=new_block.previous_hash,
                                  merkle_root=new_block.merkle_root,
                                  audits=block_audits)

        try:
            votes = await self.broadcast_block_proposal(grpc_block)

            if votes >= len(self.neighbors):
                return new_block, grpc_block, True

        except Exception as e:
            print(f"propose_block an error occurred: {e}")

        return None, None, False


    async def process_queue(self):
        while True:
            try:
                request = await asyncio.wait_for(self.request_queue.get(), timeout=3.0)

                if request not in self.mem_pool:
                    self.append_to_mem_pool(request)
            except asyncio.TimeoutError:
                pass

            if len(self.mem_pool) >= BLOCK_SIZE:
                if self.leader:
                    print("Queue has reached BLOCK_SIZE, processing the queue ...")

                    new_block, grpc_block, block_proposal_accepted = await self.propose_block()
                    if block_proposal_accepted:
                        await self.broadcast_commit_block(new_block, grpc_block)
                        await self.commit_block(grpc_block)

    # Save block to disk
    def save_block_to_disk(self, block, path="./blocks"):
        os.makedirs(path, exist_ok=True)
        if not block.id:
            block.id = 0
        block_dict = MessageToDict(block, preserving_proto_field_name=True)
        block_number = block.id

        file_path = os.path.join(path, f"block_{block_number}.json")
        with open(file_path, 'w') as f:
            json.dump(block_dict, f, indent=4)
        print(f"Block {block_number} saved to: {file_path}")

    # Load blocks from disk
    def load_blocks_from_disk(self, path="./blocks"):
        blocks = []
        if os.path.exists(path):
            for fname in sorted(os.listdir(path)):
                if fname.endswith(".json"):
                    with open(os.path.join(path, fname)) as f:
                        block_dict = json.load(f)
                        print(f"[DEBUG] Loading block from {fname}: {block_dict}")

                        if 'index' not in block_dict:
                            try:
                                block_num = int(fname.split('_')[1].split('.')[0])
                                block_dict['index'] = block_num
                                print(f"Added missing index {block_num} from filename")
                            except (IndexError, ValueError):
                                block_dict['index'] = len(blocks)
                                print(f"Added missing index {len(blocks)} based on block count")

                        if 'previous_hash' not in block_dict:
                            # Default value for the first block or missing hash
                            block_dict['previous_hash'] = "0"
                            print(f"Added default previous_hash: 0")

                        if 'audits' not in block_dict:
                            # Default to an empty list if audits are missing
                            block_dict['audits'] = []
                            print(f"Added default audits: []")

                        # Create a Block instance with the required fields
                        block = Block(
                            index=block_dict['index'],
                            previous_hash=block_dict['previous_hash'],
                            audits=block_dict['audits'],
                            merkle_root=block_dict.get('merkle_root'),
                            timestamp=block_dict.get('timestamp'),
                            hash=block_dict.get('hash')
                        )
                        blocks.append(block)
        print(f"Loaded {len(blocks)} block(s) from disk.")
        return blocks



class FileAuditService(file_audit_pb2_grpc.FileAuditServiceServicer):

    def __init__(self,full_node):
        self.full_node = full_node

    async def SubmitAudit(self, request, context):
        print(f"SubmitAudit {request.req_id}")

        verified = verify_signature(request)

        if not verified:
            print(f"SubmitAudit: failed to verify {request.req_id}")
            return file_audit_pb2.FileAuditResponse(
                req_id=request.req_id,
                status="failure",
                error_message=f"Failed to verify audit {audit}")

        # Whisper the audit to all neighbors
        await self.full_node.broadcast_whisper_audits(request)

        # Create a future that is resolved once the audit is added to a block
        future = asyncio.get_event_loop().create_future()
        AUDIT_REQUESTS_MAP[request.req_id] = future

        # Add this request to the queue
        await full_node.request_queue.put(request)

        # Wait for the audit to be added to a block
        block = await future
        print(f"SubmitAudit {request.req_id} was added to block {block}")

        return file_audit_pb2.FileAuditResponse(
            req_id=request.req_id,
            status="success"
        )


class BlockChainService(block_chain_pb2_grpc.BlockChainServiceServicer):
    def __init__(self,full_node):
        self.full_node = full_node


    async def WhisperAuditRequest(self, request, context):
        print(f"WhisperAuditRequest {request.req_id}")

        verified = verify_signature(request)

        if not verified:
            print(f"WhisperAuditRequest: failed to verify {request.req_id}")
            return file_audit_pb2.FileAuditResponse(status="failure", error_message=f"Failed to verify audit {audit}")

        await full_node.request_queue.put(request)
        return block_chain_pb2.WhisperResponse(status="success")


    async def ProposeBlock(self, block, context):
        print(f"ProposeBlock: {block.hash}")

        if not self.full_node.verify_previous_block_hash(block):
            return block_chain_pb2.BlockVoteResponse(
                vote=False,
                status="failure",
                error_message="Previous block hash does not match"
            )

        for audit in block.audits:
            if audit not in self.full_node.mem_pool:
                # Fallback to verifying audit signatures
                verified = verify_signature(audit)
                if not verified:
                    return block_chain_pb2.BlockVoteResponse(
                        vote=False,
                        status="failure",
                        error_message=f"Failed to verify audit {audit}")

        return block_chain_pb2.BlockVoteResponse(vote=True, status="success")


    async def CommitBlock(self, block, context):
        print(f"CommitBlock: {block.hash}")

        if not self.full_node.verify_previous_block_hash(block):
            return block_chain_pb2.BlockCommitResponse(
                status="failure",
                error_message="Previous block hash does not match"
            )

        await self.full_node.commit_block(block)

        return block_chain_pb2.BlockCommitResponse(status="success")


async def serve(full_node):
    server = grpc.aio.server()

    file_audit_service = FileAuditService(full_node)
    file_audit_pb2_grpc.add_FileAuditServiceServicer_to_server(file_audit_service, server)
    block_chain_pb2_grpc.add_BlockChainServiceServicer_to_server(BlockChainService(full_node),server)

    server.add_insecure_port('[::]:'+str(full_node.port))
    print("Server started on port ", full_node.port)

    await asyncio.gather(server.start(), full_node.process_queue())
    await server.wait_for_termination()


def parse_args():
    parser = argparse.ArgumentParser(description="Async gRPC block chain server")
    parser.add_argument('--port', type=int, help='port number', default=50051)
    parser.add_argument('--is_leader', help='is leader flag', action='store_true', default=False)
    parser.add_argument('--is_local', help='local configuration', action='store_true', default=False)
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    if args.is_local:
        config_file_name = "local_config.yaml"
    else:
        config_file_name = "config.yaml"

    with open(config_file_name) as f:
        config = yaml.safe_load(f)

    full_node = FullNode(args, config)

    print(full_node.port)
    print(full_node.leader)

    asyncio.run(serve(full_node))
