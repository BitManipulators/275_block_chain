#!/usr/bin/env python3

import json
import time
import copy
import hashlib

def sha256(data):
    """Consistent hashing function"""
    return hashlib.sha256(str(data).encode()).hexdigest()

class TestAudit:
    """Simple class to mimic your audit structure"""
    def __init__(self, req_id, file_name, user_name):
        self.req_id = req_id
        self.file_info = {"file_name": file_name, "file_id": "file_123"}
        self.user_info = {"user_name": user_name, "user_id": "user_456"}
        self.access_type = "READ"
        self.timestamp = str(int(time.time()))

def test_tampering_detection():
    print("\n===== TESTING TAMPERING DETECTION =====")

    # Create a hash store (mimics your audit_hash_store)
    hash_store = {}

    # Create a test audit
    audit = TestAudit("test-audit-1", "original.txt", "test-user")
    req_id = audit.req_id
    print(f"Created test audit with ID: {req_id}")

    # Calculate and store its hash
    audit_hash = sha256(audit)
    hash_store[req_id] = audit_hash
    print(f"Stored original hash: {audit_hash}")

    # Test unmodified audit
    print("\nTesting unmodified audit...")
    current_hash = sha256(audit)
    print(f"Current hash: {current_hash}")
    if current_hash == hash_store[req_id]:
        print("Unmodified audit passes integrity check (good)")
    else:
        print("Unmodified audit fails integrity check (unexpected)")

    # Create a modified version with the same ID
    modified_audit = copy.deepcopy(audit)
    modified_audit.file_info["file_name"] = "tampered.txt"

    # Test modified audit
    print("\nTesting tampered audit...")
    tampered_hash = sha256(modified_audit)
    print(f"Tampered hash: {tampered_hash}")
    if tampered_hash != hash_store[req_id]:
        print("Tampered audit detected (good)")
    else:
        print("Tampered audit NOT detected (unexpected)")

    # Test the actual verification logic used in your system
    print("\nTesting verification function...")

    # This simulates your actual verification logic
    def simulate_verification(audit, hash_store):
        audit_hash = sha256(audit)
        if audit.req_id in hash_store:
            stored_hash = hash_store[audit.req_id]
            if stored_hash != audit_hash:
                print(f"⚠️ TAMPERING DETECTED: Hash mismatch")
                print(f"  Stored hash: {stored_hash}")
                print(f"  Current hash: {audit_hash}")
                return False
            else:
                print(f"✓ Integrity verified: Hashes match")
                return True
        return True  # No stored hash to compare

    # Test with original audit
    print("\nVerifying original audit:")
    result = simulate_verification(audit, hash_store)
    print(f"Original audit verification: {'PASSED' if result else 'FAILED'}")

    # Test with tampered audit
    print("\nVerifying tampered audit:")
    result = simulate_verification(modified_audit, hash_store)
    print(f"Tampered audit verification: {'FAILED (Good)' if not result else 'PASSED (Bad)'}")

    print("\n===== TAMPERING DETECTION TEST COMPLETE =====")

if __name__ == "__main__":
    test_tampering_detection()