# 创建FakeUserAgent对象
import base64
import json
import os
import re
import threading
import time
from queue import Queue

import requests
import websocket
from flask import request, jsonify, Response, send_from_directory
from flask_cors import cross_origin

import config
import gpt
import init
from auth import get_access_key, get_access_key_default
from gpt import send_text_prompt_and_get_response, data_fetcher, keep_alive, count_tokens, count_total_input_words, \
    save_image, replace_complete_citation, register_websocket
from init import app, logger
from modules import models
from modules.models import get_accessible_model_list, find_model_config
from modules.utils import generate_unique_id, is_valid_citation_format, is_complete_citation_format

VERSION = '0.7.0'
# VERSION = 'test'
UPDATE_INFO = '适配WSS输出'
# UPDATE_INFO = '【仅供临时测试使用】 '

with app.app_context():
    global gpts_configurations  # 移到作用域的最开始

    # 输出版本信息
    logger.info("==========================================")
    logger.info(f"Version: {VERSION}")
    logger.info(f"Update Info: {UPDATE_INFO}")

    logger.info(f"LOG_LEVEL: {config.LOG_LEVEL}")
    logger.info(f"NEED_LOG_TO_FILE: {config.NEED_LOG_TO_FILE}")

    logger.info(f"BOT_MODE_ENABLED: {config.BOT_MODE_ENABLED}")

    if config.BOT_MODE_ENABLED:
        logger.info(f"enabled_markdown_image_output: {config.BOT_MODE_ENABLED_MARKDOWN_IMAGE_OUTPUT}")
        logger.info(f"enabled_plain_image_url_output: {config.BOT_MODE_ENABLED_PLAIN_IMAGE_URL_OUTPUT}")
        logger.info(f"enabled_bing_reference_output: {config.BOT_MODE_ENABLED_BING_REFERENCE_OUTPUT}")
        logger.info(f"enabled_plugin_output: {config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT}")

    if not config.BASE_URL:
        raise Exception('upstream_base_url is not set')
    else:
        logger.info(f"upstream_base_url: {config.BASE_URL}")
    if not config.PROXY_API_PREFIX:
        logger.warning('upstream_api_prefix is not set')
    else:
        logger.info(f"upstream_api_prefix: {config.PROXY_API_PREFIX}")

    if config.USE_OAIUSERCONTENT_URL == False:
        # 检测./images和./files文件夹是否存在，不存在则创建
        if not os.path.exists('./images'):
            os.makedirs('./images')
        if not os.path.exists('./files'):
            os.makedirs('./files')

    if not config.UPLOAD_BASE_URL:
        if config.USE_OAIUSERCONTENT_URL:
            logger.info("backend_container_url 未设置，将使用 oaiusercontent.com 作为图片域名")
        else:
            logger.warning("backend_container_url 未设置，图片生成功能将无法正常使用")


    else:
        logger.info(f"backend_container_url: {config.UPLOAD_BASE_URL}")

    if not config.KEY_FOR_GPTS_INFO:
        logger.warning("key_for_gpts_info 未设置，请将 gpts.json 中仅保留 “{}” 作为内容")
    else:
        logger.info(f"key_for_gpts_info: {config.KEY_FOR_GPTS_INFO}")

    if not config.API_PREFIX:
        logger.warning("backend_container_api_prefix 未设置，安全性会有所下降")
        logger.info(f'Chat 接口 URI: /v1/chat/completions')
        logger.info(f'绘图接口 URI: /v1/images/generations')
    else:
        logger.info(f"backend_container_api_prefix: {config.API_PREFIX}")
        logger.info(f'Chat 接口 URI: /{config.API_PREFIX}/v1/chat/completions')
        logger.info(f'绘图接口 URI: /{config.API_PREFIX}/v1/images/generations')

    logger.info(f"need_delete_conversation_after_response: {config.NEED_DELETE_CONVERSATION_AFTER_RESPONSE}")

    logger.info(f"use_oaiusercontent_url: {config.USE_OAIUSERCONTENT_URL}")

    logger.info(f"use_pandora_file_server: False")

    logger.info(f"custom_arkose_url: {config.CUSTOM_ARKOSE}")

    if config.CUSTOM_ARKOSE:
        logger.info(f"arkose_urls: {config.ARKOSE_URLS}")

    logger.info(f"DALLE_prompt_prefix: {config.DALLE_PROMPT_PREFIX}")

    logger.info(f"==========================================")

    if config.PROXY_CONFIG_ENABLED:
        logger.info("proxy is enabled")

        # 打印当前使用的代理设置
        logger.info(f"Use Proxy: {config.PROXY_CONFIG_PROTOCOL}://{config.PROXY_CONFIG_HOST}:{config.PROXY_CONFIG_PORT}")
    else:
        logger.info("No Proxy")


    ip_info = gpt.parse_oai_ip_info()
    logger.info(f"The ip you are using to access oai is: {ip_info['ip']}")
    logger.info(f"The location of this ip is: {ip_info['loc']}")
    logger.info(f"The colo is: {ip_info['colo']}")
    logger.info(f"Is this ip a Warp ip: {ip_info['warp']}")

    # 处理 websocket 连接
    # data_queue = Queue()
    # stop_event = threading.Event()
    # last_data_time = [time.time()]

    # api_key = get_access_key_default()
    # wss_url = register_websocket(api_key)
    # gpt.process_wss(wss_url=wss_url, data_queue=data_queue, stop_event=stop_event, last_data_time=last_data_time)

    logger.info(f"==========================================")

    # 更新 gpts_configurations 列表，支持多个映射
    for name in config.GPT_4_S_New_Names:
        init.gpts_configurations.append({
            "name": name.strip(),
            "ori_name": "gpt-4-s"
        })
    for name in config.GPT_4_MOBILE_NEW_NAMES:
        init.gpts_configurations.append({
            "name": name.strip(),
            "ori_name": "gpt-4-mobile"
        })
    for name in config.GPT_3_5_NEW_NAMES:
        init.gpts_configurations.append({
            "name": name.strip(),
            "ori_name": "gpt-3.5-turbo"
        })

    logger.info(f"GPTS 配置信息")


    # 加载配置并添加到全局列表
    models.add_config_to_global_list(config.BASE_URL, config.PROXY_API_PREFIX, config.GPTs_DATA, config.KEY_FOR_GPTS_INFO)
    # print("当前可用GPTS：" + get_accessible_model_list())
    # 输出当前可用 GPTS name
    # 获取当前可用的 GPTS 模型列表
    accessible_model_list = models.get_accessible_model_list()
    logger.info(f"当前可用 GPTS 列表: {accessible_model_list}")

    # 检查列表中是否有重复的模型名称
    if len(accessible_model_list) != len(set(accessible_model_list)):
        raise Exception("检测到重复的模型名称，请检查环境变量或配置文件。")

    logger.info(f"==========================================")

    # print(f"GPTs Payload 生成测试")

    # print(f"gpt-4-classic: {generate_gpts_payload('gpt-4-classic', [])}")


# 定义 Flask 路由
@app.route(f'/{config.API_PREFIX}/v1/chat/completions' if config.API_PREFIX else '/v1/chat/completions', methods=['POST'])
def chat_completions():
    logger.info(f"New Request")
    data = request.json
    messages = data.get('messages')
    model = data.get('model')
    accessible_model_list = get_accessible_model_list()
    if model not in accessible_model_list:
        return jsonify({"error": "model is not accessible"}), 401

    stream = data.get('stream', False)

    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Authorization header is missing or invalid"}), 401
    api_key = auth_header.split(' ')[1]
    logger.info(f"api_key: {api_key}")
    # 将api_key转换为access_key
    api_key = get_access_key(key=api_key)
    if not api_key:
        logger.info(f"api_key: {api_key} -> 无法获取到access key")
        return jsonify({"error": "Authorization header is missing or invalid"}), 401

    # upstream_response = send_text_prompt_and_get_response(messages, api_key, stream, model)

    # 在非流式响应的情况下，我们需要一个变量来累积所有的 new_text
    all_new_text = ""

    # 处理流式响应
    def generate():
        nonlocal all_new_text  # 引用外部变量
        data_queue = Queue()
        stop_event = threading.Event()
        last_data_time = [time.time()]
        chat_message_id = generate_unique_id("chatcmpl")

        conversation_id_print_tag = False

        conversation_id = ''

        # 启动数据处理线程
        fetcher_thread = threading.Thread(target=data_fetcher, args=(
        data_queue, stop_event, last_data_time, api_key, chat_message_id, model, "url", messages))
        fetcher_thread.start()

        # 启动保活线程
        keep_alive_thread = threading.Thread(target=keep_alive,
                                             args=(last_data_time, stop_event, data_queue, model, chat_message_id))
        keep_alive_thread.start()

        try:
            while True:
                data = data_queue.get()
                if isinstance(data, tuple) and data[0] == 'all_new_text':
                    # 更新 all_new_text
                    logger.info(f"完整消息: {data[1]}")
                    all_new_text += data[1]
                elif isinstance(data, tuple) and data[0] == 'conversation_id':
                    if conversation_id_print_tag == False:
                        logger.info(f"当前会话id: {data[1]}")
                        conversation_id_print_tag = True
                    # 更新 conversation_id
                    conversation_id = data[1]
                    # print(f"收到会话id: {conversation_id}")
                elif data == 'data: [DONE]\n\n':
                    # 接收到结束信号，退出循环
                    timestamp = int(time.time())

                    new_data = {
                        "id": chat_message_id,
                        "object": "chat.completion.chunk",
                        "created": timestamp,
                        "model": model,
                        "choices": [
                            {
                                "delta": {},
                                "index": 0,
                                "finish_reason": "stop"
                            }
                        ]
                    }
                    q_data = 'data: ' + json.dumps(new_data, ensure_ascii=False) + '\n\n'
                    yield q_data

                    logger.debug(f"会话结束-外层")
                    yield data
                    break
                else:
                    yield data

        finally:
            stop_event.set()
            fetcher_thread.join()
            keep_alive_thread.join()

            # if conversation_id:
            #     # print(f"准备删除的会话id： {conversation_id}")
            #     delete_conversation(conversation_id, api_key)

    if not stream:
        # 执行流式响应的生成函数来累积 all_new_text
        # 迭代生成器对象以执行其内部逻辑
        for _ in generate():
            pass
        # 构造响应的 JSON 结构
        ori_model_name = ''
        model_config = find_model_config(model)
        if model_config:
            ori_model_name = model_config.get('ori_name', model)
        input_tokens = count_total_input_words(messages, ori_model_name)
        comp_tokens = count_tokens(all_new_text, ori_model_name)
        response_json = {
            "id": generate_unique_id("chatcmpl"),
            "object": "chat.completion",
            "created": int(time.time()),  # 使用当前时间戳
            "model": model,  # 使用请求中指定的模型
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": all_new_text  # 使用累积的文本
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                # 这里的 token 计数需要根据实际情况计算
                "prompt_tokens": input_tokens,
                "completion_tokens": comp_tokens,
                "total_tokens": input_tokens + comp_tokens
            },
            "system_fingerprint": None
        }

        # 返回 JSON 响应
        return jsonify(response_json)
    else:
        return Response(generate(), mimetype='text/event-stream')


@app.route(f'/{config.API_PREFIX}/v1/images/generations' if config.API_PREFIX else '/v1/images/generations', methods=['POST'])
def images_generations():
    logger.info(f"New Img Request")
    data = request.json
    logger.debug(f"data: {data}")
    # messages = data.get('messages')
    model = data.get('model')
    accessible_model_list = get_accessible_model_list()
    if model not in accessible_model_list:
        return jsonify({"error": "model is not accessible"}), 401

    prompt = data.get('prompt', '')

    prompt = config.DALLE_PROMPT_PREFIX + prompt

    # 获取请求中的response_format参数，默认为"url"
    response_format = data.get('response_format', 'url')

    # stream = data.get('stream', False)

    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Authorization header is missing or invalid"}), 401
    api_key = auth_header.split(' ')[1]
    logger.info(f"api_key: {api_key}")
    # 将api_key转换为access_key
    api_key = get_access_key(key=api_key)
    if not api_key:
        logger.info(f"api_key: {api_key} -> 无法获取到access key")
        return jsonify({"error": "Authorization header is missing or invalid"}), 401

    image_urls = []

    messages = [
        {
            "role": "user",
            "content": prompt,
            "hasName": False
        }
    ]

    # upstream_response = send_text_prompt_and_get_response(messages, api_key, False, model)

    # 在非流式响应的情况下，我们需要一个变量来累积所有的 new_text
    all_new_text = ""

    # 处理流式响应
    def generate():
        nonlocal all_new_text  # 引用外部变量
        data_queue = Queue()
        stop_event = threading.Event()
        last_data_time = [time.time()]
        chat_message_id = generate_unique_id("chatcmpl")

        conversation_id_print_tag = False

        conversation_id = ''

        # 启动数据处理线程
        fetcher_thread = threading.Thread(target=data_fetcher, args=(
        data_queue, stop_event, last_data_time, api_key, chat_message_id, model, response_format, messages))
        fetcher_thread.start()

        # 启动保活线程
        keep_alive_thread = threading.Thread(target=keep_alive,
                                             args=(last_data_time, stop_event, data_queue, model, chat_message_id))
        keep_alive_thread.start()

        try:
            while True:
                data = data_queue.get()
                if isinstance(data, tuple) and data[0] == 'all_new_text':
                    # 更新 all_new_text
                    logger.info(f"完整消息: {data[1]}")
                    all_new_text += data[1]
                elif isinstance(data, tuple) and data[0] == 'conversation_id':
                    if conversation_id_print_tag == False:
                        logger.info(f"当前会话id: {data[1]}")
                        conversation_id_print_tag = True
                    # 更新 conversation_id
                    conversation_id = data[1]
                    # print(f"收到会话id: {conversation_id}")
                elif isinstance(data, tuple) and data[0] == 'image_url':
                    # 更新 image_url
                    image_urls.append(data[1])
                    logger.debug(f"收到图片链接: {data[1]}")
                elif data == 'data: [DONE]\n\n':
                    # 接收到结束信号，退出循环
                    logger.debug(f"会话结束-外层")
                    yield data
                    break
                else:
                    yield data

        finally:
            logger.critical(f"准备结束会话")
            stop_event.set()
            fetcher_thread.join()
            keep_alive_thread.join()

            # if conversation_id:
            #     # print(f"准备删除的会话id： {conversation_id}")
            #     delete_conversation(conversation_id, cookie, x_authorization)

    # 执行流式响应的生成函数来累积 all_new_text
    # 迭代生成器对象以执行其内部逻辑
    for _ in generate():
        pass
    # 构造响应的 JSON 结构
    response_json = {}
    # 检查 image_urls 是否为空
    if not image_urls:
        response_json = {
            "error": {
                "message": all_new_text,  # 使用累积的文本作为错误信息
                "type": "invalid_request_error",
                "param": "",
                "code": "image_generate_fail"
            }
        }
    else:
        if response_format == "url":
            response_json = {
                "created": int(time.time()),  # 使用当前时间戳
                # "reply": all_new_text,  # 使用累积的文本
                "data": [
                    {
                        "revised_prompt": all_new_text,  # 将描述文本加入每个字典
                        "url": url
                    } for url in image_urls
                ]  # 将图片链接列表转换为所需格式
            }
        else:
            response_json = {
                "created": int(time.time()),  # 使用当前时间戳
                # "reply": all_new_text,  # 使用累积的文本
                "data": [
                    {
                        "revised_prompt": all_new_text,  # 将描述文本加入每个字典
                        "b64_json": base64
                    } for base64 in image_urls
                ]  # 将图片链接列表转换为所需格式
            }
    # logger.critical(f"response_json: {response_json}")

    # 返回 JSON 响应
    return jsonify(response_json)


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Requested-With')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


# 特殊的 OPTIONS 请求处理器
@app.route(f'/{config.API_PREFIX}/v1/chat/completions' if config.API_PREFIX else '/v1/chat/completions', methods=['OPTIONS'])
def options_handler():
    logger.info(f"Options Request")
    return Response(status=200)


@app.route('/', defaults={'path': ''}, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
@app.route('/<path:path>', methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
def catch_all(path):
    logger.debug(f"未知请求: {path}")
    logger.debug(f"请求方法: {request.method}")
    logger.debug(f"请求头: {request.headers}")
    logger.debug(f"请求体: {request.data}")

    return jsonify({"message": "Welcome to Inker's World"}), 200


@app.route('/images/<filename>')
@cross_origin()  # 使用装饰器来允许跨域请求
def get_image(filename):
    # 检查文件是否存在
    if not os.path.isfile(os.path.join('images', filename)):
        return "文件不存在哦！", 404
    return send_from_directory('images', filename)


@app.route('/files/<filename>')
@cross_origin()  # 使用装饰器来允许跨域请求
def get_file(filename):
    # 检查文件是否存在
    if not os.path.isfile(os.path.join('files', filename)):
        return "文件不存在哦！", 404
    return send_from_directory('files', filename)


# 运行 Flask 应用
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=33333)
