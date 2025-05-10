import argparse
import asyncio
import grpc
import time

from proto import block_chain_pb2
from proto import block_chain_pb2_grpc
from proto import common_pb2
from proto import common_pb2_grpc
from proto import file_audit_pb2
from proto import file_audit_pb2_grpc

from modules.block import Block
from modules.merkle import MerkleTree

from google.protobuf import empty_pb2


BLOCK_SIZE = 3
AUDIT_REQUESTS_MAP = {}


class AuditDetails():
    def __init__(self, audit_id , block_id):
        self.audit_id = audit_id
        self.block_id = block_id


class FullNode():
    def __init__(self, args):
        self.request_queue = asyncio.Queue()
        self.mem_pool = []
        self.port = args.port
        self.isvalidator = args.isvalidator
        self.blocks = [Block.create_genesis_block()]
        self.audit_details_byfile = {}  # Lookup data strcture based on File Id
        self.leader = False
        self.neighbors = ['[::]:50052','[::]:50053']


    def create_block(self, audits, merkle_tree):
        last_block = self.blocks[-1]
        new_block = Block(index = last_block.index+1,
                          previous_hash=last_block.hash,
                          audits=audits,
                          merkle_root=merkle_tree.root)

        self.blocks.append(new_block)
        return new_block


    def append_block(self, new_block):
        print("Block appended!!!")
        self.blocks.append(new_block)


    def append_to_mem_pool(self,req):
        print("Request added to mem pool")
        self.mem_pool.append(req)


    def remove_from_mem_pool(self, req):
        print("Requets Removed from mempool")
        self.mem_pool.remove(req)


    def store_file_audits(self, file_id, audit_id, block_id):
        audit_details = AuditDetails(audit_id, block_id)
        if file_id in self.audit_details_byfile :
            self.audit_details_byfile[file_id].append(audit_details)
        else :
            self.audit_details_byfile[file_id] = [audit_details]


    async def send_block_proposal(self, block, audit_requests):
        votes = 1

        grpc_block = block_chain_pb2.Block(index=block.index,
                                  hash=block.hash,
                                  previous_hash=block.previous_hash,
                                  timestamp=block.timestamp,
                                  merkle_root=block.merkle_root,
                                  file_audit_requests = audit_requests,
                                  file_audits = block.audits )

        for neighbor in self.neighbors:
            async with grpc.aio.insecure_channel(neighbor) as channel:
                stub = block_chain_pb2_grpc.BlockChainServiceStub(channel)

                response = await stub.proposeBlock(grpc_block)
                print("Propose block response received:", response)

                if response.vote:
                    votes += 1

        return grpc_block, votes


    async def whisper_audits(self, request, peer_address):
        async with grpc.aio.insecure_channel(peer_address) as channel:
            stub1 = block_chain_pb2_grpc.BlockChainServiceStub(channel)
            response = await stub1.wisperAuditRequest(request)
            print("Whisper response received:", response)


    async def process_queue(self):
        while True:
            request = await self.request_queue.get()

            self.append_to_mem_pool(request)

            if len(self.mem_pool) >= BLOCK_SIZE:
                if self.isvalidator:
                    print("Queue has reached BLOCK_SIZE, processing the queue ...")
                    await self.propose_block()


    def resolve_request_futures(self, new_block, grpc_block):
        for file_audit_request in grpc_block.file_audit_requests:
            future = AUDIT_REQUESTS_MAP[file_audit_request.req_id]
            future.set_result(new_block)


    async def commit_block(self, new_block, grpc_block):
        for neighbor in self.neighbors:
            async with grpc.aio.insecure_channel(neighbor) as channel:
                stub = block_chain_pb2_grpc.BlockChainServiceStub(channel)

                response = await stub.commitBlock(grpc_block)
                print("Commit block response received:", response)

        self.resolve_request_futures(new_block, grpc_block)


    async def propose_block(self):
        block_audits = []

        for audit_request_index in range(BLOCK_SIZE):
            block_audits.append(self.mem_pool[audit_request_index])

        # create merkle tree
        merkle_tree = MerkleTree(block_audits)

        # create new block in the chain
        new_block = self.create_block([audit.req_id for audit in block_audits], merkle_tree)

        try:
            grpc_block, votes = await self.send_block_proposal(new_block, block_audits)

            if votes >= 2:
                await self.commit_block(new_block, grpc_block)

        except Exception as e:
            print(f"An error occurred: {e}")


        print("Checking the queue...")
        await asyncio.sleep(3)


    async def get_genesis_block(self):
        async with grpc.aio.insecure_channel('[::]:50051') as channel:
            stub1 = block_chain_pb2_grpc.BlockChainServiceStub(channel)
            genesis_block_response = await stub1.getGenesisBlock(empty_pb2.Empty())
            print("Geneis Block  received!!")

            genesis_block = Block(index=genesis_block_response.index,
                              previous_hash=genesis_block_response.previous_hash,
                              audits = genesis_block_response.file_audits,
                              timestamp = genesis_block_response.timestamp,
                              merkle_root= genesis_block_response.merkle_root,
                              hash = genesis_block_response.hash
                              )
            
            self.append_block(genesis_block)
            
        
     

class FileAuditService(file_audit_pb2_grpc.FileAuditServiceServicer):

    def __init__(self,full_node):
        self.full_node = full_node

    async def SubmitAudit(self, request, context):
        print("Got a new audit request")
        #print(request)

        # Whisper it to all neighbors
        whisper_tasks = []

        try:
            neighbors = ['[::]:50052','[::]:50053']
            for neighbor in neighbors :
                whisper_task = asyncio.create_task(full_node.whisper_audits(request, neighbor))
                whisper_tasks.append(whisper_task)
        except Exception as e :
            print(f"An error occurred: {e}")

        for whisper_task in whisper_tasks:
            await whisper_task

        await full_node.request_queue.put(request)

        future = asyncio.get_event_loop().create_future()
        AUDIT_REQUESTS_MAP[request.req_id] = future
        block = await future
        del AUDIT_REQUESTS_MAP[request.req_id]

        # todo create response using block data
        response = file_audit_pb2.FileAuditResponse(status="success",
                                                    #merkle_proof = block.merkle_tree.get_merkle_proof(index),
                                                    #audit_index = block.index,
                                                    merkle_root = block.merkle_root)
        return response


class BlockChainService(block_chain_pb2_grpc.BlockChainServiceServicer):
    def __init__(self,full_node):
        self.full_node = full_node


    async def wisperAuditRequest(self, request, context):
        print("Got an audit whispered from a peer")
        await full_node.request_queue.put(request)
        return block_chain_pb2.WhisperResponse(status="success")


    async def proposeBlock(self, proposed_block_request, context):
        for file_audit_request in proposed_block_request.file_audit_requests:
            if file_audit_request in self.full_node.mem_pool:
                continue
            else:
                # verified_signature = todo()
                # if not verified_signature:
                #    return block_chain_pb2.ProposeResponse(status="failure", vote=False)
                pass # verify signature

        return block_chain_pb2.ProposeResponse(status="success", vote=True)


    async def commitBlock(self, proposed_block_request, context):
        print("Got Block Proposal")
        #print(proposed_block_request)

        #check for the last stored hash and prev hash from the request
        if self.full_node.blocks[-1].hash == proposed_block_request.previous_hash :
            print("Previous hash matches!!")
            
            file_audit_requests = proposed_block_request.file_audit_requests
           
            # Remove from MemPool
            for req in file_audit_requests :
                self.full_node.remove_from_mem_pool(req)
                
            
            new_block = Block(index=proposed_block_request.index,
                              previous_hash=proposed_block_request.previous_hash,
                              audits=proposed_block_request.file_audits,
                              timestamp = proposed_block_request.timestamp,
                              merkle_root= proposed_block_request.merkle_root,
                              hash = proposed_block_request.hash
                              )
            
            self.full_node.append_block(new_block)
            
            return block_chain_pb2.CommitResponse(status="success")
            
        else:
            
            
            print("Hash Didnot match")
            #print("file_audit_requests  -  ", proposed_block_request.previous_hash)
            #print("Previous block",self.full_node.blocks[-1].hash)
            
            return block_chain_pb2.CommitResponse(status="failure")
         
             
        
        
    
    async def getGenesisBlock(self, genesis_block_request, context):
        
        print("Got Genesis Block Request")
        
        genesis_block = self.full_node.blocks[0]
        genesis_block_response = block_chain_pb2.Block(index=genesis_block.index,
                                  hash=genesis_block.hash,
                                  previous_hash=genesis_block.previous_hash,
                                  timestamp=genesis_block.timestamp,
                                  merkle_root=genesis_block.merkle_root,
                                  )
        return genesis_block_response


async def serve(full_node):
    
    server = grpc.aio.server() 
    
    file_audit_service = FileAuditService(full_node)
    file_audit_pb2_grpc.add_FileAuditServiceServicer_to_server(file_audit_service, server)
    block_chain_pb2_grpc.add_BlockChainServiceServicer_to_server(BlockChainService(full_node),server)
    
    server.add_insecure_port('[::]:'+str(full_node.port))
    print("Server started on port ", full_node.port)
    
    if full_node.isvalidator:
        await asyncio.gather(server.start(), full_node.process_queue())
    else:
        await asyncio.gather(full_node.get_genesis_block(), server.start(), full_node.process_queue())
    
    await server.wait_for_termination()  

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int, help='port number', default=50051)
    parser.add_argument('--isvalidator',type=bool, help='validator flag', default=0)
    args = parser.parse_args()
    
    full_node = FullNode(args)
    
    print(full_node.port)
    print(full_node.isvalidator)
    
    
    asyncio.run(serve(full_node))
