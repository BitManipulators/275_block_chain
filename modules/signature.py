#!/usr/bin/python3

import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from pathlib import Path


def create_string(req_id, file_info, user_info, access_type, timestamp):
    string_to_sign = ",".join([
        req_id,
        str(file_info.file_id),
        file_info.file_name,
        str(user_info.user_id),
        user_info.user_name,
        str(access_type),
        str(timestamp),
    ])

    return string_to_sign


def create_signature(req_id, file_info, user_info, access_type, timestamp):
    string_to_sign = create_string(req_id, file_info, user_info, access_type, timestamp)

    print(string_to_sign)

    home_dir = str(Path.home())

    # Load private key from ~/.ssh/id_rsa
    with open(f"{home_dir}/.ssh/id_rsa", "rb") as private_key_file:
        private_key = serialization.load_ssh_private_key(
            private_key_file.read(),
            password=None,
        )

    signature = private_key.sign(
        string_to_sign.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    with open(f"{home_dir}/.ssh/id_rsa.pub", "r") as public_key_file:
        public_key = public_key_file.read()

    return base64.b64encode(signature).decode(), public_key


def verify_signature(file_audit):
    string_to_verify = create_string(file_audit.req_id,
                                     file_audit.file_info,
                                     file_audit.user_info,
                                     file_audit.access_type,
                                     file_audit.timestamp)

    public_key = serialization.load_ssh_public_key(file_audit.public_key.encode('utf-8'))

    try:
        public_key.verify(
            base64.b64decode(file_audit.signature.encode('utf-8')),
            string_to_verify.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except:
        return False
