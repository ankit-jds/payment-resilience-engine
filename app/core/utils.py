from datetime import datetime
from zoneinfo import ZoneInfo

def get_ist_now() -> datetime:
    """Returns the current timestamp localized to Indian Standard Time (IST)."""
    # ZoneInfo is highly preferred because it is built straight into modern Python
    # avoiding extra heavy dependency requirements like pytz
    return datetime.now(ZoneInfo('Asia/Kolkata'))
