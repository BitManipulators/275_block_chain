import asyncio
import grpc

from proto import common_pb2
from proto import common_pb2_grpc
from proto import file_audit_pb2
from proto import file_audit_pb2_grpc

from modules.merkle import MerkleTree

'''
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
auditsByFileId[0] = FileAudits()

'''

async def push_audit(audit_info,ip):
    
    async with grpc.aio.insecure_channel(ip) as channel:
        
        stub = file_audit_pb2_grpc.FileAuditServiceStub(channel)
        FileAuditRequest = common_pb2.FileAuditRequest(audit_info=audit_info,file_id="0")
        response = await stub.SubmitAudit(FileAuditRequest)
        merkle_proof = response.merkle_proof
        merkle_root = response.merkle_root
        
        print("File audit Mekle  Proof:", merkle_proof)
        print("File audit Mekle  Root:", merkle_root)
        print("File audit audit index",response.audit_index)
        print("Is valid", MerkleTree.verify_merkle_proof(str(audit_info),response.audit_index,merkle_proof,merkle_root))



async def run():
   
        audit_info1 = common_pb2.AuditInfo(audit_id=str(0) ,user_id="999", access_type=common_pb2.AccessType.READ)
        audit_info2 = common_pb2.AuditInfo(audit_id=str(1) ,user_id="996", access_type=common_pb2.AccessType.READ)
        audit_info3 = common_pb2.AuditInfo(audit_id=str(2) ,user_id="997", access_type=common_pb2.AccessType.READ)
        await asyncio.gather(push_audit(audit_info1,"[::]:50051"),push_audit(audit_info2,"[::]:50051"),push_audit(audit_info3,"[::]:50051"))


if __name__ == '__main__':
    # Run the client code asynchronously
    asyncio.run(run())
