import requests as rq
import logging
import concurrent.futures
import string
from random import choice, choices
from urllib.parse import urlparse
from time import sleep

import botocore.exceptions

from .aws import AWS
from .errors import ApiConnectionError
from .logger import Logger
from .models import (
    Connection,
    Endpoint,
    Plan,
)
from .regions import (
    DEFAULT_REGIONS,
    EXTRA_REGIONS,
    ALL_REGIONS,
)


__all__ = ['ApiGateway']


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
        # Define class attributes
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret


        site_loc = f"{urlparse(site).netloc}{urlparse(site).path}"
        self.api_name = "requests_ip_rotator_api-{i}-{s}".format(i=''.join(choices(string.ascii_lowercase, k=8)), s=site_loc)
        self.usage_plan_name = "requests_ip_rotator_usage-{i}-{s}".format(i=''.join(choices(string.ascii_lowercase, k=8)), s=site_loc)
        self.regions = regions
        self.log_level = log_level

        # Setup logger
        self._logger = Logger(f"aws-api-gateway for regions: '{self.regions}'")
        self._logger.set_level(self.log_level.upper())

        # Set simple params from constructor
        if site.endswith("/"):
            self.site = site[:-1]
        else:
            self.site = site


    def _existing_connection(self, aws: AWS) -> Connection:
        """ Returns existing endpoint"""

        try:
            current_apis = aws.client.get_rest_apis().get('items')
        except botocore.exceptions.ClientError as e:
            if e.response.get('Error').get('Code') == "UnrecognizedClientException":
                self._logger.error(f"Could not create region (some regions require manual enabling): {region}")
                return Connection(success=False)
            raise ApiConnectionError(e)

        if len(current_apis) == 0:
            return Connection()
        for api in current_apis:
            if self.api_name == api.get('name'):
                return Connection(
                    success = True,
                    endpoint = f"{api.get('id')}.execute-api.{aws.region}.amazonaws.com",
                    new = False,
                )
    def _active_endpoints(self, aws: AWS, limit=500) -> list:
        """ Returns existing endpoint"""

        try:
            current_apis = aws.client.get_rest_apis(limit=limit).get('items')
        except botocore.exceptions.ClientError as e:
            if e.response.get('Error').get('Code') == "UnrecognizedClientException":
                return self._logger.error(f"Could not create region (some regions require manual enabling): {region}")
            raise ApiConnectionError(e)
        endpoints = []
        for api in current_apis:
            endpoint = Endpoint(
                identity = api.get('id'),
                name = api.get('name'),
                created_date = api.get('createdDate'),
                key_source = api.get('apiKeySource'),
                config = api.get('endpointConfiguration'),
                url = f"{api.get('id')}.execute-api.{aws.region}.amazonaws.com",
            )
            endpoints.append(endpoint)
        return endpoints

    def _active_usage_plans(self, aws: AWS, limit=500) -> list:
        """ Returns existing endpoint"""

        try:
            current_usage_plans = aws.client.get_usage_plans(limit=limit).get('items')
        except botocore.exceptions.ClientError as e:
            if e.response.get('Error').get('Code') == "UnrecognizedClientException":
                return self._logger.error(f"Could not create region (some regions require manual enabling): {region}")
            raise ApiConnectionError(e)
        usage_plans = []
        for usg_pln in current_usage_plans:
            plan = Plan(
                identity = usg_pln.get('id'),
                name = usg_pln.get('name'),
                description = usg_pln.get('description'),
                api_stages = usg_pln.get('apiStages'),
            )
            usage_plans.append(plan)
        return usage_plans
        

    def _init_gateway(self, region: str, force: bool = False) -> dict:
        # Connect to AWS
        aws = AWS(region, self.access_key_id, self.access_key_secret, self._logger.get_level())

        # If API gateway already exists for host, return pre-existing endpoint
        current_endpoints = self._existing_connection(aws)
        if not force and current_endpoints is None:
            raise ApiConnectionError('No endpoints found')
        if not force and current_endpoints.success:
            return self._existing_connection(aws)

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
            restApiId=create_api_response.get('id')
        )
        rest_api_id = create_api_response.get('id')

        # Create "Resource" (wildcard proxy path)
        create_resource_response = aws.client.create_resource(
            restApiId=create_api_response.get('id'),
            parentId=get_resource_response.get('items')[0].get('id'),
            pathPart="{proxy+}"
        )

        # Allow all methods to new resource
        aws.client.put_method(
            restApiId=create_api_response.get('id'),
            resourceId=get_resource_response.get('items')[0].get('id'),
            httpMethod="ANY",
            authorizationType="NONE",
            requestParameters={
                "method.request.path.proxy": True,
                "method.request.header.X-My-X-Forwarded-For": True
            }
        )

        # Make new resource route traffic to new host
        aws.client.put_integration(
            restApiId=create_api_response.get('id'),
            resourceId=get_resource_response.get('items')[0].get('id'),
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
            restApiId=create_api_response.get('id'),
            resourceId=create_resource_response.get('id'),
            httpMethod="ANY",
            authorizationType="NONE",
            requestParameters={
                "method.request.path.proxy": True,
                "method.request.header.X-My-X-Forwarded-For": True
            }
        )

        aws.client.put_integration(
            restApiId=create_api_response.get('id'),
            resourceId=create_resource_response.get('id'),
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
        aws.client.create_usage_plan(
            name=self.usage_plan_name,
            description=rest_api_id,
            apiStages=[
                {
                    "apiId": rest_api_id,
                    "stage": "ProxyStage"
                }
            ]
        )

        # Return endpoint name and whether it show it is newly created
        return Connection(
            success = True,
            endpoint = f"{rest_api_id}.execute-api.{region}.amazonaws.com",
            new = False,
        )


    def _delete_gateway(self, region: str) -> int:
        # Connect to AWS
        aws = AWS(region, self.access_key_id, self.access_key_secret, self._logger.get_level())

        # Get all gateway apis (or skip if we don't have permission)
        endpoints = self._active_endpoints(aws)
        usage_plans = self._active_usage_plans(aws)
        deleted_endpoints = 0
        for ep in endpoints:
            # Check if hostname matches
            if self.api_name == ep.name:
                date_format = '%Y/%m/%d %H:%M:%S %z'
                self._logger.debug("Removing endpoint '{identity}' named as '{name}' created on '{date}'".format(identity=ep.identity, name=ep.name, date=ep.created_date.strftime(date_format)))
                
                # Attempt delete
                try:
                    success = aws.client.delete_rest_api(restApiId=ep.identity)
                    if success:
                        deleted_endpoints += 1
                        self._logger.debug(f"Removed API '{ep.identity}'")
                    else:
                        self._logger.error(f"Failed to delete API {ep.identity}.")
                except botocore.exceptions.ClientError as e:
                    # If timeout, retry
                    err_code = e.response.get('Error').get('Code')
                    if err_code == "TooManyRequestsException":
                        sleep(1)
                        continue
                    else:
                        self._logger.error(f"Failed to delete API {ep.identity}.")
       
        deleted_plans = 0
        for usg_pln in usage_plans:
            # Check if usage plan matches
            if self.usage_plan_name == usg_pln.name:
                date_format = '%Y/%m/%d %H:%M:%S %z'
                self._logger.debug("Removing plan '{identity}' named as '{name}'".format(identity=usg_pln.identity, name=usg_pln.name))

                # Attempt delete
                try:
                    success = aws.client.delete_usage_plan(usagePlanId=usg_pln.identity)
                    if success:
                        deleted_plans += 1
                        self._logger.debug(f"Removed Plan '{usg_pln.identity}'")
                    else:
                        self._logger.error(f"Failed to delete Plan {usg_pln.identity}.")
                except botocore.exceptions.ClientError as e:
                    # If timeout, retry
                    err_code = e.response.get('Error').get('Code')
                    err_msg = e.response.get('Error').get('Message')
                    if err_code == "TooManyRequestsException":
                        sleep(1)
                        continue
                    if err_code == "BadRequestException":
                        self._logger.error(err_msg)
                    else:
                        self._logger.error(f"Failed to delete Plan {usg_pln.identity}.")
        
        return deleted_endpoints, deleted_plans


    def _current_gateways(self, region: str) -> dict:
        # Connect to AWS
        aws = AWS(region, self.access_key_id, self.access_key_secret, self._logger.get_level())
        
        usage_plans = {}
        for usg_pln in self._active_usage_plans(aws):
            date_format = '%Y/%m/%d %H:%M:%S %z'
            self._logger.debug("plan '{idn}' named as '{name}' is active".format(idn=usg_pln.identity, name=usg_pln.name))
            usage_plans[usg_pln.identity] = {
                'name': usg_pln.name,
                'description': usg_pln.description,
            }

        endpoints = {}
        for ep in self._active_endpoints(aws):
            date_format = '%Y/%m/%d %H:%M:%S %z'
            self._logger.debug("Endpoint '{name}' located at '{url}' created on '{date}' is active".format(name=ep.name, url=ep.url, date=ep.created_date.strftime(date_format)))
            endpoints[ep.identity] = {
                'name': ep.name,
                'creation_date': ep.created_date,
                'url': ep.url,
            }
        return usage_plans, endpoints


    def _remove_all_gateways(self, region: str) -> dict:
        # Connect to AWS
        aws = AWS(region, self.access_key_id, self.access_key_secret, self._logger.get_level())
        
        endpoints = self._active_endpoints(aws)
        usage_plans = self._active_usage_plans(aws)
        deleted_endpoints = 0
        for ep in endpoints:
            date_format = '%Y/%m/%d %H:%M:%S %z'
            self._logger.debug("Removing endpoint '{identity}' created on '{date}'".format(identity=ep.identity, date=ep.created_date.strftime(date_format)))
            
            # Attempt delete
            try:
                success = aws.client.delete_rest_api(restApiId=ep.identity)
                if success:
                    deleted_endpoints += 1
                    self._logger.debug(f"Removed API({deleted_endpoints}/{len(endpoints)}) '{ep.identity}'")
                else:
                    self._logger.error(f"Failed to delete API {ep.identity}.")
            except botocore.exceptions.ClientError as e:
                # If timeout, retry
                err_code = e.response.get('Error').get('Code')
                if err_code == "TooManyRequestsException":
                    sleep(1)
                    continue
                else:
                    self._logger.error(f"Failed to delete API {ep.identity}.")

        deleted_plans = 0
        for usg_pln in usage_plans:
            date_format = '%Y/%m/%d %H:%M:%S %z'
            self._logger.debug("Removing plan '{identity}' named as '{name}'".format(identity=usg_pln.identity, name=usg_pln.name))
            
            # Attempt delete
            try:
                success = aws.client.delete_usage_plan(usagePlanId=usg_pln.identity)
                if success:
                    deleted_plans += 1
                    self._logger.debug(f"Removed Plan({deleted_plans}/{len(usage_plans)}) '{usg_pln.identity}'")
                else:
                    self._logger.error(f"Failed to delete Plan {usg_pln.identity}.")
            except botocore.exceptions.ClientError as e:
                # If timeout, retry
                err_code = e.response.get('Error').get('Code')
                if err_code == "TooManyRequestsException":
                    sleep(1)
                    continue
                else:
                    self._logger.error(f"Failed to delete Plan {usg_pln.identity}.")
        return deleted_endpoints, deleted_plans

    def send(self, request: rq.models.Response, stream: bool = False, timeout: int = None,
        verify: bool = True,
        cert: tuple = None,
        proxies: dict = None,
        ) -> rq.models.Response:
        # Get random endpoint
        try:
            endpoint = choice(self.endpoints)
        except AttributeError:
            raise ApiConnectionError('No API endpoints detected, has a gateway been started?')
        # Replace URL with our endpoint
        protocol, site = request.url.split("://", 1)
        site_path = site.split("/", 1)[1]
        request.url = "https://" + endpoint + "/ProxyStage/" + site_path
        # Replace host with endpoint host
        request.headers['Host'] = endpoint
        # Run original python requests send function
        return super().send(request, stream, timeout, verify, cert, proxies)

    def start(self, force=False, endpoints=[]) -> list:
        # If endpoints given already, assign and continue
        if len(endpoints) > 0:
            self.endpoints = endpoints
            return endpoints

        # Otherwise, start/locate new endpoints
        self._logger.info(
            f"Starting API gateway{'s' if len(self.regions) > 1 else ''} in {len(self.regions)} regions: {', '.join(self.regions)}"
        )
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
                if result.success:
                    self.endpoints.append(result.endpoint)
                    if result.new:
                        new_endpoints += 1

        self._logger.debug(f"Using {len(self.endpoints)} endpoints with name '{self.api_name}' ({new_endpoints} new).")
        return self.endpoints

    def shutdown(self):
        self._logger.info(f"Deleting API gateway{'s' if len(self.regions) > 1 else ''} for site '{self.site}'.")

        # Setup multithreading object
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            # Send each region deletion to its own thread
            for region in self.regions:
                futures.append(executor.submit(self._delete_gateway, region=region))
            # Check outputs
            deleted_endpoints = 0
            deleted_plans = 0
            for future in concurrent.futures.as_completed(futures):
                endpoints, plans = future.result()
                deleted_endpoints += endpoints
                deleted_plans += plans
                
        self._logger.debug(f"Deleted {deleted_endpoints} endpoints and {deleted_plans} plans for site '{self.site}'.")

    def status(self, force=False) -> dict:
        self._logger.info(f"Getting status of API gateway{'s' if len(self.regions) > 1 else ''} for site '{self.site}'.")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            # Send each region creation to its own thread
            for region in self.regions:
                futures.append(executor.submit(self._current_gateways, region=region))
            # Get thread outputs
            for future in concurrent.futures.as_completed(futures):
                plans, endpoints = future.result()
        self._logger.debug(f"total active plans: {len(plans)}")
        self._logger.debug(f"total active endpoints: {len(endpoints)}")
        return {
            'active_plans': plans,
            'active_endpoints': endpoints,
        }

    def cleanup(self, force=False) -> dict:
        self._logger.info(f"Removing all API gateway{'s' if len(self.regions) > 1 else ''} endpoints.")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            # Send each region creation to its own thread
            for region in self.regions:
                futures.append(executor.submit(self._remove_all_gateways, region=region))
            # Get thread outputs
            for future in concurrent.futures.as_completed(futures):
                endpoints, plans = future.result()
        return {
            'removed_endpoints': endpoints,
            'removed_plans': plans,
        }
        