import requests as rq
import logging
import concurrent.futures
from random import choice
from time import sleep

import boto3
import botocore.exceptions

# Region lists that can be imported and used in the ApiGateway class
DEFAULT_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-north-1",
    "eu-central-1", "ca-central-1"
]

EXTRA_REGIONS = DEFAULT_REGIONS + [
    "ap-south-1", "ap-northeast-3", "ap-northeast-2",
    "ap-southeast-1", "ap-southeast-2", "ap-northeast-1",
    "sa-east-1"
]

# These regions require manual opt-in from AWS
ALL_REGIONS = EXTRA_REGIONS + [
    "ap-east-1", "af-south-1", "eu-south-1", "me-south-1"
]

# Enable Logging
logging.basicConfig(
    format = '[%(levelname)s] %(message)s',
    datefmt = '%Y-%m-%d %H:%M:%S %z',
)

class AWS:

    def __init__(self, region: str, access_id: str, access_secret: str):
        self.region = region

        session = boto3.session.Session()
        self.client = session.client(
            "apigateway",
            region_name=region,
            aws_access_key_id=access_id,
            aws_secret_access_key=access_secret
        )


# Inherits from HTTPAdapter so that we can edit each request before sending
class ApiGateway(rq.adapters.HTTPAdapter):

    def __init__(
        self, site,
        regions: str = DEFAULT_REGIONS,
        access_key_id: str = None,
        access_key_secret: str = None,
        log_level: str = "info",
    ):
        super().__init__()
        # Setup self.logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level.upper())

        # Set simple params from constructor
        if site.endswith("/"):
            self.site = site[:-1]
        else:
            self.site = site
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.api_name = site + " - IP Rotate API"
        self.regions = regions

    def _active_endpoints(self, aws: AWS) -> dict:
        """ Returns existing endpoint"""

        try:
            current_apis = aws.client.get_rest_apis()["items"]
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "UnrecognizedClientException":
                self.logger.error(f"Could not create region (some regions require manual enabling): {region}")
                return {
                    "success": False
                }
            else:
                raise e

        if len(current_apis) == 0:
            return {}
        for api in current_apis:
            if self.api_name == api["name"]:
                return {
                    "success": True,
                    "endpoint": f"{api['id']}.execute-api.{aws.region}.amazonaws.com",
                    "new": False
                }        

    def _init_gateway(self, region: str, force: bool = False) -> dict:
        # Connect to AWS
        aws = AWS(region, self.access_key_id, self.access_key_secret)

        # If API gateway already exists for host, return pre-existing endpoint
        current_endpoints = self._active_endpoints(aws)
        if not force and current_endpoints.get('success'):
            return self._active_endpoints(aws)

        # Create simple rest API resource
        create_api_response = aws.client.create_rest_api(
            name=self.api_name,
            endpointConfiguration={
                "types": [
                    "REGIONAL",
                ]
            }
        )

        # Get ID for new resource
        get_resource_response = aws.client.get_resources(
            restApiId=create_api_response["id"]
        )
        rest_api_id = create_api_response["id"]

        # Create "Resource" (wildcard proxy path)
        create_resource_response = aws.client.create_resource(
            restApiId=create_api_response["id"],
            parentId=get_resource_response["items"][0]["id"],
            pathPart="{proxy+}"
        )

        # Allow all methods to new resource
        aws.client.put_method(
            restApiId=create_api_response["id"],
            resourceId=get_resource_response["items"][0]["id"],
            httpMethod="ANY",
            authorizationType="NONE",
            requestParameters={
                "method.request.path.proxy": True,
                "method.request.header.X-My-X-Forwarded-For": True
            }
        )

        # Make new resource route traffic to new host
        aws.client.put_integration(
            restApiId=create_api_response["id"],
            resourceId=get_resource_response["items"][0]["id"],
            type="HTTP_PROXY",
            httpMethod="ANY",
            integrationHttpMethod="ANY",
            uri=self.site,
            connectionType="INTERNET",
            requestParameters={
                "integration.request.path.proxy": "method.request.path.proxy",
                "integration.request.header.X-Forwarded-For": "method.request.header.X-My-X-Forwarded-For"
            }
        )

        aws.client.put_method(
            restApiId=create_api_response["id"],
            resourceId=create_resource_response["id"],
            httpMethod="ANY",
            authorizationType="NONE",
            requestParameters={
                "method.request.path.proxy": True,
                "method.request.header.X-My-X-Forwarded-For": True
            }
        )

        aws.client.put_integration(
            restApiId=create_api_response["id"],
            resourceId=create_resource_response["id"],
            type="HTTP_PROXY",
            httpMethod="ANY",
            integrationHttpMethod="ANY",
            uri=f"{self.site}/{{proxy}}",
            connectionType="INTERNET",
            requestParameters={
                "integration.request.path.proxy": "method.request.path.proxy",
                "integration.request.header.X-Forwarded-For": "method.request.header.X-My-X-Forwarded-For"
            }
        )

        # Creates deployment resource, so that our API to be callable
        aws.client.create_deployment(
            restApiId=rest_api_id,
            stageName="ProxyStage"
        )

        # Create simple usage plan
        # TODO: Cleanup usage plans on delete
        aws.client.create_usage_plan(
            name="burpusage",
            description=rest_api_id,
            apiStages=[
                {
                    "apiId": rest_api_id,
                    "stage": "ProxyStage"
                }
            ]
        )

        # Return endpoint name and whether it show it is newly created
        return {
            "success": True,
            "endpoint": f"{rest_api_id}.execute-api.{region}.amazonaws.com",
            "new": True
        }

    def _delete_gateway(self, region: str) -> int:
        # Connect to AWS
        aws = AWS(region, self.access_key_id, self.access_key_secret)

        # Get all gateway apis (or skip if we don't have permission)
        try:
            apis = aws.client.get_rest_apis()["items"]
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "UnrecognizedClientException":
                return 0
        # Delete APIs matching target name
        api_iter = 0
        deleted = 0
        while api_iter < len(apis):
            api = apis[api_iter]
            # Check if hostname matches
            if self.api_name == api["name"]:
                # Attempt delete
                try:
                    success = aws.client.delete_rest_api(restApiId=api["id"])
                    if success:
                        deleted += 1
                    else:
                        self.logger.error(f"Failed to delete API {api['id']}.")
                except botocore.exceptions.ClientError as e:
                    # If timeout, retry
                    err_code = e.response["Error"]["Code"]
                    if err_code == "TooManyRequestsException":
                        sleep(1)
                        continue
                    else:
                        self.logger.error(f"Failed to delete API {api['id']}.")
            api_iter += 1
        return deleted

    def _check_endpoints(self, region: str) -> dict:
        # Connect to AWS
        aws = AWS(region, self.access_key_id, self.access_key_secret)
        return self._active_endpoints(aws)

    def send(self, request: rq.models.Response, stream: bool = False, timeout: int = None,
        verify: bool = True,
        cert: tuple = None,
        proxies: dict = None,
        ) -> rq.models.Response:
        # Get random endpoint
        endpoint = choice(self.endpoints)
        # Replace URL with our endpoint
        protocol, site = request.url.split("://", 1)
        site_path = site.split("/", 1)[1]
        request.url = "https://" + endpoint + "/ProxyStage/" + site_path
        # Replace host with endpoint host
        request.headers["Host"] = endpoint
        # Run original python requests send function
        return super().send(request, stream, timeout, verify, cert, proxies)

    def start(self, force=False, endpoints=[]) -> list:
        # If endpoints given already, assign and continue
        if len(endpoints) > 0:
            self.endpoints = endpoints
            return endpoints

        # Otherwise, start/locate new endpoints
        self.logger.debug(f"Starting API gateway{'s' if len(self.regions) > 1 else ''} in {len(self.regions)} regions.")
        self.endpoints = []
        new_endpoints = 0

        # Setup multithreading object
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            # Send each region creation to its own thread
            for region in self.regions:
                futures.append(executor.submit(self._init_gateway, region=region, force=force))
            # Get thread outputs
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result["success"]:
                    self.endpoints.append(result["endpoint"])
                    if result["new"]:
                        new_endpoints += 1

        self.logger.info(f"Using {len(self.endpoints)} endpoints with name '{self.api_name}' ({new_endpoints} new).")
        return self.endpoints

    def shutdown(self):
        self.logger.debug(f"Deleting gateway{'s' if len(self.regions) > 1 else ''} for site '{self.site}'.")
        futures = []

        # Setup multithreading object
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Send each region deletion to its own thread
            for region in self.regions:
                futures.append(executor.submit(self._delete_gateway, region=region))
            # Check outputs
            deleted = 0
            for future in concurrent.futures.as_completed(futures):
                deleted += future.result()
        self.logger.debug(f"Deleted {deleted} endpoints with for site '{self.site}'.")

    def status(self, force=False) -> dict:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            endpoints = []
            # Send each region creation to its own thread
            for region in self.regions:
                futures.append(executor.submit(self._check_endpoints, region=region))
            # Get thread outputs
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result["success"]:
                    endpoints.append(result["endpoint"])
        return {
            'endpoints': endpoints
        }