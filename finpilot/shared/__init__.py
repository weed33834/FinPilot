"""共享模块.

放置跨服务共享的 schemas、events、constants，定义服务边界契约。
单体架构下预留的共享契约入口，为将来微服务化做准备。
"""

from . import constants, events, schemas

__all__ = ["constants", "events", "schemas"]
