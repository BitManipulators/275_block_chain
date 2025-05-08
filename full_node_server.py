import asyncio
import grpc
import argparse
import time


from proto import common_pb2
from proto import common_pb2_grpc
from proto import file_audit_pb2
from proto import file_audit_pb2_grpc


from proto import block_chain_pb2
from proto import block_chain_pb2_grpc


from modules.block import Block 
from modules.merkle import MerkleTree 

from google.protobuf import empty_pb2




BLOCK_SIZE = 3

class AuditDetails ():
    def __init__(self, audit_id , block_id):
        self.audit_id = audit_id
        self.block_id = block_id        


class FullNode () :
    def __init__(self,args):
        self.request_queue = asyncio.Queue()
        self.mem_pool = []
        self.port = args.port
        self.isvalidator = args.isvalidator
        self.blocks = [Block.create_genesis_block()]
        self.audit_details_byfile = {}  # Lookup data strcture based on File Id
    
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
            
    
    def store_file_audits(self,file_id, audit_id, block_id):
        
        audit_details = AuditDetails(audit_id, block_id)
        if file_id in self.audit_details_byfile :
            self.audit_details_byfile[file_id].append(audit_details)
        else :
            self.audit_details_byfile[file_id] = [audit_details]
        
    
    async def propose_block(self,block,fileaudit_requests,peer_address):
        
        async with grpc.aio.insecure_channel(peer_address) as channel:
            stub1 = block_chain_pb2_grpc.BlockChainServiceStub(channel)
            
            grpc_block = block_chain_pb2.Block(index=block.index,
                                  hash=block.hash,
                                  previous_hash=block.previous_hash,
                                  timestamp=block.timestamp,
                                  merkle_root=block.merkle_root,
                                  file_audit_requests = fileaudit_requests,
                                  file_audits = block.audits )
            
            response = await stub1.proposeBlock(grpc_block)
            print("Propose response received:", response)    
    
    
    async def whisper_audits(self,request,peer_address):
        
        async with grpc.aio.insecure_channel(peer_address) as channel:
            stub1 = block_chain_pb2_grpc.BlockChainServiceStub(channel)
            response = await stub1.wisperAuditRequest(request)
            print("Whisper response received:", response)  
            
    
    async def process_queue(self):
       
        while True :
            
            if  self.request_queue.qsize() >= BLOCK_SIZE :
                
                print("Queue has reached BLOCK_SIZE, processing the queue ...")
                
                same_block_audits = []
                request_and_future_list = []
                
                
                for _ in range(BLOCK_SIZE):
                    req_and_future =  await self.request_queue.get()
                    request_and_future_list.append(req_and_future)
                    audit_request = req_and_future[0]
                    audit_info = str(audit_request.audit_info)
                    same_block_audits.append(audit_info)

                
                # create merkle tree
                merkle_tree = MerkleTree(same_block_audits)
                
                # create new block in the chain
                new_block = self.create_block(same_block_audits,merkle_tree)
                
                try :
                    
                    neighbors_ports = ['50052','50053']
                    for neighbor_port in neighbors_ports :
                
                        if neighbor_port == full_node.port :
                            continue
                
                        neighbor_ip = "[::]:" + neighbor_port
                        file_audit_requests = [request for request,_ in request_and_future_list ] 
                        asyncio.create_task(self.propose_block(new_block,file_audit_requests,neighbor_ip))
                
                except Exception as e : 
                    print(f"An error occured{e}")
                
    
                
                
                index = 0
                for request,future  in request_and_future_list :
                    
                    
                    # persist the every audit's block information -
                    # file_id = request.file_id
                    # audit_id = request.audit_info.audit_id
                    # block_hash = new_block.hash
                     
                    #self.store_file_audits(file_id,audit_id,block_hash)
                    
                    response = file_audit_pb2.FileAuditResponse(status="success",
                                                                merkle_proof = merkle_tree.get_merkle_proof(index), 
                                                                merkle_root = merkle_tree.root,
                                                                audit_index = index)
                    
                    
                    #Remove the processed request from mempool
                    self.mem_pool.remove(request)
                    future.set_result(response)
                    index +=1
                    
            
            
            
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
        
        #whisper it to the neighbor
        try :
            
            neighbors_ports = ['50052','50053']
            for neighbor_port in neighbors_ports :
                
                if neighbor_port == full_node.port :
                    continue
                
                neighbor_ip = "[::]:" + neighbor_port
                asyncio.create_task(full_node.whisper_audits(request,neighbor_ip))
        
        except Exception as e :
            print(f"An error occured{e}")
        
        future = asyncio.Future()
        
        
        self.full_node.append_to_mem_pool(request)
        await full_node.request_queue.put((request,future))
        
        result = await future
        return result

       
    

class BlockChainService(block_chain_pb2_grpc.BlockChainServiceServicer):
    
    def __init__(self,full_node):
        self.full_node = full_node
    
    
    async def wisperAuditRequest(self,audit_request,context) :
        
        print("Got a audit from the peer")
        self.full_node.append_to_mem_pool(audit_request)
        return block_chain_pb2.WhisperResponse(status="success")
    
    async def proposeBlock(self, proposed_block_request, context):
        
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
            
            return block_chain_pb2.ProposeResponse(status="success")
            
        else :
            
            
            print("Hash Didnot match")
            #print("file_audit_requests  -  ", proposed_block_request.previous_hash)
            #print("Previous block",self.full_node.blocks[-1].hash)
            
            return block_chain_pb2.ProposeResponse(status="failure")
         
             
        
        
    
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
    
    if full_node.isvalidator :
        await asyncio.gather(full_node.process_queue(),server.start())
    else :
        await asyncio.gather(full_node.get_genesis_block(),server.start())    
    
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
