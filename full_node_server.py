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

BLOCK_SIZE = 2

class ServerProperties () :
    def __init__(self,args):
        self.request_queue = asyncio.Queue()
        self.port = args.port
        self.isvalidator = args.isvalidator
        self.blocks = [Block.create_genesis_block()]
            

class FileAuditService(file_audit_pb2_grpc.FileAuditServiceServicer):

    def __init__(self,server_properties):
        self.server_properties = server_properties
    
    '''    
    async def whisper_audits(request):
        
        async with grpc.aio.insecure_channel('[::]:50052') as channel:
            stub1 = block_chain_pb2_grpc.BlockChainServiceStub(channel)
            request = common_pb2.FileAuditRequest(req_id="123")
            response = await stub1.WisperAuditRequest(request)
            print("Whiseper response received:", response) '''
            
        
    
    async def SubmitAudit(self, request, context):
        
        print("Printing the request")
        print(request)
        future = asyncio.Future()
        await server_properties.request_queue.put((request,future))
        print(server_properties.request_queue.qsize())
        result = await future
        return result

    
    async def process_queue(self):
       
        while True :
            
            if  server_properties.request_queue.qsize() >= BLOCK_SIZE :
                
                print("Queue has reached BLOCK_SIZE, processing the queue ...")
                
                audits = []
                req_list = []
                
                for _ in range(BLOCK_SIZE):
                    req =  await server_properties.request_queue.get()
                    req_list.append(req)
                    file_info = str(req[0].file_info)
                    audits.append(file_info)

                merkle_tree = MerkleTree(audits)
                
                last_block = server_properties.blocks[-1]
                new_block = Block(index = last_block.index+1,
                          previous_hash=last_block.hash,
                         audits=audits,merkle_root=merkle_tree.root)
        
                server_properties.blocks.append(new_block)
                
                block_header = file_audit_pb2.BlockHeader(previous_block_hash=new_block.previous_hash,
                                                          merkle_root=new_block.merkle_root)
                
                for req,future  in req_list :
                    future.set_result(file_audit_pb2.FileAuditResponse(block_header=block_header, status="success"))

            print("Checking the queue...")
            await asyncio.sleep(3)        


class BlockChainService(block_chain_pb2_grpc.BlockChainServiceServicer):
    
    def __init__(self,server_properties):
        self.server_properties = server_properties
    
    '''
    async def WisperAuditRequest(self,request,context) :
        print(request)
        return block_chain_pb2.WhisperResponse(status="success") '''


async def serve(server_properties):
    
    server = grpc.aio.server() 
    
    file_audit = FileAuditService(server_properties)
    file_audit_pb2_grpc.add_FileAuditServiceServicer_to_server(file_audit, server)
    block_chain_pb2_grpc.add_BlockChainServiceServicer_to_server(BlockChainService(server_properties),server)
    
    server.add_insecure_port('[::]:'+str(server_properties.port))
    print("Server started on port ", server_properties.port)
    
    await asyncio.gather(server.start(),file_audit.process_queue())
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
