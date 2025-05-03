import asyncio
import grpc

from proto import common_pb2
from proto import common_pb2_grpc
from proto import file_audit_pb2
from proto import file_audit_pb2_grpc

async def run():
   
    async with grpc.aio.insecure_channel('[::]:50051') as channel:
        
        stub = file_audit_pb2_grpc.FileAuditServiceStub(channel)
        
        file_info = common_pb2.FileInfo(file_id="1",file_name="File1")
        user_info = common_pb2.UserInfo(user_id ="1", user_name="suriya")
        FileAuditRequest = common_pb2.FileAuditRequest(file_info=file_info,user_info=user_info,access_type=common_pb2.AccessType.READ)
        
        #request = common_pb2.FileAuditRequest(req_id="123",signature="Hello")
        response = await stub.SubmitAudit(FileAuditRequest)
        print("File audit Client received:", response)
        

if __name__ == '__main__':
    # Run the client code asynchronously
    asyncio.run(run())
