
import boto3
import botocore.exceptions

from .errors import ApiConnectionError
from .logger import Logger

__all__ = ['AWS']


class AWS:

    def __init__(self, region: str, access_id: str, access_secret: str, log_level: str):
        self.region = region
        self._logger = Logger('aws-services')
        self._logger.set_level(log_level.upper())
       
        session = boto3.session.Session()
        try:
            self.client = session.client(
                "apigateway",
                region_name=region,
                aws_access_key_id=access_id,
                aws_secret_access_key=access_secret,
            )
            self._logger.debug(f"Successfully authenticated to AWS region: '{region}'")
        except botocore.exceptions as err:
            raise ApiConnectionError(err)