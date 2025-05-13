import hashlib 

from modules.signature import create_string

class MerkleTree :
    def __init__(self,audits):
        self.levels , self.root = MerkleTree.build_merkle_tree(audits)
    
    def get_merkle_proof(self,index):
        
        proof = []
        
        for level in self.levels[:-1] :
            
            if len(level) % 2 == 1 :
                level.append(level[-1])
            sibling_index = index ^ 1
            proof.append(level[sibling_index])
            index = index // 2
        
        return proof    
    
    @staticmethod
    def verify_merkle_proof(audit,index,proof, root):
        
        current_hash = MerkleTree.sha256(audit)
        
        for sibling_hash in proof :
            if index % 2 == 0 :
                current_hash = MerkleTree.sha256(current_hash + sibling_hash)
            else :
                current_hash = MerkleTree.sha256(sibling_hash + current_hash)
            
            index = index // 2
        
        return current_hash == root         
        
      

    @staticmethod
    def sha256(data):
        return hashlib.sha256(str(data).encode()).hexdigest()
    
    @staticmethod
    def build_merkle_tree(audits):
        
        levels = []
        audit_strings = [
            create_string(audit.req_id,audit.file_info,audit.user_info,audit.access_type,audit.timestamp) for audit in audits]
        current_level = [MerkleTree.sha256(audit_string) for audit_string in audit_strings]
        levels.append(current_level)
        
        while len(current_level) > 1 :
            
            if len(current_level) % 2 == 1 :
                current_level.append(current_level[-1])
            
            next_level = []
            for i in range(0,len(current_level),2):
                combined = current_level[i] + current_level[i+1]
                next_level.append(MerkleTree.sha256(combined))
            
            current_level = next_level
            levels.append(current_level)    
                
        
        return [levels,levels[-1][0]]
        

'''
def merkle_root(audits):
    
    audit_hashes = [hashlib.sha256(str(audit).encode()).hexdigest() for audit in audits]
    
    while len(audit_hashes) > 1 :
        if len(audit_hashes) % 2 != 0 :
            audit_hashes.append(audit_hashes[-1])
        audit_hashes = [hashlib.sha256((audit_hashes[i]+audit_hashes[i+1]).encode()).hexdigest() for i in range(0,len(audit_hashes),2)]
    
    return audit_hashes[0]    

'''