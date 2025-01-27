import json as _json
import logging as _logging
import pathlib as _pathlib
import requests as _requests

from requests_ip_rotator import ApiGateway as _ApiGateway


CREDENTIALS_FILE = './examples/credentials.json'
TEST_SITE = 'http://www.google.com'
EXTRA_REGIONS = ["us-east-1", "us-east-2"]
LOG_LEVEL = "debug"

def main() -> None:
    
    ### Load credentials 
    credentials_path = _pathlib.Path(CREDENTIALS_FILE)
    if not credentials_path.exists():
        _log.error(f"invalid credentials path: '{credentials}'")
    
    with open(credentials_path, 'r') as json_file:
        credentials = _json.load(json_file)
    
    # Create gateway object and initialise in AWS
    gateway = _ApiGateway(
        site = TEST_SITE,
        regions=EXTRA_REGIONS,
        access_key_id = credentials.get('access_key_id'),
        access_key_secret = credentials.get('access_key_secret'),
        log_level = LOG_LEVEL.upper()
    )

    # Remove any residual gateways and usage plans
    gateway.cleanup()

if __name__ == '__main__':
    
    ### Enable Logging
    _logging.basicConfig(
        format = '[%(levelname)s] %(message)s',
        datefmt = '%Y-%m-%d %H:%M:%S %z',
    )
    _log = _logging.getLogger(__name__)
    _log.setLevel(LOG_LEVEL.upper())

    ### Run main
    main()