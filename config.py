from modules.utils import load_config


"""
全局基础配置
"""

CONFIG = load_config('./data/config.json')

LOG_LEVEL = CONFIG.get('log_level', 'DEBUG').upper()
NEED_LOG_TO_FILE = CONFIG.get('need_log_to_file', 'true').lower() == 'true'

# 使用 get 方法获取配置项，同时提供默认值
BASE_URL = CONFIG.get('upstream_base_url', '')
PROXY_API_PREFIX = CONFIG.get('upstream_api_prefix', '')
if PROXY_API_PREFIX != '':
    PROXY_API_PREFIX = "/" + PROXY_API_PREFIX
UPLOAD_BASE_URL = CONFIG.get('backend_container_url', '')
KEY_FOR_GPTS_INFO = CONFIG.get('key_for_gpts_info', '')
API_PREFIX = CONFIG.get('backend_container_api_prefix', '')
GPT_4_S_New_Names = CONFIG.get('gpt_4_s_new_name', 'gpt-4-s').split(',')
GPT_4_MOBILE_NEW_NAMES = CONFIG.get('gpt_4_mobile_new_name', 'gpt-4-mobile').split(',')
GPT_3_5_NEW_NAMES = CONFIG.get('gpt_3_5_new_name', 'gpt-3.5-turbo').split(',')

BOT_MODE = CONFIG.get('bot_mode', {})
BOT_MODE_ENABLED = BOT_MODE.get('enabled', 'false').lower() == 'true'
BOT_MODE_ENABLED_MARKDOWN_IMAGE_OUTPUT = BOT_MODE.get('enabled_markdown_image_output', 'false').lower() == 'true'
BOT_MODE_ENABLED_BING_REFERENCE_OUTPUT = BOT_MODE.get('enabled_bing_reference_output', 'false').lower() == 'true'
BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT = BOT_MODE.get('enabled_plugin_output', 'false').lower() == 'true'

BOT_MODE_ENABLED_PLAIN_IMAGE_URL_OUTPUT = BOT_MODE.get('enabled_plain_image_url_output', 'false').lower() == 'true'

NEED_DELETE_CONVERSATION_AFTER_RESPONSE = CONFIG.get('need_delete_conversation_after_response', 'true').lower() == 'true'

USE_OAIUSERCONTENT_URL = CONFIG.get('use_oaiusercontent_url', 'false').lower() == 'true'

# USE_PANDORA_FILE_SERVER = CONFIG.get('use_pandora_file_server', 'false').lower() == 'true'

CUSTOM_ARKOSE = CONFIG.get('custom_arkose_url', 'false').lower() == 'true'

ARKOSE_URLS = CONFIG.get('arkose_urls', "")

DALLE_PROMPT_PREFIX = CONFIG.get('dalle_prompt_prefix', '')

# redis配置读取
REDIS_CONFIG = CONFIG.get('redis', {})
REDIS_CONFIG_HOST = REDIS_CONFIG.get('host', 'redis')
REDIS_CONFIG_PORT = REDIS_CONFIG.get('port', 6379)
REDIS_CONFIG_PASSWORD = REDIS_CONFIG.get('password', '')
REDIS_CONFIG_DB = REDIS_CONFIG.get('db', 0)
REDIS_CONFIG_POOL_SIZE = REDIS_CONFIG.get('pool_size', 10)
REDIS_CONFIG_POOL_TIMEOUT = REDIS_CONFIG.get('pool_timeout', 30)

# 账号配置
ACCOUNT_CONFIG = CONFIG.get('account', {})
ACCOUNT_CONFIG_USERNAME = ACCOUNT_CONFIG.get('username', '')
ACCOUNT_CONFIG_PASSWORD = ACCOUNT_CONFIG.get('password', '')

# proxy配置（主要是代理wss）
PROXY_CONFIG = CONFIG.get('proxy', {})
PROXY_CONFIG_ENABLED = PROXY_CONFIG.get('enabled', 'false') == 'true'
PROXY_CONFIG_HOST = PROXY_CONFIG.get('host', '')
PROXY_CONFIG_PORT = PROXY_CONFIG.get('port', 7890)
PROXY_CONFIG_PROTOCOL = PROXY_CONFIG.get('protocol', '')
PROXY_CONFIG_USERNAME = PROXY_CONFIG.get('username', '')
PROXY_CONFIG_PASSWORD = PROXY_CONFIG.get('password', '')
PROXY_CONFIG_AUTH = [
    PROXY_CONFIG_USERNAME,
    PROXY_CONFIG_PASSWORD
]


"""
GPTs配置
"""

GPTs_DATA = load_config("./data/gpts.json")
