#!/usr/bin/env python3

import os
import json
import hashlib
import argparse
from google.protobuf.json_format import ParseDict
from common_pb2 import FileAudit

class BlockchainVerifier:
    def __init__(self, blocks_dir="./blocks"):
        self.blocks_dir = blocks_dir
        self.blocks = self.load_blocks()

    def load_blocks(self):
        """Load all blocks from disk"""
        blocks = []
        if os.path.exists(self.blocks_dir):
            for fname in sorted(os.listdir(self.blocks_dir)):
                if fname.endswith(".json"):
                    with open(os.path.join(self.blocks_dir, fname), 'r') as f:
                        try:
                            block_dict = json.load(f)
                            block_dict['filename'] = fname  # Store filename for reference
                            blocks.append(block_dict)
                        except json.JSONDecodeError:
                            print(f"Error loading block from {fname}: Invalid JSON")

        print(f"Loaded {len(blocks)} block(s) from disk.")
        return blocks

    def find_block_with_audit(self, req_id):
        """Find a block containing the specified audit req_id"""
        for block in self.blocks:
            for audit in block.get('audits', []):
                if audit.get('req_id') == req_id:
                    return block, audit
        return None, None

    def verify_block_integrity(self, block):
        """Verify a block's integrity by recalculating its Merkle root"""
        stored_merkle_root = block.get('merkle_root')
        if not stored_merkle_root:
            return False, "Block does not contain a Merkle root"

        # Convert audit dictionaries to FileAudit protobuf objects
        audit_objects = []
        for audit_dict in block.get('audits', []):
            audit_obj = ParseDict(audit_dict, FileAudit())
            audit_objects.append(audit_obj)

        # Recalculate the Merkle root
        recreated_root = self.calculate_merkle_root(audit_objects)

        # Check if the recreated root matches the stored root
        is_valid = recreated_root == stored_merkle_root

        return is_valid, {
            'stored_root': stored_merkle_root,
            'recreated_root': recreated_root
        }

    def verify_blockchain_integrity(self):
        """Verify the integrity of the entire blockchain"""
        if not self.blocks:
            return True, "No blocks to verify"

        for i in range(1, len(self.blocks)):
            # Each block should reference the previous block's hash
            prev_block = self.blocks[i-1]
            curr_block = self.blocks[i]

            prev_hash = prev_block.get('hash')
            curr_prev_hash = curr_block.get('previous_hash')

            if prev_hash != curr_prev_hash:
                return False, f"Chain broken at block {i}: previous hash mismatch"

            # Verify each block's Merkle root
            is_valid, _ = self.verify_block_integrity(curr_block)
            if not is_valid:
                return False, f"Block {i} has invalid Merkle root"

        return True, "Blockchain integrity verified"

    @staticmethod
    def sha256(data):
        """Replicate the exact hashing method from your MerkleTree class"""
        return hashlib.sha256(str(data).encode()).hexdigest()

    def calculate_merkle_root(self, audits):
        """Calculate the Merkle root from a list of audits"""
        if not audits:
            return None

        # Create leaf nodes
        leaf_nodes = [self.sha256(audit) for audit in audits]

        # If there's only one leaf, it's also the root
        if len(leaf_nodes) == 1:
            return leaf_nodes[0]

        # Build the Merkle tree
        current_level = leaf_nodes
        while len(current_level) > 1:
            if len(current_level) % 2 == 1:
                current_level.append(current_level[-1])

            next_level = []
            for i in range(0, len(current_level), 2):
                combined = current_level[i] + current_level[i+1]
                next_level.append(self.sha256(combined))

            current_level = next_level

        return current_level[0]

    def print_audit_details(self, audit_dict):
        """Print detailed information about an audit"""
        print("\nAudit Details:")
        print(f"  Req ID:       {audit_dict.get('req_id')}")

        file_info = audit_dict.get('file_info', {})
        print(f"  File:         {file_info.get('file_name')} (ID: {file_info.get('file_id')})")

        user_info = audit_dict.get('user_info', {})
        print(f"  User:         {user_info.get('user_name')} (ID: {user_info.get('user_id')})")

        print(f"  Access Type:  {audit_dict.get('access_type')}")
        print(f"  Timestamp:    {audit_dict.get('timestamp')}")

        # Show abbreviated signatures for readability
        signature = audit_dict.get('signature', '')
        if len(signature) > 20:
            signature = signature[:10] + "..." + signature[-10:]
        print(f"  Signature:    {signature}")

        # Check if signature is valid
        audit_obj = ParseDict(audit_dict, FileAudit())
        from modules.signature import verify_signature
        try:
            is_valid = verify_signature(audit_obj)
            print(f"  Signature Valid: {'Yes' if is_valid else 'No'}")
        except Exception as e:
            print(f"  Signature Verification Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Blockchain verification tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Find audit command
    find_parser = subparsers.add_parser("find", help="Find a block containing a specific audit")
    find_parser.add_argument("req_id", help="Request ID to search for")

    # Verify block command
    verify_parser = subparsers.add_parser("verify", help="Verify a specific block")
    verify_parser.add_argument("block_num", type=int, help="Block number to verify")

    # Verify chain command
    subparsers.add_parser("chain", help="Verify the entire blockchain")

    # List blocks command
    subparsers.add_parser("list", help="List all blocks in the blockchain")

    # Add this after the other subparsers
    audit_parser = subparsers.add_parser("print_audit_details", help="Print details of an audit in a specific block")
    audit_parser.add_argument("block_num", type=int, help="Block number containing the audit")
    audit_parser.add_argument("audit_index", type=int, help="Index of the audit in the block (usually 0)", default=0, nargs='?')

    args = parser.parse_args()

    verifier = BlockchainVerifier()

    if args.command == "find":
        block, audit = verifier.find_block_with_audit(args.req_id)
        if block:
            print(f"Found audit with req_id '{args.req_id}' in block {block.get('filename')}")

            # Print detailed information about the block
            print("\nBlock Details:")
            print(f"  Filename:     {block.get('filename')}")
            print(f"  Index:        {block.get('index', block.get('id', 'unknown'))}")
            print(f"  Hash:         {block.get('hash')}")
            print(f"  Previous Hash: {block.get('previous_hash')}")
            print(f"  Merkle Root:  {block.get('merkle_root')}")
            print(f"  Audits:       {len(block.get('audits', []))}")

            # Verify the block's integrity
            is_valid, details = verifier.verify_block_integrity(block)
            print(f"\nBlock integrity: {'VALID' if is_valid else 'INVALID'}")
            if not is_valid:
                print(f"  Stored Root:    {details['stored_root']}")
                print(f"  Recreated Root: {details['recreated_root']}")

            # Print details about the audit
            verifier.print_audit_details(audit)
        else:
            print(f"No block found containing audit with req_id '{args.req_id}'")

    elif args.command == "verify":
        if args.block_num < len(verifier.blocks):
            block = verifier.blocks[args.block_num]
            print(f"Verifying block {block.get('filename')}")

            is_valid, details = verifier.verify_block_integrity(block)
            print(f"Block integrity: {'VALID' if is_valid else 'INVALID'}")

            if not is_valid:
                print(f"  Stored Root:    {details['stored_root']}")
                print(f"  Recreated Root: {details['recreated_root']}")

            print("\nBlock Details:")
            print(f"  Filename:     {block.get('filename')}")
            print(f"  Index:        {block.get('index', block.get('id', 'unknown'))}")
            print(f"  Hash:         {block.get('hash')}")
            print(f"  Previous Hash: {block.get('previous_hash')}")
            print(f"  Merkle Root:  {block.get('merkle_root')}")
            print(f"  Audits:       {len(block.get('audits', []))}")
        else:
            print(f"Block number {args.block_num} not found")

    elif args.command == "chain":
        is_valid, message = verifier.verify_blockchain_integrity()
        print(f"Blockchain integrity: {'VALID' if is_valid else 'INVALID'}")
        print(f"  {message}")

    elif args.command == "list":
        print("\nBlocks in the blockchain:")
        for i, block in enumerate(verifier.blocks):
            print(f"  {i}: {block.get('filename')} - Hash: {block.get('hash')[:10]}... Audits: {len(block.get('audits', []))}")

    elif args.command == "print_audit_details":
        if args.block_num < len(verifier.blocks):
            block = verifier.blocks[args.block_num]
            audits = block.get('audits', [])

            if args.audit_index < len(audits):
                audit = audits[args.audit_index]
                print(f"Printing details for audit at index {args.audit_index} in block {block.get('filename')}")
                verifier.print_audit_details(audit)
            else:
                print(f"Audit index {args.audit_index} out of range. Block has {len(audits)} audits.")
        else:
            print(f"Block number {args.block_num} not found")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()