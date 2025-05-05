import asyncio
import grpc

from proto import common_pb2
from proto import common_pb2_grpc
from proto import file_audit_pb2
from proto import file_audit_pb2_grpc

from modules.merkle import MerkleTree


from enum import Enum




class AccessType(Enum):
    READ = 1,
    UPDATE = 2,
    DELETE = 3
    

class Audit :
    def __init__(self, audit_id, user_id, file_id, access_type):
        
        self.audit_id = audit_id
        self.user_id = user_id
        self.file_id = file_id 
        self.access_type = access_type    


class FileAudits :
    
    def __init__(self):
        self.audits = []
        self.next_id = 0
    
    def add_audits(self,audit):
        self.audits.append(audit)
        self.next_id += 1
    
    def get_next_id(self):
        return self.next_id
        
    
auditsByFileId = {}
auditsByFileId[123] = FileAudits()




async def run():
   
    async with grpc.aio.insecure_channel('[::]:50051') as channel:
        
        
        stub = file_audit_pb2_grpc.FileAuditServiceStub(channel)
        
        audit_id = auditsByFileId[123].get_next_id()
        audit_info = common_pb2.AuditInfo(audit_id=str(audit_id) ,user_id="999", access_type=common_pb2.AccessType.READ)
        response_header = {} 
        FileAuditRequest = common_pb2.FileAuditRequest(audit_info=audit_info,file_id="123")
        id_response_pair = (audit_id, response_header)
        auditsByFileId[123].add_audits(id_response_pair)
        
        response = await stub.SubmitAudit(FileAuditRequest)
        
        merkle_proof = response.merkle_proof
        merkle_root = response.merkle_root
        
        print("File audit Mekle  Proof:", merkle_proof)
        print("File audit Mekle  Root:", merkle_root)
        print("File audit audit index",response.audit_index)
        
        print("Is valid", MerkleTree.verify_merkle_proof(str(audit_info),response.audit_index,merkle_proof,merkle_root))

if __name__ == '__main__':
    # Run the client code asynchronously
    asyncio.run(run())
