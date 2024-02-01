import requests
import config
from init import redis_client, logger
from urllib.parse import urlencode

cache_key = "gpt_access_key:"
ACCOUNT_CONFIG_USERNAME = config.ACCOUNT_CONFIG_USERNAME
ACCOUNT_CONFIG_PASSWORD = config.ACCOUNT_CONFIG_PASSWORD


def get_access_key(key):
    """
    获取 access_key
    :return access_key
    """

    if key != config.KEY_FOR_GPTS_INFO:
        return ""

    if not redis_client.exists(get_cache_name(key)):
        url = config.BASE_URL + "/auth/token"

        # option values: web, apple, platform, default: web
        payload = urlencode({
            "username": ACCOUNT_CONFIG_USERNAME,
            "password": ACCOUNT_CONFIG_PASSWORD,
            "option": "web"
        })
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        response = requests.request("POST", url, headers=headers, data=payload)
        print(response.text)
        if response.status_code == 200:
            accessToken = response.json()['accessToken']
            redis_client.set(get_cache_name(key), accessToken, exat=get_exat_unix(response.json()['expires']))
            return accessToken
        else:
            logger.error(f"accessToken获取失败: {response.json()['msg']}，程序结束")
    else:
        return redis_client.get(get_cache_name(key)).decode()


def get_access_key_default():
    return get_access_key(config.KEY_FOR_GPTS_INFO)


def get_exat_unix(date_str):
    from datetime import datetime
    import time
    return int(time.mktime(datetime.strptime(date_str[:-6], "%Y-%m-%dT%H:%M:%S").timetuple()))


def get_cache_name(key):
    return cache_key + key


if __name__ == '__main__':
    print(get_exat_unix("2024-04-30T13:34:40.547Z"))