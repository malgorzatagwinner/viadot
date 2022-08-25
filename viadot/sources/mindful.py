import os
from io import StringIO
from typing import Any, Dict, Literal

import prefect
import pandas as pd
from datetime import datetime, timedelta
from requests.models import Response

from viadot.config import local_config
from viadot.sources.base import Source
from viadot.utils import handle_api_response
from viadot.exceptions import CredentialError, APIError


class Mindful(Source):
    def __init__(
        self,
        *args,
        credentials_mindful: Dict[str, Any] = None,
        region: Literal["us1", "us2", "us3", "ca1", "eu1", "au1"] = "eu1",
        start_date: datetime = None,
        end_date: datetime = None,
        date_interval: int = 1,
        file_extension: Literal["parquet", "csv"] = "csv",
        **kwargs,
    ) -> None:
        """Mindful connector which allows listing and downloading into Data Frame or specified format output.

        Args:
            credentials_mindful (Dict[str, Any], optional): Credentials to connect with Mindful API. Defaults to None.
            region (Literal[us1, us2, us3, ca1, eu1, au1], optional): SD region from where to interact with the mindful API. Defaults to "eu1".
            start_date (datetime, optional): Start date of the request. Defaults to None.
            end_date (datetime, optional): End date of the resquest. Defaults to None.
            date_interval (int, optional): How many days are included in the request.
                If end_date is passed as an argument, date_interval will be invalidated. Defaults to 1.
            file_extension (Literal[parquet, csv;], optional): file extensions for storing responses. Defaults to "csv".
        Raises:
            CredentialError: If credentials are not provided in local_config or directly as a parameter.
        """
        self.logger = prefect.context.get("logger")

        self.credentials_mindful = credentials_mindful

        if credentials_mindful is not None:
            self.credentials_mindful = credentials_mindful
            self.logger.info("Mindful credentials provided by user")
        else:
            try:
                self.credentials_mindful = local_config["MINDFUL"]
                self.logger.info("Mindful credentials loaded from local config")
            except KeyError:
                self.credentials_mindful = None
                raise CredentialError("Credentials not found.")

        super().__init__(*args, credentials=self.credentials_mindful, **kwargs)

        if region != "us1":
            self.region = region + "."
        else:
            self.region = ""

        if not isinstance(start_date, datetime):
            self.start_date = datetime.now()
            self.end_date = self.start_date + timedelta(days=date_interval)
            self.logger.info(
                f"Mindful start_date variable is None or not in datetime format, it has been taken as: {self.start_date}."
            )
            self.logger.info(
                f"Mindful end_date variable has been also taken as: {self.end_date}."
            )
        elif isinstance(start_date, datetime) and not isinstance(end_date, datetime):
            self.start_date = start_date
            self.end_date = start_date + timedelta(days=date_interval)
            self.logger.info(
                f"Mindful end_date variable is None or not in datetime format, it has been taken as: {self.end_date}."
            )
        elif start_date >= end_date:
            raise ValueError(
                f"start_date variable must be grater than end_date variable."
            )
        else:
            self.start_date = start_date
            self.end_date = end_date

        self.file_extension = file_extension
        self.header = {
            "Authorization": f"Bearer {self.credentials_mindful.get('VAULT')}",
        }

    def _mindful_api_response(
        self,
        params: Dict[str, Any] = None,
        endpoint: str = "",
        **kwargs,
    ) -> Response:
        """Basic call to Mindful API given an endpoint

        Args:
            params (Dict[str, Any], optional): Parameters to be passed into the request. Defaults to None.
            endpoint (str, optional): API endpoint for an individual request. Defaults to "".

        Returns:
            Response: request object with the response from the Mindful API.
        """

        response = handle_api_response(
            url=f"https://{self.region}surveydynamix.com/api/{endpoint}",
            params=params,
            headers=self.header,
            method="GET",
        )

        return response

    def get_interactions_list(
        self,
        limit: int = 1000,
        **kwargs,
    ) -> Response:
        """Gets a list of survey interactions as a JSON array of interaction resources.

        Args:
            limit (int, optional): The number of matching interactions to return. Defaults to 1000.

        Returns:
            Response: request object with the response from the Mindful API.
        """

        self.endpoint = "interactions"
        params = {
            "_limit": limit,
            "start_date": f"{self.start_date}",
            "end_date": f"{self.end_date}",
        }

        response = self._mindful_api_response(
            endpoint=self.endpoint,
            params=params,
        )

        if response.status_code == 200:
            self.logger.info(
                "Succesfully downloaded interactions data from mindful API."
            )
        else:
            self.logger.error(
                f"Failed to downloaded interactions data. - {response.content}"
            )
            raise APIError("Failed to downloaded interactions data.")

        return response

    def get_responses_list(
        self,
        limit: int = 1000,
        **kwargs,
    ) -> Response:
        """Gets a list of survey responses associated with a survey, question, or interaction resource.

        Args:
            limit (int, optional): The number of matching interactions to return. Defaults to 1000.

        Returns:
            Response: request object with the response from the Mindful API.
        """

        self.endpoint = "responses"
        params = {
            "_limit": limit,
            "start_date": f"{self.start_date}",
            "end_date": f"{self.end_date}",
        }

        response = self._mindful_api_response(
            endpoint=self.endpoint,
            params=params,
        )

        if response.status_code == 200:
            self.logger.info("Succesfully downloaded responses data from mindful API.")
        else:
            self.logger.error(
                f"Failed to downloaded responses data. - {response.content}"
            )
            raise APIError("Failed to downloaded responses data.")

        return response

    def response_to_file(
        self, response: Response, file_name: str = None, file_path: str = ""
    ) -> None:
        """Save Mindful response data to file.

        Args:
            response (Response, optional): request object with the response from the Mindful API. Defaults to None.
            file_name (str, optional): Name of the file where saving data. Defaults to None.
            file_path (str, optional): Path where to save the file. Defaults to ''.
        """

        data_frame = pd.read_json(StringIO(response.content.decode("utf-8")))
        if not file_name:
            self._file_name = os.path.join(
                file_path, f"{self.endpoint}.{self.file_extension}"
            )
        else:
            self._file_name = os.path.join(
                file_path, f"{file_name}.{self.file_extension}"
            )

        if self.file_extension == "csv":
            data_frame.to_csv(self._file_name, index=False)
        elif self.file_extension == "parquet":
            data_frame.to_parquet(self._file_name, index=False)
        else:
            self.logger.warning(
                "File extension is not available, please choose file_extension: 'parquet' or 'csv' (def.) at Mindful instance."
            )
