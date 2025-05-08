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




BLOCK_SIZE = 3

class AuditDetails ():
    def __init__(self, audit_id , block_id):
        self.audit_id = audit_id
        self.block_id = block_id        


class ServerProperties () :
    def __init__(self,args):
        self.request_queue = asyncio.Queue()
        self.mem_pool = []
        self.port = args.port
        self.isvalidator = args.isvalidator
        self.blocks = [Block.create_genesis_block()]
        self.audit_details_byfile = {}  # Lookup data strcture based on File Id
    
    def create_block(self, audits, merkle_tree):
        
        last_block = server_properties.blocks[-1]
        new_block = Block(index = last_block.index+1,
                          previous_hash=last_block.hash,
                          audits=audits,
                          merkle_root=merkle_tree.root)
        
        self.blocks.append(new_block)
        return new_block
    
    def store_file_audits(self,file_id, audit_id, block_id):
        
        audit_details = AuditDetails(audit_id, block_id)
        if file_id in server_properties.audit_details_byfile :
            server_properties.audit_details_byfile[file_id].append(audit_details)
        else :
            server_properties.audit_details_byfile[file_id] = [audit_details]
        
        #print(server_properties.audit_details_byfile[file_id]) 
        
        

     

class FileAuditService(file_audit_pb2_grpc.FileAuditServiceServicer):

    def __init__(self,server_properties):
        self.server_properties = server_properties
    
    
    async def propose_block(self,block,fileaudit_requests,peer_address):
        
        async with grpc.aio.insecure_channel(peer_address) as channel:
            stub1 = block_chain_pb2_grpc.BlockChainServiceStub(channel)
            
            grpc_block = block_chain_pb2.Block(index=block.index,
                                  hash=block.hash,
                                  previous_hash=block.previous_hash,
                                  timestamp=block.timestamp,
                                  merkle_root=block.merkle_root,
                                  file_audit_requests = fileaudit_requests)
            
            response = await stub1.ProposeBlock(grpc_block)
            print("Propose response received:", response)    
    
    async def whisper_audits(self,request,peer_address):
        
        async with grpc.aio.insecure_channel(peer_address) as channel:
            stub1 = block_chain_pb2_grpc.BlockChainServiceStub(channel)
            response = await stub1.WisperAuditRequest(request)
            print("Whisper response received:", response) 
            
        
    async def SubmitAudit(self, request, context):
        
        print("Got a new audit request")
        print(request)
        
        #whisper it to the neighbor
        try :
            neighbors = ['[::]:50052','[::]:50053']
            for neighbor in neighbors :
                asyncio.create_task(self.whisper_audits(request,neighbor))
        
        except Exception as e :
            print(f"An error occured{e}")
        
        future = asyncio.Future()
        
        self.server_properties.mem_pool.append(request)
        await server_properties.request_queue.put((request,future))
        
        result = await future
        return result

       
    async def process_queue(self):
       
        while True :
            
            if  server_properties.request_queue.qsize() >= BLOCK_SIZE :
                
                print("Queue has reached BLOCK_SIZE, processing the queue ...")
                
                same_block_audits = []
                request_and_future_list = []
                
                
                for _ in range(BLOCK_SIZE):
                    req_and_future =  await server_properties.request_queue.get()
                    request_and_future_list.append(req_and_future)
                    audit_request = req_and_future[0]
                    audit_info = str(audit_request.audit_info)
                    same_block_audits.append(audit_info)

                
                # create merkle tree
                merkle_tree = MerkleTree(same_block_audits)
                
                # create new block in the chain
                new_block = self.server_properties.create_block(same_block_audits,merkle_tree)
                
                try :
                    
                    neighbors = ['[::]:50052','[::]:50053']
                    for neighbor in neighbors :
                        file_audit_requests = [request for request,_ in request_and_future_list ] 
                        asyncio.create_task(self.propose_block(new_block,file_audit_requests,neighbor))
                
                except Exception as e : 
                    print(f"An error occured{e}")
                
    
                
                
                index = 0
                for request,future  in request_and_future_list :
                    file_id = request.file_id
                    audit_id = request.audit_info.audit_id
                    block_hash = new_block.hash
                    
                    # persist the every audit's block information - 
                    self.server_properties.store_file_audits(file_id,audit_id,block_hash)
                    response = file_audit_pb2.FileAuditResponse(status="success",
                                                                merkle_proof = merkle_tree.get_merkle_proof(index), 
                                                                merkle_root = merkle_tree.root,
                                                                audit_index = index)
                    
                    
                    #Remove the processed request from mempool
                    self.server_properties.mem_pool.remove(request)
                    future.set_result(response)
                    index +=1
                    
            
            
            
            print("Checking the queue...")
            await asyncio.sleep(3)        


class BlockChainService(block_chain_pb2_grpc.BlockChainServiceServicer):
    
    def __init__(self,server_properties):
        self.server_properties = server_properties
    
    
    async def WisperAuditRequest(self,audit_request,context) :
        
        print("Got a audit from the peer",audit_request)
        self.server_properties.mem_pool.append(audit_request)
        return block_chain_pb2.WhisperResponse(status="success")
    
    async def ProposeBlock(self, proposed_block_request, context):
        
        print("Got Block Proposal")
        print(proposed_block_request)
        
        file_audit_requests = proposed_block_request.file_audit_requests
        # Remove from MemPool
        for req in file_audit_requests :
            self.server_properties.mem_pool.remove(req)
        
        
        
        return block_chain_pb2.ProposeResponse(status="success")


async def serve(server_properties):
    
    server = grpc.aio.server() 
    
    file_audit_service = FileAuditService(server_properties)
    file_audit_pb2_grpc.add_FileAuditServiceServicer_to_server(file_audit_service, server)
    block_chain_pb2_grpc.add_BlockChainServiceServicer_to_server(BlockChainService(server_properties),server)
    
    server.add_insecure_port('[::]:'+str(server_properties.port))
    print("Server started on port ", server_properties.port)
    
    if server_properties.isvalidator :
        await asyncio.gather(server.start(),file_audit_service.process_queue())
    else :
        await server.start()    
    
    await server.wait_for_termination()  

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int, help='port number', default=50051)
    parser.add_argument('--isvalidator',type=bool, help='validator flag', default=0)
    args = parser.parse_args()
    
    server_properties = ServerProperties(args)
    
    print(server_properties.port)
    print(server_properties.isvalidator)
    
    
    asyncio.run(serve(server_properties))
