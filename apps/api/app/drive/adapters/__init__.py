"""按种类找出网盘适配器。"""

from app.drive.adapters.baidu import BaiduAdapter
from app.drive.kinds import kind_ready


def get_adapter(kind: str):
    if kind == "baidu":
        return BaiduAdapter()
    if not kind_ready(kind):
        raise ValueError("这种网盘以后再接")
    raise ValueError("不支持这种网盘")
