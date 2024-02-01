import config
import logging
from logging.handlers import TimedRotatingFileHandler
from fake_useragent import UserAgent
from modules.RedisClient import RedisClient

# 初始化一些操作
ua = UserAgent()


# 初始化Redis客户端
def init_redis(host='127.0.0.1', port=6379, password=None, db=0):
    redis_client = RedisClient(
        host=host,
        port=port,
        password=password,
        db=db
    ).client
    return redis_client


def init_logger(level, need_to_file):
    # 设置日志级别
    log_level_dict = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')

    logger = logging.getLogger()
    logger.setLevel(log_level_dict.get(level, logging.DEBUG))

    # 如果环境变量指示需要输出到文件
    if need_to_file:
        log_filename = './log/access.log'
        file_handler = TimedRotatingFileHandler(log_filename, when="midnight", interval=1, backupCount=30)
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)

    # 添加标准输出流处理器（控制台输出）
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)

    return logger
