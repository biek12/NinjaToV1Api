# 创建FakeUserAgent对象
import base64
import json
import os
import re
import threading
import time
from queue import Queue

import requests
from flask import request, jsonify, Response, send_from_directory
from flask_cors import cross_origin

import config
import init
from auth import get_access_key
from gpt import send_text_prompt_and_get_response, data_fetcher, keep_alive, count_tokens, count_total_input_words, \
    save_image, replace_complete_citation
from init import app, logger
from modules import models
from modules.models import get_accessible_model_list, find_model_config
from modules.utils import generate_unique_id, is_valid_citation_format, is_complete_citation_format

VERSION = '0.6.0'
# VERSION = 'test'
UPDATE_INFO = '去除PandoraNext相关服务依赖选项，并修改部分配置名，Respect Pandora！'
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

    upstream_response = send_text_prompt_and_get_response(messages, api_key, stream, model)

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
        upstream_response, data_queue, stop_event, last_data_time, api_key, chat_message_id, model))
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

    image_urls = []

    messages = [
        {
            "role": "user",
            "content": prompt,
            "hasName": False
        }
    ]

    upstream_response = send_text_prompt_and_get_response(messages, api_key, False, model)

    # 在非流式响应的情况下，我们需要一个变量来累积所有的 new_text
    all_new_text = ""

    # 处理流式响应
    def generate():
        nonlocal all_new_text  # 引用外部变量
        chat_message_id = generate_unique_id("chatcmpl")
        # 当前时间戳
        timestamp = int(time.time())

        buffer = ""
        last_full_text = ""  # 用于存储之前所有出现过的 parts 组成的完整文本
        last_full_code = ""
        last_full_code_result = ""
        last_content_type = None  # 用于记录上一个消息的内容类型
        conversation_id = ''
        citation_buffer = ""
        citation_accumulating = False
        for chunk in upstream_response.iter_content(chunk_size=1024):
            if chunk:
                buffer += chunk.decode('utf-8')
                # 检查是否存在 "event: ping"，如果存在，则只保留 "data:" 后面的内容
                if "event: ping" in buffer:
                    if "data:" in buffer:
                        buffer = buffer.split("data:", 1)[1]
                        buffer = "data:" + buffer
                # 使用正则表达式移除特定格式的字符串
                # print("应用正则表达式之前的 buffer:", buffer.replace('\n', '\\n'))
                buffer = re.sub(r'data: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}(\r\n|\r|\n){2}', '', buffer)
                # print("应用正则表达式之后的 buffer:", buffer.replace('\n', '\\n'))

                while 'data:' in buffer and '\n\n' in buffer:
                    end_index = buffer.index('\n\n') + 2
                    complete_data, buffer = buffer[:end_index], buffer[end_index:]
                    # 解析 data 块
                    try:
                        data_json = json.loads(complete_data.replace('data: ', ''))
                        # print(f"data_json: {data_json}")
                        message = data_json.get("message", {})

                        if message == None:
                            logger.error(f"message 为空: data_json: {data_json}")

                        message_status = message.get("status")
                        content = message.get("content", {})
                        role = message.get("author", {}).get("role")
                        content_type = content.get("content_type")
                        # logger.debug(f"content_type: {content_type}")
                        # logger.debug(f"last_content_type: {last_content_type}")

                        metadata = {}
                        citations = []
                        try:
                            metadata = message.get("metadata", {})
                            citations = metadata.get("citations", [])
                        except:
                            pass
                        name = message.get("author", {}).get("name")
                        if (
                                role == "user" or message_status == "finished_successfully" or role == "system") and role != "tool":
                            # 如果是用户发来的消息，直接舍弃
                            continue
                        try:
                            conversation_id = data_json.get("conversation_id")
                            logger.debug(f"conversation_id: {conversation_id}")
                        except:
                            pass
                            # 只获取新的部分
                        new_text = ""
                        is_img_message = False
                        parts = content.get("parts", [])
                        for part in parts:
                            try:
                                # print(f"part: {part}")
                                # print(f"part type: {part.get('content_type')}")
                                if part.get('content_type') == 'image_asset_pointer':
                                    logger.debug(f"find img message~")
                                    is_img_message = True
                                    asset_pointer = part.get('asset_pointer').replace('file-service://', '')
                                    logger.debug(f"asset_pointer: {asset_pointer}")
                                    image_url = f"{config.BASE_URL}{config.PROXY_API_PREFIX}/backend-api/files/{asset_pointer}/download"

                                    ak = get_access_key(api_key)
                                    if not ak or ak == '':
                                        return jsonify({"error": "Authorization header is missing or invalid"}), 401

                                    headers = {
                                        "Authorization": f"Bearer {ak}"
                                    }
                                    image_response = requests.get(image_url, headers=headers)

                                    if image_response.status_code == 200:
                                        download_url = image_response.json().get('download_url')
                                        logger.debug(f"download_url: {download_url}")
                                        if config.USE_OAIUSERCONTENT_URL == True and response_format == "url":
                                            image_link = f"{download_url}"
                                            image_urls.append(image_link)  # 将图片链接保存到列表中
                                            new_text = ""
                                        else:
                                            if response_format == "url":
                                                # 从URL下载图片
                                                # image_data = requests.get(download_url).content
                                                image_download_response = requests.get(download_url)
                                                # print(f"image_download_response: {image_download_response.text}")
                                                if image_download_response.status_code == 200:
                                                    logger.debug(f"下载图片成功")
                                                    image_data = image_download_response.content
                                                    today_image_url = save_image(image_data)  # 保存图片，并获取文件名
                                                    # new_text = f"\n![image]({UPLOAD_BASE_URL}/{today_image_url})\n[下载链接]({UPLOAD_BASE_URL}/{today_image_url})\n"
                                                    image_link = f"{config.UPLOAD_BASE_URL}/{today_image_url}"
                                                    image_urls.append(image_link)  # 将图片链接保存到列表中
                                                    new_text = ""
                                                else:
                                                    logger.error(f"下载图片失败: {image_download_response.text}")
                                            else:
                                                # 使用base64编码图片
                                                # image_data = requests.get(download_url).content
                                                image_download_response = requests.get(download_url)
                                                if image_download_response.status_code == 200:
                                                    logger.debug(f"下载图片成功")
                                                    image_data = image_download_response.content
                                                    image_base64 = base64.b64encode(image_data).decode('utf-8')
                                                    image_urls.append(image_base64)
                                                    new_text = ""
                                                else:
                                                    logger.error(f"下载图片失败: {image_download_response.text}")
                                        if last_content_type == "code":
                                            new_text = new_text
                                            # new_text = "\n```\n" + new_text
                                        logger.debug(f"new_text: {new_text}")
                                        is_img_message = True
                                    else:
                                        logger.error(f"获取图片下载链接失败: {image_response.text}")
                            except:
                                pass

                        if is_img_message == False:
                            # print(f"data_json: {data_json}")
                            if content_type == "multimodal_text" and last_content_type == "code":
                                new_text = "\n```\n" + content.get("text", "")
                            elif role == "tool" and name == "dalle.text2im":
                                logger.debug(f"无视消息: {content.get('text', '')}")
                                continue
                            # 代码块特殊处理
                            if content_type == "code" and last_content_type != "code" and content_type != None:
                                full_code = ''.join(content.get("text", ""))
                                new_text = "\n```\n" + full_code[len(last_full_code):]
                                # print(f"full_code: {full_code}")
                                # print(f"last_full_code: {last_full_code}")
                                # print(f"new_text: {new_text}")
                                last_full_code = full_code  # 更新完整代码以备下次比较

                            elif last_content_type == "code" and content_type != "code" and content_type != None:
                                full_code = ''.join(content.get("text", ""))
                                new_text = "\n```\n" + full_code[len(last_full_code):]
                                # print(f"full_code: {full_code}")
                                # print(f"last_full_code: {last_full_code}")
                                # print(f"new_text: {new_text}")
                                last_full_code = ""  # 更新完整代码以备下次比较

                            elif content_type == "code" and last_content_type == "code" and content_type != None:
                                full_code = ''.join(content.get("text", ""))
                                new_text = full_code[len(last_full_code):]
                                # print(f"full_code: {full_code}")
                                # print(f"last_full_code: {last_full_code}")
                                # print(f"new_text: {new_text}")
                                last_full_code = full_code  # 更新完整代码以备下次比较

                            else:
                                # 只获取新的 parts
                                parts = content.get("parts", [])
                                full_text = ''.join(parts)
                                new_text = full_text[len(last_full_text):]
                                last_full_text = full_text  # 更新完整文本以备下次比较
                                if "\u3010" in new_text and not citation_accumulating:
                                    citation_accumulating = True
                                    citation_buffer = citation_buffer + new_text
                                    logger.debug(f"开始积累引用: {citation_buffer}")
                                elif citation_accumulating:
                                    citation_buffer += new_text
                                    logger.debug(f"积累引用: {citation_buffer}")
                                if citation_accumulating:
                                    if is_valid_citation_format(citation_buffer):
                                        logger.debug(f"合法格式: {citation_buffer}")
                                        # 继续积累
                                        if is_complete_citation_format(citation_buffer):

                                            # 替换完整的引用格式
                                            replaced_text, remaining_text, is_potential_citation = replace_complete_citation(
                                                citation_buffer, citations)
                                            # print(replaced_text)  # 输出替换后的文本
                                            new_text = replaced_text

                                            if (is_potential_citation):
                                                citation_buffer = remaining_text
                                            else:
                                                citation_accumulating = False
                                                citation_buffer = ""
                                            logger.debug(f"替换完整的引用格式: {new_text}")
                                        else:
                                            continue
                                    else:
                                        # 不是合法格式，放弃积累并响应
                                        logger.debug(f"不合法格式: {citation_buffer}")
                                        new_text = citation_buffer
                                        citation_accumulating = False
                                        citation_buffer = ""

                            # Python 工具执行输出特殊处理
                            if role == "tool" and name == "python" and last_content_type != "execution_output" and content_type != None:

                                full_code_result = ''.join(content.get("text", ""))
                                new_text = "`Result:` \n```\n" + full_code_result[len(last_full_code_result):]
                                if last_content_type == "code":
                                    new_text = "\n```\n" + new_text
                                # print(f"full_code_result: {full_code_result}")
                                # print(f"last_full_code_result: {last_full_code_result}")
                                # print(f"new_text: {new_text}")
                                last_full_code_result = full_code_result  # 更新完整代码以备下次比较
                            elif last_content_type == "execution_output" and (
                                    role != "tool" or name != "python") and content_type != None:
                                # new_text = content.get("text", "") + "\n```"
                                full_code_result = ''.join(content.get("text", ""))
                                new_text = full_code_result[len(last_full_code_result):] + "\n```\n"
                                if content_type == "code":
                                    new_text = new_text + "\n```\n"
                                # print(f"full_code_result: {full_code_result}")
                                # print(f"last_full_code_result: {last_full_code_result}")
                                # print(f"new_text: {new_text}")
                                last_full_code_result = ""  # 更新完整代码以备下次比较
                            elif last_content_type == "execution_output" and role == "tool" and name == "python" and content_type != None:
                                full_code_result = ''.join(content.get("text", ""))
                                new_text = full_code_result[len(last_full_code_result):]
                                # print(f"full_code_result: {full_code_result}")
                                # print(f"last_full_code_result: {last_full_code_result}")
                                # print(f"new_text: {new_text}")
                                last_full_code_result = full_code_result

                        # print(f"收到数据: {data_json}")
                        # print(f"收到的完整文本: {full_text}")
                        # print(f"上次收到的完整文本: {last_full_text}")
                        # print(f"新的文本: {new_text}")

                        # 更新 last_content_type
                        if content_type != None:
                            last_content_type = content_type if role != "user" else last_content_type

                        new_data = {
                            "id": chat_message_id,
                            "object": "chat.completion.chunk",
                            "created": timestamp,
                            "model": message.get("metadata", {}).get("model_slug"),
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "content": ''.join(new_text)
                                    },
                                    "finish_reason": None
                                }
                            ]
                        }
                        # print(f"Role: {role}")
                        logger.info(f"发送消息: {new_text}")
                        tmp = 'data: ' + json.dumps(new_data, ensure_ascii=False) + '\n\n'
                        # print(f"发送数据: {tmp}")
                        # 累积 new_text
                        all_new_text += new_text
                        yield 'data: ' + json.dumps(new_data, ensure_ascii=False) + '\n\n'
                    except json.JSONDecodeError:
                        # print("JSON 解析错误")
                        logger.info(f"发送数据: {complete_data}")
                        if complete_data == 'data: [DONE]\n\n':
                            logger.info(f"会话结束")
                            yield complete_data
        if citation_buffer != "":
            new_data = {
                "id": chat_message_id,
                "object": "chat.completion.chunk",
                "created": timestamp,
                "model": message.get("metadata", {}).get("model_slug"),
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": ''.join(citation_buffer)
                        },
                        "finish_reason": None
                    }
                ]
            }
            tmp = 'data: ' + json.dumps(new_data) + '\n\n'
            # print(f"发送数据: {tmp}")
            # 累积 new_text
            all_new_text += citation_buffer
            yield 'data: ' + json.dumps(new_data) + '\n\n'
        if buffer:
            # print(f"最后的数据: {buffer}")
            # delete_conversation(conversation_id, api_key)
            try:
                buffer_json = json.loads(buffer)
                error_message = buffer_json.get("detail", {}).get("message", "未知错误")
                error_data = {
                    "id": chat_message_id,
                    "object": "chat.completion.chunk",
                    "created": timestamp,
                    "model": "error",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "content": ''.join("```\n" + error_message + "\n```")
                            },
                            "finish_reason": None
                        }
                    ]
                }
                tmp = 'data: ' + json.dumps(error_data) + '\n\n'
                logger.info(f"发送最后的数据: {tmp}")
                # 累积 new_text
                all_new_text += ''.join("```\n" + error_message + "\n```")
                yield 'data: ' + json.dumps(error_data) + '\n\n'
            except:
                # print("JSON 解析错误")
                logger.info(f"发送最后的数据: {buffer}")
                yield buffer

        # delete_conversation(conversation_id, api_key)

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
                "code": "content_policy_violation"
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
    logger.debug(f"response_json: {response_json}")

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
    app.run(host='0.0.0.0')
