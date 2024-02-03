import config
from modules import init_logger, init_redis

from flask import Flask
from flask_cors import CORS

logger = init_logger(
    level=config.LOG_LEVEL,
    need_to_file=config.NEED_LOG_TO_FILE
)

redis_client = init_redis(
    host=config.REDIS_CONFIG_HOST,
    port=config.REDIS_CONFIG_PORT,
    password=config.REDIS_CONFIG_PASSWORD,
    db=config.REDIS_CONFIG_DB
)

# 创建 Flask 应用
app = Flask(__name__)
CORS(app, resources={r"/images/*": {"origins": "*"}})

gpts_configurations = []