import time
import hashlib
from modules.merkle import MerkleTree

class Block :
    
    def __init__(self,index,previous_hash,audits,merkle_root=None):
        self.index = index
        self.previous_hash = previous_hash
        self.audits = audits
        self.timestamp = time.time()
        self.merkle_root = merkle_root
        self.hash = self.compute_hash()
    
    def compute_hash(self):
        block_string = f"{self.index}{self.previous_hash},{self.audits},{self.timestamp},{self.merkle_root}"
        return hashlib.sha256(block_string.encode()).hexdigest() 
    
    def get_merkle_root(self):
        
        merkle_tree = MerkleTree(self.audits)
        return merkle_tree.root
    
    @staticmethod
    def create_genesis_block():
        return Block(0,"0"*64,[])  
        
    
        
    
        