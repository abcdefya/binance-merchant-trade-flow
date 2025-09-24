import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from binance_sdk_c2c.rest_api.models import GetC2CTradeHistoryResponse, GetC2CTradeHistoryResponseDataInner
from binance_sdk_c2c.c2c import C2C, ConfigurationRestAPI, C2C_REST_API_PROD_URL
from src.utils.utils import *

# Configure logging
logging.basicConfig(level=logging.INFO)


class C2CExtended(C2C):
    """Extended C2C API with specific time-based trade history retrieval methods for Vietnam timezone (UTC+7)."""

    def __init__(self, config_rest_api: ConfigurationRestAPI = None) -> None:
        super().__init__(config_rest_api)
        self.max_records = 50  # Maximum records per request as per observed API limit
        self.tz_vietnam = timezone(timedelta(hours=7))  # UTC+7 For Vietnam timezone

    def _fetch_data(
        self,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[GetC2CTradeHistoryResponseDataInner]:
        """
        Fetch all trade history records with pagination.
        
        Args:
            start_time (Optional[int]): Start timestamp in milliseconds
            end_time (Optional[int]): End timestamp in milliseconds
            
        Returns:
            List[GetC2CTradeHistoryResponseDataInner]: List of all trade records
        """
        fetch_data = []
        page = 1 

        while True:
            response = self.rest_api.get_c2_c_trade_history(
                start_time=start_time,
                end_time=end_time,
                page=page,
                recv_window=60000
            )

            rate_limits = response.rate_limits
            logging.info(f"Page {page} rate limits: {rate_limits}")

            # Extract the inner data list from the response
            response_data = response.data()
            if response_data.code != '000000' or not response_data.data:
                logging.info(f"Stopping at page {page}: No more data or error (code: {response_data.code})")
                break

            data = response_data.data
            # Verify that trades are within the requested time range
            filtered_data = [
                trade for trade in data
                if start_time <= trade.create_time <= end_time
            ]
            fetch_data.extend(filtered_data)
            logging.info(f"Page {page} retrieved {len(data)} records, {len(filtered_data)} within time range")

            # If fewer than max_records, we've reached the end
            if len(data) < self.max_records:
                break

            page += 1
        
        return fetch_data

    def get_latest(self) -> List[GetC2CTradeHistoryResponseDataInner]:
        """
        Get trade history from 00:00 of current day to now in Vietnam timezone (UTC+7).
        Includes both BUY and SELL trades.
        
        Returns:
            List[GetC2CTradeHistoryResponseDataInner]: List of trade records
        """
        now = datetime.now(self.tz_vietnam)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999000)

        start_time = get_timestamp(start_of_today)
        end_time = get_timestamp(end_of_today)

        return self._fetch_data(start_time, end_time)

    def get_latest_by_week(self) -> List[GetC2CTradeHistoryResponseDataInner]:
        """
        Get trade history from start of current week (Monday) to now in Vietnam timezone (UTC+7).
        Includes both BUY and SELL trades.
        
        Returns:
            List[GetC2CTradeHistoryResponseDataInner]: List of trade records
        """

        now = datetime.now(self.tz_vietnam)

        # Calculate days since Monday (0 = Mon, 1 = Tues,...)
        days_since_monday = now.weekday()
        start_of_week = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)

        start_time = get_timestamp(start_of_week)
        end_time = get_timestamp(now)

        return self._fetch_data(start_time, end_time)
    
    def get_prev_week_data(self) -> List[GetC2CTradeHistoryResponseDataInner]:
        """
        Get trade history for the entire previous week (Monday to Sunday) in Vietnam timezone (UTC+7).
        Includes both BUY and SELL trades.
        
        Returns:
            List[GetC2CTradeHistoryResponseDataInner]: List of trade records
        """
        now = datetime.now(self.tz_vietnam)
        days_since_monday = now.weekday()
        start_of_current_week = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_prev_week = start_of_current_week - timedelta(days=7)
        end_of_prev_week = start_of_prev_week + timedelta(days=7) - timedelta(milliseconds=1)

        start_time = get_timestamp(start_of_prev_week)
        end_time = get_timestamp(end_of_prev_week)

        return self._fetch_data(start_time, end_time)


    def get_prev_month(self) -> List[GetC2CTradeHistoryResponseDataInner]:
        """
        Get trade history for the entire previous month in Vietnam timezone (UTC+7).
        Includes both BUY and SELL trades.
        
        Returns:
            List[GetC2CTradeHistoryResponseDataInner]: List of trade records
        """

        now = datetime.now(self.tz_vietnam)

        # Get first day of current month
        start_of_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get first day of previous month
        start_of_prev_month = (start_of_current_month - timedelta(days=1)).replace(day=1)

        # Get last day of previous month
        if start_of_prev_month.month == 12:
            end_of_prev_month = start_of_prev_month.replace(year=start_of_prev_month.year + 1,
            month=1,
            day=1)
        else:
            end_of_prev_month = start_of_prev_month.replace(month=start_of_prev_month.month + 1,
            day=1)
        
        end_of_prev_month -= timedelta(milliseconds=1)

        start_time = get_timestamp(start_of_prev_month)
        end_time = get_timestamp(end_of_prev_month)

        return self._fetch_data(start_time, end_time)

        
    def get_yesterday(self) -> List[GetC2CTradeHistoryResponseDataInner]:
        """
        Get trade history for the yesterday since today in Vietnam timezone (UTC+7).
        Includes both BUY and SELL trades.
        
        Returns:
            List[GetC2CTradeHistoryResponseDataInner]: List of trade records
        """

        now = datetime.now(self.tz_vietnam)
        
        # Start of yesterday
        start_of_yesterday = (now - timedelta(days=1)).replace(hour=0, 
                                                            minute=0,
                                                            second=0,
                                                            microsecond=0)
        
        # End of yesterday
        end_of_yesterday = start_of_yesterday.replace(hour=23,
                                                    minute=59,
                                                    second=59,
                                                    microsecond=999000)

        start_time = get_timestamp(start_of_yesterday)
        end_time = get_timestamp(end_of_yesterday)

        return self._fetch_data(start_time, end_time)