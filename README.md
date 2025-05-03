# 275_block_chain

## To generate proto - Run this from Home directory

- python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. proto/block_chain.proto

## To Run server

- python full_node_server.py --port 50051 --isvalidator 1