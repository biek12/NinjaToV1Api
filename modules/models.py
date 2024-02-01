import uuid

import requests
import config
import init
from auth import get_access_key_default, get_access_key


def get_accessible_model_list():
    return [conf['name'] for conf in init.gpts_configurations]


def find_model_config(model_name):
    for conf in init.gpts_configurations:
        if conf['name'] == model_name:
            return conf
    return None


# 将配置添加到全局列表
def add_config_to_global_list(base_url, proxy_api_prefix, gpts_data, key_for_gpts_info):
    # print(f"gpts_data: {gpts_data}")
    for model_name, model_info in gpts_data.items():
        # print(f"model_name: {model_name}")
        # print(f"model_info: {model_info}")
        model_id = model_info['id']
        gizmo_info = fetch_gizmo_info(base_url, proxy_api_prefix, model_id, key_for_gpts_info)
        if gizmo_info:
            init.gpts_configurations.append({
                'name': model_name,
                'id': model_id,
                'config': gizmo_info
            })


# 根据 ID 发送请求并获取配置信息
def fetch_gizmo_info(base_url, proxy_api_prefix, model_id, key_for_gpts_info):
    url = f"{base_url}{proxy_api_prefix}/backend-api/gizmos/{model_id}"

    # TODO 将这里改认证
    ak = get_access_key(key_for_gpts_info)

    headers = {
        "Authorization": f"Bearer {ak}"
    }

    response = requests.get(url, headers=headers)
    # init.logger.debug(f"fetch_gizmo_info_response: {response.text}")
    if response.status_code == 200:
        return response.json()
    else:
        return None


def generate_gpts_payload(model, messages):
    model_config = find_model_config(model)
    if model_config:
        gizmo_info = model_config['config']
        gizmo_id = gizmo_info['gizmo']['id']

        payload = {
            "action": "next",
            "messages": messages,
            "parent_message_id": str(uuid.uuid4()),
            "model": "gpt-4-gizmo",
            "timezone_offset_min": -480,
            "history_and_training_disabled": False,
            "conversation_mode": {
                "gizmo": gizmo_info,
                "kind": "gizmo_interaction",
                "gizmo_id": gizmo_id
            },
            "force_paragen": False,
            "force_rate_limit": False
        }
        return payload
    else:
        return None