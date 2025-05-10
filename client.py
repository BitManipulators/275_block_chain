#!/usr/bin/env python3

import argparse
import asyncio
import grpc
import random
import time
import uuid
import yaml

import common_pb2
import common_pb2_grpc
import file_audit_pb2
import file_audit_pb2_grpc

from enum import Enum

from modules.merkle import MerkleTree
from modules.signature import create_signature, verify_signature


TASKS = set()
REQUESTS = {}
REQUEST_TIMEOUT_SECONDS = 30
TASK_CLEANUP_INTERVAL_SECONDS = .5


# Define choices that can be randomly selected from
file_infos = []
for file_id in range(0, 10):
    file_infos.append(common_pb2.FileInfo(file_id=str(file_id), file_name=f"file_{file_id}"))

user_infos = []
for user_id in range(1000, 1100):
    user_infos.append(common_pb2.UserInfo(user_id=str(user_id), user_name=f"user_{user_id}"))

access_types = [
    common_pb2.AccessType.READ,
    common_pb2.AccessType.WRITE,
    common_pb2.AccessType.UPDATE,
    common_pb2.AccessType.DELETE
]


class RequestDistributionStrategy(Enum):
    RANDOM = "random"
    ROUND_ROBIN = "round_robin"

    def __str__(self):
        return self.value


async def send_request(stub, request):
    try:
        return await asyncio.wait_for(stub.SubmitAudit(request), timeout=REQUEST_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        print("[TIMEOUT] Request timed out")
    except grpc.aio.AioRpcError as e:
        print(f"[GRPC ERROR] {e.code()}: {e.details()}")


def create_random_request(rng):
    # Use uuid to generate an request id
    req_id = str(uuid.uuid4())
    timestamp = int(time.time())

    # Randomly pick from lists to construct file audit requests
    file_info = file_infos[rng.randint(0, len(file_infos) - 1)]
    user_info = user_infos[rng.randint(0, len(user_infos) - 1)]
    access_type = access_types[rng.randint(0, len(access_types) - 1)]

    signature, public_key = create_signature(req_id, file_info, user_info, access_type, timestamp)

    file_audit = common_pb2.FileAudit(
        req_id = req_id,
        file_info=file_info,
        user_info=user_info,
        access_type=access_type,
        timestamp=timestamp,
        signature=signature,
        public_key=public_key,
    )

    verified = verify_signature(file_audit)
    if not verified:
        raise Exception("Signature was not verified!")

    print(f"Created request: {req_id} with file_id {file_info.file_id}, user_id {user_info.user_id}, and signature {signature}")

    return file_audit


async def client_loop(args, config):
    global TASKS

    max_total_requests = args.max_total_requests
    max_num_requests_in_flight = args.max_num_requests_in_flight
    request_distribution_strategy = args.request_distribution_strategy

    request_count = 0
    round_robin_index = 0

    infinite_requests = max_total_requests is None

    # Create random number generator
    rng = random.Random(42)  # Fixed seed for determinism

    # Create channels and stubs per server
    channels = [grpc.aio.insecure_channel(server['address']) for server in config['servers']]
    stubs = [file_audit_pb2_grpc.FileAuditServiceStub(ch) for ch in channels]

    # Warm-up
    await asyncio.gather(*(ch.channel_ready() for ch in channels))
    print("All channels ready.")

    while infinite_requests or TASKS or request_count < max_total_requests:
        # Clean up any completed tasks
        done = {t for t in TASKS if t.done()}
        for t in done:
            try:
                response = t.result()

                #audit_index = response.audit_index
                #merkle_proof = response.merkle_proof
                #merkle_root = response.merkle_root

                #print(f"[✓] Got response for {audit_index}! Merkle proof {merkle_proof} and merkle root: {merkle_root}")
                print(f"[✓] Got response! Status: {response.status}")
                #print("Is valid", MerkleTree.verify_merkle_proof(str(audit_info), audit_index, merkle_proof, merkle_root))
            except Exception as e:
                print(f"[!] Request failed: {e}")
            TASKS.remove(t)

        can_send_more_requests = infinite_requests or request_count < max_total_requests

        # Fill up tasks to max in flight again, or stop if max total is reached
        while len(TASKS) < max_num_requests_in_flight and can_send_more_requests:
            request_count += 1

            # Choose server stub based on strategy
            if request_distribution_strategy == RequestDistributionStrategy.ROUND_ROBIN:
                stub = stubs[round_robin_index % len(stubs)]
                round_robin_index += 1
            else:
                stub = random.choice(stubs)

            request = create_random_request(rng)
            task = asyncio.create_task(send_request(stub, request))
            TASKS.add(task)

            can_send_more_requests = infinite_requests or request_count < max_total_requests

        await asyncio.sleep(TASK_CLEANUP_INTERVAL_SECONDS)


def parse_args():
    parser = argparse.ArgumentParser(description="Async gRPC load generator")

    parser.add_argument(
        "--request-distribution-strategy",
        type=RequestDistributionStrategy,
        choices=list(RequestDistributionStrategy),
        default=RequestDistributionStrategy.ROUND_ROBIN,
        help="Server selection strategy (random or round_robin)"
    )
    parser.add_argument(
        "--max-num-requests-in-flight",
        type=int,
        default=3,
        help="Maximum number of concurrent requests in flight at same time"
    )
    parser.add_argument(
        "--max-total-requests",
        type=int,
        default=3,
        help="Total number of requests to send before shutdown (omit or 0 for infinite)"
    )

    return parser.parse_args()


async def run():
    args = parse_args()

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    await client_loop(args, config)


if __name__ == '__main__':
    # Run the client code asynchronously
    asyncio.run(run())
