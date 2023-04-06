import json
import pandas as pd
import datetime

from typing import List, Dict, Any, Literal
from prefect import Task
from prefect.tasks.secrets import PrefectSecret
from prefect.utilities import logging
from viadot.exceptions import ValidationError
from viadot.sources import Hubspot

logger = logging.get_logger()


class HubspotToDF(Task):
    def __init__(
        self,
        hubspot_credentials: dict,
        *args,
        **kwargs,
    ):

        self.credentials = hubspot_credentials
        super().__init__(
            name="hubspot_to_df",
            *args,
            **kwargs,
        )

    def __call__(self):
        """Download Hubspot data to a DF"""
        super().__call__(self)

    def to_df(self, result: list = None) -> pd.DataFrame:
        """
        Args:
            result (list, optional): API response in JSON format. Defaults to None.

        Returns:
            pd.DataFrame: DF from JSON
        """
        return pd.json_normalize(result)

    def date_to_unixtimestamp(self, date: str = None):
        """
        Function for date conversion from user defined "yyyy-mm-dd" to Unix Timestamp (SECONDS SINCE JAN 01 1970. (UTC)).
        For example: 1680774921 SECONDS SINCE JAN 01 1970. (UTC) -> 11:55:49 AM 2023-04-06.
        """
        clean_date = int(
            datetime.datetime.timestamp(datetime.datetime.strptime(date, "%Y-%m-%d"))
            * 1000
        )
        return clean_date

    def format_filters(self, filters: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Function for API body (filters) conversion from a user defined to API language. Converts date to Unix Timestamp.

        Args:
            filters (Dict[str, Any], optional): Filters in JSON format. Defaults to {}.

        Returns:
            Dict[str, Any]: Filters in JSON format after data cleaning
        """
        for item in filters:
            for iterator in range(len(item["filters"])):
                for subitem in item["filters"][iterator]:
                    lookup = item["filters"][iterator][subitem]
                    try:
                        datetime.date.fromisoformat(lookup)
                        date_to_format = item["filters"][iterator][subitem]
                        date_after_format = self.date_to_unixtimestamp(date_to_format)
                        filters[filters.index(item)]["filters"][iterator][
                            subitem
                        ] = date_after_format
                    except:
                        pass

        return filters

    def get_offset_from_response(self, api_response: Dict[str, Any] = {}) -> tuple:
        """
        Helper funtion for assigning offset type/value depends on keys in API response.

        Args:
            api_response (Dict[str, Any], optional): API response in JSON format. Defaults to {}.

        Returns:
            tuple: Tuple in order: (offset_type, offset_value)
        """
        if "paging" in api_response.keys():
            offset_type = "after"
            offset_value = api_response["paging"]["next"][f"{offset_type}"]
        elif "offset" in api_response.keys():
            offset_type = "offset"
            offset_value = api_response["offset"]
        else:
            offset_type = None
            offset_value = None

        return (offset_type, offset_value)

    def run(
        self,
        endpoint: str,
        properties: List[Any] = [],
        filters: Dict[str, Any] = {},
        nrows: int = None,
    ):

        hubspot = Hubspot(credentials=self.credentials)

        url = hubspot.get_api_url(
            endpoint=endpoint,
            properties=properties,
            filters=filters,
        )

        if filters:

            filters_formatted = self.format_filters(filters=filters)
            body = hubspot.get_api_body(filters=filters_formatted)
            self.method = "POST"
            partition = hubspot.to_json(url=url, body=body, method=self.method)
            full_dataset = partition["results"]

            while "paging" in partition.keys() and len(full_dataset) < nrows:
                body = json.loads(hubspot.get_api_body(filters=filters_formatted))
                body["after"] = partition["paging"]["next"]["after"]
                partition = hubspot.to_json(
                    url=url, body=json.dumps(body), method=self.method
                )
                full_dataset.extend(partition["results"])

        else:
            self.method = "GET"

            partition = hubspot.to_json(url=url, method=self.method)
            full_dataset = partition[list(partition.keys())[0]]

            offset_type = self.get_offset_from_response(partition)[0]
            offset_value = self.get_offset_from_response(partition)[1]

            while offset_value and len(full_dataset) < nrows:
                url = hubspot.get_api_url(
                    endpoint=endpoint,
                    properties=properties,
                    filters=filters,
                )
                url += f"{offset_type}={offset_value}"

                partition = hubspot.to_json(url=url, method=self.method)
                full_dataset.extend(partition[list(partition.keys())[0]])

                offset_type = self.get_offset_from_response(partition)[0]
                offset_value = self.get_offset_from_response(partition)[1]

        df = self.to_df(full_dataset)[:nrows]

        return df
