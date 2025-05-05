from modules.merkle import MerkleTree
   

audits = ["Brandon","Aish", "Suriya"]
print("Merkle tree's root")

mtree = MerkleTree(audits)
print(mtree.root)  

proof_of_index2 = mtree.get_merkle_proof(2)
proof_of_index1 = mtree.get_merkle_proof(1)
print("Merkle tree's prof of index 2", proof_of_index2)

print("Is merkle proof valid ", MerkleTree.verify_merkle_proof(audits[2],2,proof_of_index2,mtree.root))


# This should be invalid
print("Is merkle proof valid ", MerkleTree.verify_merkle_proof(audits[2],2,proof_of_index1,mtree.root))