ssh user@98.70.24.178
# upload check_iceberg.py to the host (scp / paste / git)
export LAKEHOUSE_ACCESS_KEY=admin
export LAKEHOUSE_SECRET_KEY=password123
export LAKEHOUSE_REST_URI=http://localhost:8181
export LAKEHOUSE_S3_ENDPOINT=http://localhost:9000
python3 check_iceberg.py