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
from google.protobuf.json_format import MessageToDict
from google.protobuf import empty_pb2


BLOCK_SIZE = 1
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_TIMEOUT_THRESHOLD_SECONDS = 15

AUDIT_REQUESTS_MAP = {}
HEARTBEATS_MAP = {}


class FullNode():
    def __init__(self, args, config):
        self.request_queue = asyncio.Queue()
        self.mem_pool = []
        self.port = args.port
        self.blocks = [] # TODO (aishwarya): this should be on disk
        self.known_block_hashes = set()
        self.is_leader = args.is_leader
        self.current_leader = None
        self.address = args.ip + ":" + str(args.port)
        self.neighbors = [server['address'] for server in config['servers'] if server['address'] != self.address]
        self.audit_hash_store = {}
        print(f"Neighbors: {self.neighbors}")


    async def send_heartbeats(self):
        while True:
            for neighbor in self.neighbors:
                heartbeat_request = block_chain_pb2.HeartbeatRequest(
                    from_address=self.address,
                    current_leader_address=self.current_leader if self.current_leader else "",
                    latest_block_id=len(self.blocks) - 1,
                    mem_pool_size=len(self.mem_pool),
                )

                #print(f"{self.address}: block size : {len(self.blocks)} and mem_pool size {len(self.mem_pool)}")
                #print(heartbeat_request)

                try:
                    async with grpc.aio.insecure_channel(neighbor) as channel:
                        stub = block_chain_pb2_grpc.BlockChainServiceStub(channel)
                        heartbeat_response = await stub.SendHeartbeat(heartbeat_request)
                        #if heartbeat_response.error_message:
                        #    print(f"send_heartbeats an error_message from {neighbor}: heartbeat_response.error_message")
                except Exception as e:
                    pass
                    #print(f"send_heartbeats an error occurred sending to {neighbor}: {e}")
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


    def create_heartbeat_tasks(self):
        send_heartbeats_task = asyncio.create_task(self.send_heartbeats())
        monitor_heartbeat_latest_block_task = asyncio.create_task(self.monitor_heartbeat_latest_blocks())
        monitor_missed_heartbeats_task = asyncio.create_task(self.monitor_missed_heartbeats())

        return [send_heartbeats_task, monitor_heartbeat_latest_block_task, monitor_missed_heartbeats_task]
        #return [send_heartbeats_task, monitor_missed_heartbeats_task]


    async def synchronize_blocks(self, latest_block_id,neighbor_address):
        print(f"synchronize_blocks latest_block_id : {latest_block_id} neighbor_address : {neighbor_address}")
        current_block_id = -1 if len(self.blocks) == 0 else (len(self.blocks)-1)
        while current_block_id < latest_block_id :
            getblock_request = block_chain_pb2.GetBlockRequest(id=current_block_id+1)
            try:
                async with grpc.aio.insecure_channel(neighbor_address) as channel:
                    stub = block_chain_pb2_grpc.BlockChainServiceStub(channel)
                    get_block_response = await stub.GetBlock(getblock_request)
                    if get_block_response.error_message:
                        print(f"synchronize_blocks an error_message from {neighbor_address}: heartbeat_response.error_message")
                        break
                    grpc_block = get_block_response.block
                    valid, validation_error_msg = await self.validate_block(grpc_block)
                    if not valid :
                        break
                    await self.commit_block(grpc_block)
                    current_block_id += 1

            except Exception as e:
                print(f"synchronize_blocks an error occurred sending to {neighbor_address}: {e}")
                break


    async def monitor_heartbeat_latest_blocks(self):
        while True:
            try:
                for neighbor, heartbeat_data in HEARTBEATS_MAP.items():
                    if not heartbeat_data['is_valid']:
                        continue

                    other_latest_block_id = heartbeat_data['request'].latest_block_id
                    if not self.is_leader:
                        local_last_block_id = -1 if len(self.blocks) == 0 else len(self.blocks) - 1
                        if local_last_block_id < other_latest_block_id:
                            await self.synchronize_blocks(other_latest_block_id, neighbor)
            except Exception as e:
                print(f"monitor_heartbeat_latest_blocks an error occurred monitoring heartbeats: {e}")

            await asyncio.sleep(2)


    async def monitor_missed_heartbeats(self):
        while True:
            now = time.time()
            for neighbor, heartbeat_data in HEARTBEATS_MAP.items():
                if not heartbeat_data['is_valid']:
                    continue

                if now - heartbeat_data['time'] > HEARTBEAT_TIMEOUT_THRESHOLD_SECONDS:
                    heartbeat_data['is_valid'] = False
                    print(f"Missed heartbeats from {neighbor}, now {now} and last_time {heartbeat_data['time']}")

            await asyncio.sleep(HEARTBEAT_TIMEOUT_THRESHOLD_SECONDS)


    def get_best_server_to_elect(self):
        best_neighbor_address = self.address
        best_neighbor_block_id = len(self.blocks) - 1
        best_neighbor_mem_pool_size = len(self.mem_pool)

        for neighbor, heartbeat_data in HEARTBEATS_MAP.items():
            if not heartbeat_data['is_valid']:
                continue

            if heartbeat_data['request'].latest_block_id > best_neighbor_block_id:
                best_neighbor_address = neighbor
                best_neighbor_block_id = heartbeat_data['request'].latest_block_id
                best_neighbor_mem_pool_size = heartbeat_data['request'].mem_pool_size
                continue

            if heartbeat_data['request'].mem_pool_size > best_neighbor_mem_pool_size:
                best_neighbor_address = neighbor
                best_neighbor_block_id = heartbeat_data['request'].latest_block_id
                best_neighbor_mem_pool_size = heartbeat_data['request'].mem_pool_size
                continue

            if neighbor > best_neighbor_address:
                best_neighbor_address = neighbor
                best_neighbor_block_id = heartbeat_data['request'].latest_block_id
                best_neighbor_mem_pool_size = heartbeat_data['request'].mem_pool_size

#        print(f"best_neighbor_to_elect {best_neighbor_address} {best_neighbor_block_id} {best_neighbor_mem_pool_size}")
        return best_neighbor_address


    def should_trigger_election(self):
        #print(self.current_leader)

        if self.is_leader:
            return False

        num_alive_neighbors = 0
        for heartbeat_data in HEARTBEATS_MAP.values():
            if heartbeat_data['is_valid']:
                num_alive_neighbors += 1

        best_server_address = self.get_best_server_to_elect()

        if self.current_leader is None:
            if num_alive_neighbors > 0: # TODO: consider larger number of alive neighbors before triggering election?
                if best_server_address == self.address:
                    return True
        else:
            if self.current_leader in HEARTBEATS_MAP:
                heartbeat_data = HEARTBEATS_MAP[self.current_leader]
                if not heartbeat_data['is_valid']: # current_leader is offline
                    if best_server_address == self.address:
                        return True

        return False


    async def handle_trigger_election(self):
        request = block_chain_pb2.TriggerElectionRequest(address=self.address)

        votes = 0
        voted_neighbors = 0
        for neighbor in self.neighbors:
            try:
                async with grpc.aio.insecure_channel(neighbor) as channel:
                    stub = block_chain_pb2_grpc.BlockChainServiceStub(channel)
                    response = await stub.TriggerElection(request)
                    print(f"trigger_election response received from {neighbor}: {response}")

                    voted_neighbors += 1

                    # Count vote if vote true
                    if response.vote:
                        votes += 1

            except Exception as e:
                print(f"An error occurred while triggering election to {neighbor}: {e}")

        # If we get here, all neighbors voted for us
        if votes >= (voted_neighbors // 2) + 1:
            await self.notify_leadership()


    async def monitor_trigger_election(self):
        await asyncio.sleep(15)

        while True:
            if self.should_trigger_election():
                await self.handle_trigger_election()

            await asyncio.sleep(5)


    def create_election_tasks(self):
        should_trigger_election_task = asyncio.create_task(self.monitor_trigger_election())
        return [should_trigger_election_task]


    async def notify_leadership(self):
        request = block_chain_pb2.NotifyLeadershipRequest(address=self.address)

        for neighbor in self.neighbors:
            try:
                async with grpc.aio.insecure_channel(neighbor) as channel:
                    stub = block_chain_pb2_grpc.BlockChainServiceStub(channel)
                    response = await stub.NotifyLeadership(request)
                    print(f"notify_leadership response received from {neighbor}: {response}")

            except Exception as e:
                print(f"An error occurred while notifying leadership to {neighbor}: {e}")

        self.is_leader = True
        self.current_leader = self.address


    def create_block(self, audits, merkle_tree):
        if len(self.blocks) == 0:
            previous_hash = "genesis"
            index = 0
        else:
            last_block = self.blocks[-1]
            previous_hash = last_block.hash
            index = last_block.index+1

        new_block = Block(index=index,
                          previous_hash=previous_hash,
                          audits=audits,
                          merkle_root=merkle_tree.root)

        return new_block


    def verify_previous_block_hash(self, block):
        # Check for the last stored hash and prev hash from the request
        if len(self.blocks) == 0:
            previous_block_hash = "genesis"
        else:
            previous_block_hash = self.blocks[-1].hash

        if previous_block_hash != block.previous_hash:
            print(f"verify_previous_block_hash previous hash {block.previous_hash} in block does not match {previous_block_hash}")
            return False

        return True


    def append_block(self, new_block):
        print(f"\nAppending new block: index={new_block.index}, hash={new_block.hash}")

        if new_block.index in self.known_block_hashes:
            print(f"append_block Ignoring duplicate block {new_block}")
            return

        self.known_block_hashes.add(new_block.index)
        self.blocks.append(new_block)
        print(f"Block appended to memory: {new_block.hash}")

        # Save block to disk
        try:
            print("Attempting to save block to disk...")
            self.save_block_to_disk(new_block)
            print("Block successfully saved to disk")
        except Exception as e:
            print(f"Error saving block to disk: {e}")


    def append_to_mem_pool(self,req):
        print(f"Request added to mem pool: {req.req_id}")
        self.mem_pool.append(req)


    def remove_from_mem_pool(self, req):
        print(f"Request removed from mem pool: {req.req_id}")
        self.mem_pool.remove(req)

    async def validate_block (self, grpc_block):
        # Verify audit signatures
        for audit in grpc_block.audits:
            if audit not in self.mem_pool:
                # Fallback to verifying audit signatures
                verified = verify_signature(audit)
                if not verified:
                    error_message=f"Failed to verify audit {audit}"
                    print(error_message)
                    return (False, error_message)

        merkle_tree = MerkleTree(grpc_block.audits)

        if merkle_tree.root != grpc_block.merkle_root:
            error_message = f"Merkle root {grpc_block.merkle_root} does not match expected merkle root {merkle_tree.root}"
            print(error_message)
            return (False, error_message)
        else:
            print(f"Merkle roots match {merkle_tree.root}!!")

        # Create new block in the chain
        new_block = self.create_block(grpc_block.audits, merkle_tree)

        if new_block.hash != grpc_block.hash:
            error_message = f"Block hash {grpc_block.hash} does not match expected hash {new_block.hash}"
            print(error_message)
            return (False, error_message)

        return (True , None)

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
                if not future.done():
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


    async def propose_block(self):
        block_audits = []

        for audit_request_index in range(BLOCK_SIZE):
            block_audits.append(self.mem_pool[audit_request_index])

        # create merkle tree
        merkle_tree = MerkleTree(block_audits)

        # Create new block in the chain
        new_block = self.create_block(block_audits, merkle_tree)

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
                if self.is_leader:
                    print("Queue has reached BLOCK_SIZE, processing the queue ...")

                    new_block, grpc_block, block_proposal_accepted = await self.propose_block()
                    if block_proposal_accepted:
                        await self.broadcast_commit_block(new_block, grpc_block)
                        await self.commit_block(grpc_block)


    # Save block to disk
    def save_block_to_disk(self, block, path="./blocks"):
        try:
            print(f"\nAttempting to save block {block.index} to disk...")
            print(f"Block details: hash={block.hash}, previous_hash={block.previous_hash}")

            os.makedirs(path, exist_ok=True)
            print(f"Created/verified blocks directory at {path}")

            # Convert audits to serializable format
            serialized_audits = []
            for audit in block.audits:
                # Convert Unix timestamp to human readable format
                audit_time = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(audit.timestamp))

                audit_dict = {
                    "req_id": audit.req_id,
                    "file_info": {
                        "file_id": audit.file_info.file_id,
                        "file_name": audit.file_info.file_name
                    },
                    "user_info": {
                        "user_id": audit.user_info.user_id,
                        "user_name": audit.user_info.user_name
                    },
                    "access_type": audit.access_type,
                    "timestamp": audit.timestamp,
                    "timestamp_readable": audit_time
                }
                serialized_audits.append(audit_dict)

            # Convert block timestamp to human readable format
            block_time = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(block.timestamp))

            # Convert Block object to a dictionary
            block_dict = {
                "id": block.index,
                "hash": block.hash,
                "previous_hash": block.previous_hash,
                "merkle_root": block.merkle_root,
                "timestamp": block.timestamp,
                "timestamp_readable": block_time,
                "audits": serialized_audits
            }

            file_path = os.path.join(path, f"block_{block.index}.json")
            print(f"Saving to file: {file_path}")

            with open(file_path, 'w') as f:
                json.dump(block_dict, f, indent=4)
            print(f"Successfully saved block {block.index} to: {file_path}")

        except Exception as e:
            print(f"Error in save_block_to_disk: {str(e)}")
            import traceback
            print(f"Full error: {traceback.format_exc()}")
            raise e


    # Load blocks from disk
    def load_blocks_from_disk(self, path="./blocks"):
        blocks = []
        try:
            if os.path.exists(path):
                for fname in sorted(os.listdir(path)):
                    if fname.endswith(".json"):
                        file_path = os.path.join(path, fname)
                        try:
                            with open(file_path) as f:
                                block_dict = json.load(f)

                                # Convert saved audits back to FileAudit objects
                                audits = []
                                for audit_dict in block_dict.get('audits', []):
                                    audit = common_pb2.FileAudit(
                                        req_id=audit_dict['req_id'],
                                        file_info=common_pb2.FileInfo(
                                            file_id=audit_dict['file_info']['file_id'],
                                            file_name=audit_dict['file_info']['file_name']
                                        ),
                                        user_info=common_pb2.UserInfo(
                                            user_id=audit_dict['user_info']['user_id'],
                                            user_name=audit_dict['user_info']['user_name']
                                        ),
                                        access_type=audit_dict['access_type'],
                                        timestamp=audit_dict['timestamp']
                                    )
                                    audits.append(audit)

                                # Create Block instance
                                block = Block(
                                    index=block_dict['id'],
                                    previous_hash=block_dict['previous_hash'],
                                    audits=audits,
                                    merkle_root=block_dict.get('merkle_root'),
                                    timestamp=block_dict.get('timestamp'),
                                    hash=block_dict.get('hash')
                                )
                                blocks.append(block)
                                print(f"Loaded block {block.index} from {fname}")
                        except Exception as e:
                            print(f"Error loading block from {fname}: {e}")
                            continue

            blocks.sort(key=lambda x: x.index)  # Ensure blocks are in order
            print(f"Loaded {len(blocks)} block(s) from disk")
            return blocks
        except Exception as e:
            print(f"Error in load_blocks_from_disk: {e}")
            return []


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

        # Initialize audit_hash_store if it doesn't exist
        if not hasattr(self, 'audit_hash_store'):
            self.audit_hash_store = {}

        valid, validation_error_msg = await self.full_node.validate_block(block)

        if not valid :
                return block_chain_pb2.BlockVoteResponse(
                         vote=False,
                         status="failure",
                         error_message=validation_error_msg)

        if hasattr(self, 'save_audit_hashes'):
            self.save_audit_hashes()

        # Save updated audit hashes after successful validation
        if hasattr(self, 'save_audit_hashes'):
            self.save_audit_hashes()

        return block_chain_pb2.BlockVoteResponse(vote=True, status="success")


    async def CommitBlock(self, block, context):
        print(f"CommitBlock: {block.hash}")
        valid, validation_error_msg = await self.full_node.validate_block(block)
        if not valid:
            return block_chain_pb2.BlockCommitResponse(
                status="failure",
                error_message=validation_error_msg
            )

        await self.full_node.commit_block(block)

        return block_chain_pb2.BlockCommitResponse(status="success")


    def save_audit_hashes(self):
        """Save audit hashes to disk"""
        try:
            import json
            with open('audit_hashes.json', 'w') as f:
                json.dump(self.audit_hash_store, f)
            print(f"Saved {len(self.audit_hash_store)} audit hashes to disk")
        except Exception as e:
            print(f"Error saving audit hashes: {e}")

    def load_audit_hashes(self):
        """Load audit hashes from disk"""
        try:
            import json
            with open('audit_hashes.json', 'r') as f:
                self.audit_hash_store = json.load(f)
            print(f"Loaded {len(self.audit_hash_store)} audit hashes from disk")
        except FileNotFoundError:
            self.audit_hash_store = {}
            print("No stored audit hashes found, starting fresh")
        except Exception as e:
            print(f"Error loading audit hashes: {e}")
            self.audit_hash_store = {}


    async def GetBlock(self, request, context):
        if request.id < len(self.full_node.blocks):
            block = self.full_node.blocks[request.id]

            grpc_block = block_chain_pb2.Block(
                             id=block.index,
                             hash=block.hash,
                             previous_hash=block.previous_hash,
                             merkle_root=block.merkle_root,
                             audits=block.audits)

            return block_chain_pb2.GetBlockResponse(block=grpc_block, status="success")
        else:
            return block_chain_pb2.GetBlockResponse(status="failure", error_message=f"Block id {request.id} does not exist")


    async def SendHeartbeat(self, request, context):
        print(f"SendHeartbeat received heartbeat from {request.from_address} with mem_pool {request.mem_pool_size} and latest_block_id {request.latest_block_id} and current leader {request.current_leader_address}")

        if request.from_address not in HEARTBEATS_MAP:
            HEARTBEATS_MAP[request.from_address] = {}

        heartbeat_data = HEARTBEATS_MAP[request.from_address]
        heartbeat_data['time'] = time.time()
        heartbeat_data['is_valid'] = True
        heartbeat_data['request'] = request

        if self.full_node.current_leader is None:
            if request.current_leader_address:
                if request.current_leader_address in HEARTBEATS_MAP and HEARTBEATS_MAP[request.current_leader_address]['is_valid']:
                    print(f"Accepting {request.current_leader_address} as current leader")
                    self.full_node.current_leader = request.current_leader_address

        return block_chain_pb2.HeartbeatResponse(status="success")


    async def TriggerElection(self, request, context):
        print(f"Election triggered by neighbor! {request}")

        if not request.address:
            return block_chain_pb2.TriggerElectionResponse(vote=False, status="failure", error_message="request.address is empty")

        if request.address not in HEARTBEATS_MAP:
            return block_chain_pb2.TriggerElectionResponse(vote=False, status="failure", error_message=f"{request.address} not in heartbeat map")

        heartbeat_data = HEARTBEATS_MAP[request.address]
        if not heartbeat_data['is_valid']:
            return block_chain_pb2.TriggerElectionResponse(vote=False, status="failure", error_message=f"{request.address} has not sent recent heartbeats")

        best_neighbor = self.full_node.get_best_server_to_elect()
        print(f"{request.address} is asking for vote, best neighbor is {best_neighbor}")

        if request.address != best_neighbor:
            return block_chain_pb2.TriggerElectionResponse(vote=False, status="failure", error_message=f"better neighbor {best_neighbor} should be elected")

        print(f"Voting for {request.address}!")
        return block_chain_pb2.TriggerElectionResponse(vote=True, status="success")


    async def NotifyLeadership(self, request, context):
        print(f"Notified of Leadership by neighbor! {request}")

        if not request.address:
            return block_chain_pb2.NotifyLeadershipResponse(status="failure", error_message="request.address is empty")

        if request.address not in HEARTBEATS_MAP:
            return block_chain_pb2.NotifyLeadershipResponse(status="failure", error_message=f"{request.address} not in heartbeat map")

        self.full_node.is_leader = False
        self.full_node.current_leader = request.address

        return block_chain_pb2.NotifyLeadershipResponse(status="success")


async def serve(full_node):
    server = grpc.aio.server()

    file_audit_service = FileAuditService(full_node)
    file_audit_pb2_grpc.add_FileAuditServiceServicer_to_server(file_audit_service, server)
    block_chain_pb2_grpc.add_BlockChainServiceServicer_to_server(BlockChainService(full_node),server)

    server.add_insecure_port('[::]:'+str(full_node.port))
    print("Server started on port ", full_node.port)

    heartbeat_tasks = full_node.create_heartbeat_tasks()
    election_tasks = full_node.create_election_tasks()
    await asyncio.gather(server.start(), full_node.process_queue(), *heartbeat_tasks, *election_tasks)
    await server.wait_for_termination()


def parse_args():
    parser = argparse.ArgumentParser(description="Async gRPC block chain server")
    parser.add_argument('--ip', help='ip address or hostname', default="")
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

    # Load existing blocks from disk on startup
    try:
        loaded_blocks = full_node.load_blocks_from_disk()
        full_node.blocks = loaded_blocks
        for block in loaded_blocks:
            full_node.known_block_hashes.add(block.index)
        print(f"Loaded {len(loaded_blocks)} blocks from disk")
    except Exception as e:
        print(f"Error loading blocks from disk: {e}")

    print(full_node.port)
    print(full_node.is_leader)

    asyncio.run(serve(full_node))
