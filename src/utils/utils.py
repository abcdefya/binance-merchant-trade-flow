import csv
import logging
from typing import List
from binance_sdk_c2c.rest_api.models import GetC2CTradeHistoryResponseDataInner
from datetime import datetime, timedelta, timezone, tzinfo

# Configure logging
logging.basicConfig(level=logging.INFO)

def get_timestamp(date: datetime = None) -> int:
    """
    Get timestamp in miliseconds for a given datatime or current time in UTC+7

    Args:
        date (datetime, optional): The dateime to convert to timestamp.
                                    If None, uses current time in UTC+7
    
    Returns:
        int: Timesptampt in miliseconds sice Unix epoch (00:00:00 UTC, 01/01/1970).

    """
    tz_vietnam = timezone(timedelta(hours=7)) # UTC+7 for Vietnam timezone

    # Use provided date or current time in UTC+7
    dt = date if date is not None else datetime.now(tz_vietnam)

    # Ensure the datetime is timezone-aware with UTC+7
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz_vietnam)
    
    # Return timestamp (seconds)
    return int(dt.timestamp() * 1000)


def write_to_csv(data: List[GetC2CTradeHistoryResponseDataInner], date_str: str) -> str:
    """
    Write trade history data to a CSV file with an auto-generated name based on the provided date string.

    Args:
        data (List[GetC2CTradeHistoryResponseDataInner]): List of trade records to write.
        date_str (str): Date string (e.g., '2025-09-23') to include in the CSV filename.

    Returns:
        str: Path to the generated CSV file.
    """
    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Format date string to ensure no invalid characters (e.g., replace '-' with '')
    cleaned_date_str = date_str.replace('-', '').replace('/', '').replace(' ', '')
    output_file = f"c2c_trade_history_{cleaned_date_str}.csv"

    # Define headers for CSV
    headers = [
        'order_number', 'adv_no', 'trade_type', 'asset', 'fiat',
        'fiat_symbol', 'amount', 'total_price', 'unit_price',
        'order_status', 'create_time', 'commission',
        'counter_part_nick_name', 'advertisement_role'
    ]

    try:
        if data:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()

                for item in data:
                    writer.writerow({
                        'order_number': item.order_number,
                        'adv_no': item.adv_no,
                        'trade_type': item.trade_type,
                        'asset': item.asset,
                        'fiat': item.fiat,
                        'fiat_symbol': item.fiat_symbol,
                        'amount': item.amount,
                        'total_price': item.total_price,
                        'unit_price': item.unit_price,
                        'order_status': item.order_status,
                        'create_time': item.create_time,  # Keep as timestamp
                        'commission': item.commission,
                        'counter_part_nick_name': item.counter_part_nick_name,
                        'advertisement_role': item.advertisement_role
                    })

            logging.info(f"Trade history written to {output_file} with {len(data)} records")
            return output_file
        else:
            logging.warning(f"No data to write to CSV for date {date_str}")
            return output_file

    except Exception as e:
        logging.error(f"Error writing to CSV for date {date_str}: {str(e)}")
        return output_file