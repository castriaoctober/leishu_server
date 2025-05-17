from django.conf import settings
import pymysql
import logging

if settings.LOGGER == "default":
    logger = logging.getLogger(__name__)
else:
    logger = logging.getLogger(settings.LOGGER)

DB_CONFIG = settings.DB_CONFIG

def connect_db(config=DB_CONFIG, **kwargs):
    """连接MySQL数据库"""
    config = config.copy()
    config.update(kwargs)
    try:
        return pymysql.connect(**config)
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        raise