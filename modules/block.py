import time
import hashlib
from modules.merkle import MerkleTree
from modules.signature import create_string

class Block :
    
    def __init__(self,index,previous_hash,audits,merkle_root=None,timestamp=None,hash=None):
        self.index = index
        self.previous_hash = previous_hash
        self.audits = audits
        self.timestamp = timestamp if timestamp else  time.time()
        self.merkle_root = merkle_root
        self.hash = hash if hash else self.compute_hash()
    
    def compute_hash(self):
        audit_strings = "".join([create_string(audit.req_id,audit.file_info,audit.user_info,audit.access_type,audit.timestamp) for audit in self.audits])
        block_string = f"{self.index}{self.previous_hash}{self.merkle_root}{audit_strings}"
        print(block_string)
        return hashlib.sha256(block_string.encode()).hexdigest()
    
    def get_merkle_root(self):
        
        merkle_tree = MerkleTree(self.audits)
        return merkle_tree.root
    
    @staticmethod
    def create_genesis_block():
        return Block(0,"0"*64,[])  
        
    
        
    
        