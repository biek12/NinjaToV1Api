import base64
import io
import json
import os
import re
import time
import urllib.parse
from urllib.parse import unquote
import uuid
from datetime import datetime

import requests
import tiktoken
from PIL import Image
from flask import jsonify

import config
from auth import get_access_key
from init import logger
from modules import ua
from modules.files import get_file_metadata, my_files_types
from modules.models import find_model_config, generate_gpts_payload
from modules.utils import is_valid_citation_format, is_complete_citation_format, \
    is_valid_sandbox_combined_corrected_final_v2, is_complete_sandbox_format

BASE_URL = config.BASE_URL
PROXY_API_PREFIX = config.PROXY_API_PREFIX

# 定义发送请求的函数
def send_text_prompt_and_get_response(messages, api_key, stream, model):
    url = f"{BASE_URL}{PROXY_API_PREFIX}/backend-api/conversation"

    ak = get_access_key(api_key)
    if not ak or ak == '':
        return jsonify({"error": "Authorization header is missing or invalid"}), 401

    headers = {
        "Authorization": f"Bearer {ak}"
    }
    # 查找模型配置
    model_config = find_model_config(model)
    ori_model_name = ''
    if model_config:
        # 检查是否有 ori_name
        ori_model_name = model_config.get('ori_name', model)

    formatted_messages = []
    # logger.debug(f"原始 messages: {messages}")
    for message in messages:
        message_id = str(uuid.uuid4())
        content = message.get("content")

        if isinstance(content, list) and ori_model_name != 'gpt-3.5-turbo':
            logger.debug(f"gpt-vision 调用")
            new_parts = []
            attachments = []
            contains_image = False  # 标记是否包含图片

            for part in content:
                if isinstance(part, dict) and "type" in part:
                    if part["type"] == "text":
                        new_parts.append(part["text"])
                    elif part["type"] == "image_url":
                        # logger.debug(f"image_url: {part['image_url']}")
                        file_url = part["image_url"]["url"]
                        if file_url.startswith('data:'):
                            # 处理 base64 编码的文件数据
                            mime_type, base64_data = file_url.split(';')[0], file_url.split(',')[1]
                            mime_type = mime_type.split(':')[1]
                            try:
                                file_content = base64.b64decode(base64_data)
                            except Exception as e:
                                logger.error(f"类型为 {mime_type} 的 base64 编码数据解码失败: {e}")
                                continue
                        else:
                            # 处理普通的文件URL
                            try:
                                tmp_user_agent = ua.random
                                logger.debug(f"随机 User-Agent: {tmp_user_agent}")
                                tmp_headers = {
                                    'User-Agent': tmp_user_agent
                                }
                                file_response = requests.get(url=file_url, headers=tmp_headers)
                                file_content = file_response.content
                                mime_type = file_response.headers.get('Content-Type', '').split(';')[0].strip()
                            except Exception as e:
                                logger.error(f"获取文件 {file_url} 失败: {e}")
                                continue

                        logger.debug(f"mime_type: {mime_type}")
                        file_metadata = get_file_metadata(file_content, mime_type, api_key, BASE_URL, PROXY_API_PREFIX)

                        mime_type = file_metadata["mimeType"]
                        logger.debug(f"处理后 mime_type: {mime_type}")

                        if mime_type.startswith('image/'):
                            contains_image = True
                            new_part = {
                                "asset_pointer": f"file-service://{file_metadata['file_id']}",
                                "size_bytes": file_metadata["size_bytes"],
                                "width": file_metadata["width"],
                                "height": file_metadata["height"]
                            }
                            new_parts.append(new_part)

                        attachment = {
                            "name": file_metadata["file_name"],
                            "id": file_metadata["file_id"],
                            "mimeType": file_metadata["mimeType"],
                            "size": file_metadata["size_bytes"]  # 添加文件大小
                        }

                        if mime_type.startswith('image/'):
                            attachment.update({
                                "width": file_metadata["width"],
                                "height": file_metadata["height"]
                            })
                        elif mime_type in my_files_types:
                            attachment.update({"fileTokenSize": len(file_metadata["file_name"])})

                        attachments.append(attachment)
                else:
                    # 确保 part 是字符串
                    text_part = str(part) if not isinstance(part, str) else part
                    new_parts.append(text_part)

            content_type = "multimodal_text" if contains_image else "text"
            formatted_message = {
                "id": message_id,
                "author": {"role": message.get("role")},
                "content": {"content_type": content_type, "parts": new_parts},
                "metadata": {"attachments": attachments}
            }
            formatted_messages.append(formatted_message)
            logger.critical(f"formatted_message: {formatted_message}")

        else:
            # 处理单个文本消息的情况
            formatted_message = {
                "id": message_id,
                "author": {"role": message.get("role")},
                "content": {"content_type": "text", "parts": [content]},
                "metadata": {}
            }
            formatted_messages.append(formatted_message)

    # logger.debug(f"formatted_messages: {formatted_messages}")
    # return
    payload = {}

    logger.info(f"model: {model}")

    # 查找模型配置
    model_config = find_model_config(model)
    if model_config:
        # 检查是否有 ori_name
        ori_model_name = model_config.get('ori_name', model)
        logger.info(f"原模型名: {ori_model_name}")
        if ori_model_name == 'gpt-4-s':
            payload = {
                # 构建 payload
                "action": "next",
                "messages": formatted_messages,
                "parent_message_id": str(uuid.uuid4()),
                "model" :"gpt-4",
                "timezone_offset_min": -480,
                "suggestions" :[],
                "history_and_training_disabled": False,
                "conversation_mode" :{"kind" :"primary_assistant"} ,"force_paragen" :False ,"force_rate_limit" :False
            }
        elif ori_model_name == 'gpt-4-mobile':
            payload = {
                # 构建 payload
                "action": "next",
                "messages": formatted_messages,
                "parent_message_id": str(uuid.uuid4()),
                "model" :"gpt-4-mobile",
                "timezone_offset_min": -480,
                "suggestions" :
                    ["Give me 3 ideas about how to plan good New Years resolutions. Give me some that are personal, family, and professionally-oriented."
                    ,"Write a text asking a friend to be my plus-one at a wedding next month. I want to keep it super short and casual, and offer an out."
                    ,"Design a database schema for an online merch store."
                    ,"Compare Gen Z and Millennial marketing strategies for sunglasses."],
                "history_and_training_disabled": False,
                "conversation_mode" :{"kind" :"primary_assistant"} ,"force_paragen" :False ,"force_rate_limit" :False
            }
        elif ori_model_name == 'gpt-3.5-turbo':
            payload = {
                # 构建 payload
                "action": "next",
                "messages": formatted_messages,
                "parent_message_id": str(uuid.uuid4()),
                "model": "text-davinci-002-render-sha",
                "timezone_offset_min": -480,
                "suggestions": [
                    "What are 5 creative things I could do with my kids' art? I don't want to throw them away, but it's also so much clutter.",
                    "I want to cheer up my friend who's having a rough day. Can you suggest a couple short and sweet text messages to go with a kitten gif?",
                    "Come up with 5 concepts for a retro-style arcade game.",
                    "I have a photoshoot tomorrow. Can you recommend me some colors and outfit options that will look good on camera?"
                ],
                "history_and_training_disabled" :False,
                "arkose_token" :None,
                "conversation_mode": {
                    "kind": "primary_assistant"
                },
                "force_paragen" :False,
                "force_rate_limit" :False
            }
        else:
            payload = generate_gpts_payload(model, formatted_messages)
            if not payload:
                raise Exception('model is not accessible')
        # 根据NEED_DELETE_CONVERSATION_AFTER_RESPONSE修改history_and_training_disabled
        if config.NEED_DELETE_CONVERSATION_AFTER_RESPONSE:
            logger.debug(f"是否保留会话: {config.NEED_DELETE_CONVERSATION_AFTER_RESPONSE == False}")
            payload['history_and_training_disabled'] = True
        if ori_model_name != 'gpt-3.5-turbo':
            if config.CUSTOM_ARKOSE:
                pass
            #     token = get_token()
            #     payload["arkose_token"] = token
        logger.debug(f"payload: {payload}")
        response = requests.post(url, headers=headers, json=payload, stream=True)
        # print(response)
        return response


def delete_conversation(conversation_id, api_key):
    logger.info(f"准备删除的会话id： {conversation_id}")
    if not config.NEED_DELETE_CONVERSATION_AFTER_RESPONSE:
        logger.info(f"自动删除会话功能已禁用")
        return
    if conversation_id and config.NEED_DELETE_CONVERSATION_AFTER_RESPONSE:
        patch_url = f"{BASE_URL}{PROXY_API_PREFIX}/backend-api/conversation/{conversation_id}"

        ak = get_access_key(api_key)

        if not ak or ak == '':
            return jsonify({"error": "Authorization header is missing or invalid"}), 401

        patch_headers = {
            "Authorization": f"Bearer {ak}"
        }
        patch_data = {"is_visible": False}
        response = requests.patch(patch_url, headers=patch_headers, json=patch_data)

        if response.status_code == 200:
            logger.info(f"删除会话 {conversation_id} 成功")
        else:
            logger.error(f"PATCH 请求失败: {response.text}")


def save_image(image_data, path='images'):
    try:
        # print(f"image_data: {image_data}")
        if not os.path.exists(path):
            os.makedirs(path)
        current_time = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f'image_{current_time}.png'
        full_path = os.path.join(path, filename)
        logger.debug(f"完整的文件路径: {full_path}")  # 打印完整路径
        # print(f"filename: {filename}")
        # 使用 PIL 打开图像数据
        with Image.open(io.BytesIO(image_data)) as image:
            # 保存为 PNG 格式
            image.save(os.path.join(path, filename), 'PNG')

        logger.debug(f"保存图片成功: {filename}")

        return os.path.join(path, filename)
    except Exception as e:
        logger.error(f"保存图片时出现异常: {e}")


# 替换完整的引用格式
def replace_complete_citation(text, citations, bot_mode_enabled, bot_mode_enabled_bing_reference_output):
    def replace_match(match):
        citation_number = match.group(1)
        for citation in citations:
            cited_message_idx = citation.get('metadata', {}).get('extra', {}).get('cited_message_idx')
            logger.debug(f"cited_message_idx: {cited_message_idx}")
            logger.debug(f"citation_number: {citation_number}")
            logger.debug(f"is citation_number == cited_message_idx: {cited_message_idx == int(citation_number)}")
            logger.debug(f"citation: {citation}")
            if cited_message_idx == int(citation_number):
                url = citation.get("metadata", {}).get("url", "")
                if ((bot_mode_enabled == False) or (
                        bot_mode_enabled == True and bot_mode_enabled_bing_reference_output == True)):
                    return f"[[{citation_number}]({url})]"
                else:
                    return ""
        # return match.group(0)  # 如果没有找到对应的引用，返回原文本
        logger.critical(f"没有找到对应的引用，舍弃{match.group(0)}引用")
        return ""

    # 使用 finditer 找到第一个匹配项
    match_iter = re.finditer(r'\u3010(\d+)\u2020(source|\u6765\u6e90)\u3011', text)
    first_match = next(match_iter, None)

    if first_match:
        start, end = first_match.span()
        replaced_text = text[:start] + replace_match(first_match) + text[end:]
        remaining_text = text[end:]
    else:
        replaced_text = text
        remaining_text = ""

    is_potential_citation = is_valid_citation_format(remaining_text)

    # 替换掉replaced_text末尾的remaining_text

    logger.debug(f"replaced_text: {replaced_text}")
    logger.debug(f"remaining_text: {remaining_text}")
    logger.debug(f"is_potential_citation: {is_potential_citation}")
    if is_potential_citation:
        replaced_text = replaced_text[:-len(remaining_text)]

    return replaced_text, remaining_text, is_potential_citation


def replace_sandbox(text, conversation_id, message_id, api_key):
    def replace_match(match):
        sandbox_path = match.group(1)
        download_url = get_download_url(conversation_id, message_id, sandbox_path)
        if download_url is None:
            return "\n```\nError: 沙箱文件下载失败，这可能是因为您启用了隐私模式\n```"
        file_name = extract_filename(download_url)
        timestamped_file_name = timestamp_filename(file_name)
        if not config.USE_OAIUSERCONTENT_URL:
            download_file(download_url, timestamped_file_name)
            return f"({config.UPLOAD_BASE_URL}/files/{timestamped_file_name})"
        else:
            return f"({download_url})"

    def get_download_url(conversation_id, message_id, sandbox_path):
        # 模拟发起请求以获取下载 URL
        sandbox_info_url = f"{BASE_URL}{PROXY_API_PREFIX}/backend-api/conversation/{conversation_id}/interpreter/download?message_id={message_id}&sandbox_path={sandbox_path}"
        ak = get_access_key(api_key)

        if not ak or ak == '':
            return jsonify({"error": "Authorization header is missing or invalid"}), 401

        headers = {
            "Authorization": f"Bearer {ak}"
        }

        response = requests.get(sandbox_info_url, headers=headers)

        if response.status_code == 200:
            logger.debug(f"获取下载 URL 成功: {response.json()}")
            return response.json().get("download_url")
        else:
            logger.error(f"获取下载 URL 失败: {response.text}")
            return None

    def extract_filename(url):
        # 从 URL 中提取 filename 参数
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        filename = query_params.get("rscd", [""])[0].split("filename=")[-1]
        return filename

    def timestamp_filename(filename):
        # 在文件名前加上当前时间戳
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # 解码URL编码的filename
        decoded_filename = unquote(filename)

        return f"{timestamp}_{decoded_filename}"

    def download_file(download_url, filename):
        # 下载并保存文件
        # 确保 ./files 目录存在
        if not os.path.exists("./files"):
            os.makedirs("./files")
        file_path = f"./files/{filename}"
        with requests.get(download_url, stream=True) as r:
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

    # 替换 (sandbox:xxx) 格式的文本
    replaced_text = re.sub(r'\(sandbox:([^)]+)\)', replace_match, text)
    return replaced_text


def data_fetcher(upstream_response, data_queue, stop_event, last_data_time, api_key, chat_message_id, model):
    all_new_text = ""

    first_output = True

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
    file_output_buffer = ""
    file_output_accumulating = False
    execution_output_image_url_buffer = ""
    execution_output_image_id_buffer = ""
    try:
        for chunk in upstream_response.iter_content(chunk_size=1024):
            if stop_event.is_set():
                logger.info(f"接受到停止信号，停止数据处理线程")
                break
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

                        if message == {} or message == None:
                            logger.debug(f"message 为空: data_json: {data_json}")

                        message_id = message.get("id")
                        message_status = message.get("status")
                        content = message.get("content", {})
                        role = message.get("author", {}).get("role")
                        content_type = content.get("content_type")
                        print(f"content_type: {content_type}")
                        print(f"last_content_type: {last_content_type}")

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
                            # print(f"conversation_id: {conversation_id}")
                            if conversation_id:
                                data_queue.put(('conversation_id', conversation_id))
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
                                    image_url = f"{BASE_URL}{PROXY_API_PREFIX}/backend-api/files/{asset_pointer}/download"

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
                                        if config.USE_OAIUSERCONTENT_URL == True:
                                            if ((config.BOT_MODE_ENABLED == False) or (
                                                    config.BOT_MODE_ENABLED == True and config.BOT_MODE_ENABLED_MARKDOWN_IMAGE_OUTPUT == True)):
                                                new_text = f"\n![image]({download_url})\n[下载链接]({download_url})\n"
                                            if config.BOT_MODE_ENABLED == True and config.BOT_MODE_ENABLED_PLAIN_IMAGE_URL_OUTPUT == True:
                                                if all_new_text != "":
                                                    new_text = f"\n图片链接：{download_url}\n"
                                                else:
                                                    new_text = f"图片链接：{download_url}\n"
                                        else:
                                            # 从URL下载图片
                                            # image_data = requests.get(download_url).content
                                            image_download_response = requests.get(download_url)
                                            # print(f"image_download_response: {image_download_response.text}")
                                            if image_download_response.status_code == 200:
                                                logger.debug(f"下载图片成功")
                                                image_data = image_download_response.content
                                                today_image_url = save_image(image_data)  # 保存图片，并获取文件名
                                                if ((config.BOT_MODE_ENABLED == False) or (
                                                        config.BOT_MODE_ENABLED == True and config.BOT_MODE_ENABLED_MARKDOWN_IMAGE_OUTPUT == True)):
                                                    new_text = f"\n![image]({config.UPLOAD_BASE_URL}/{today_image_url})\n[下载链接]({config.UPLOAD_BASE_URL}/{today_image_url})\n"
                                                if config.BOT_MODE_ENABLED == True and config.BOT_MODE_ENABLED_PLAIN_IMAGE_URL_OUTPUT == True:
                                                    if all_new_text != "":
                                                        new_text = f"\n图片链接：{config.UPLOAD_BASE_URL}/{today_image_url}\n"
                                                    else:
                                                        new_text = f"图片链接：{config.UPLOAD_BASE_URL}/{today_image_url}\n"
                                            else:
                                                logger.error(f"下载图片失败: {image_download_response.text}")
                                        if last_content_type == "code":
                                            if config.BOT_MODE_ENABLED and config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT == False:
                                                new_text = new_text
                                            else:
                                                new_text = "\n```\n" + new_text

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
                                if config.BOT_MODE_ENABLED and config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT == False:
                                    new_text = content.get("text", "")
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
                                if config.BOT_MODE_ENABLED and config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT == False:
                                    new_text = ""

                            elif last_content_type == "code" and content_type != "code" and content_type != None:
                                full_code = ''.join(content.get("text", ""))
                                new_text = "\n```\n" + full_code[len(last_full_code):]
                                # print(f"full_code: {full_code}")
                                # print(f"last_full_code: {last_full_code}")
                                # print(f"new_text: {new_text}")
                                last_full_code = ""  # 更新完整代码以备下次比较
                                if config.BOT_MODE_ENABLED and config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT == False:
                                    new_text = ""

                            elif content_type == "code" and last_content_type == "code" and content_type != None:
                                full_code = ''.join(content.get("text", ""))
                                new_text = full_code[len(last_full_code):]
                                # print(f"full_code: {full_code}")
                                # print(f"last_full_code: {last_full_code}")
                                # print(f"new_text: {new_text}")
                                last_full_code = full_code  # 更新完整代码以备下次比较
                                if config.BOT_MODE_ENABLED and config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT == False:
                                    new_text = ""

                            else:
                                # 只获取新的 parts
                                parts = content.get("parts", [])
                                full_text = ''.join(parts)
                                new_text = full_text[len(last_full_text):]
                                if full_text != '':
                                    last_full_text = full_text  # 更新完整文本以备下次比较
                                if "\u3010" in new_text and not citation_accumulating:
                                    citation_accumulating = True
                                    citation_buffer = citation_buffer + new_text
                                    # print(f"开始积累引用: {citation_buffer}")
                                elif citation_accumulating:
                                    citation_buffer += new_text
                                    # print(f"积累引用: {citation_buffer}")
                                if citation_accumulating:
                                    if is_valid_citation_format(citation_buffer):
                                        # print(f"合法格式: {citation_buffer}")
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
                                            # print(f"替换完整的引用格式: {new_text}")
                                        else:
                                            continue
                                    else:
                                        # 不是合法格式，放弃积累并响应
                                        # print(f"不合法格式: {citation_buffer}")
                                        new_text = citation_buffer
                                        citation_accumulating = False
                                        citation_buffer = ""

                                if "(" in new_text and not file_output_accumulating and not citation_accumulating:
                                    file_output_accumulating = True
                                    file_output_buffer = file_output_buffer + new_text
                                    logger.debug(f"开始积累文件输出: {file_output_buffer}")
                                elif file_output_accumulating:
                                    file_output_buffer += new_text
                                    logger.debug(f"积累文件输出: {file_output_buffer}")
                                if file_output_accumulating:
                                    if is_valid_sandbox_combined_corrected_final_v2(file_output_buffer):
                                        logger.debug(f"合法文件输出格式: {file_output_buffer}")
                                        # 继续积累
                                        if is_complete_sandbox_format(file_output_buffer):
                                            # 替换完整的引用格式
                                            replaced_text = replace_sandbox(file_output_buffer, conversation_id,
                                                                            message_id, api_key)
                                            # print(replaced_text)  # 输出替换后的文本
                                            new_text = replaced_text
                                            file_output_accumulating = False
                                            file_output_buffer = ""
                                            logger.debug(f"替换完整的文件输出格式: {new_text}")
                                        else:
                                            continue
                                    else:
                                        # 不是合法格式，放弃积累并响应
                                        logger.debug(f"不合法格式: {file_output_buffer}")
                                        new_text = file_output_buffer
                                        file_output_accumulating = False
                                        file_output_buffer = ""

                            # Python 工具执行输出特殊处理
                            if role == "tool" and name == "python" and last_content_type != "execution_output" and content_type != None:
                                full_code_result = ''.join(content.get("text", ""))
                                new_text = "`Result:` \n```\n" + full_code_result[len(last_full_code_result):]
                                if last_content_type == "code":
                                    if config.BOT_MODE_ENABLED and config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT == False:
                                        new_text = ""
                                    else:
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
                                if config.BOT_MODE_ENABLED and config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT == False:
                                    new_text = ""
                                tmp_new_text = new_text
                                if execution_output_image_url_buffer != "":
                                    if ((config.BOT_MODE_ENABLED == False) or (
                                            config.BOT_MODE_ENABLED == True and config.BOT_MODE_ENABLED_MARKDOWN_IMAGE_OUTPUT == True)):
                                        logger.debug(f"BOT_MODE_ENABLED: {config.BOT_MODE_ENABLED}")
                                        logger.debug(
                                            f"BOT_MODE_ENABLED_MARKDOWN_IMAGE_OUTPUT: {config.BOT_MODE_ENABLED_MARKDOWN_IMAGE_OUTPUT}")
                                        new_text = tmp_new_text + f"![image]({execution_output_image_url_buffer})\n[下载链接]({execution_output_image_url_buffer})\n"
                                    if config.BOT_MODE_ENABLED == True and config.BOT_MODE_ENABLED_PLAIN_IMAGE_URL_OUTPUT == True:
                                        logger.debug(f"BOT_MODE_ENABLED: {config.BOT_MODE_ENABLED}")
                                        logger.debug(
                                            f"BOT_MODE_ENABLED_PLAIN_IMAGE_URL_OUTPUT: {config.BOT_MODE_ENABLED_PLAIN_IMAGE_URL_OUTPUT}")
                                        new_text = tmp_new_text + f"图片链接：{execution_output_image_url_buffer}\n"
                                    execution_output_image_url_buffer = ""

                                if content_type == "code":
                                    new_text = new_text + "\n```\n"
                                # print(f"full_code_result: {full_code_result}")
                                # print(f"last_full_code_result: {last_full_code_result}")
                                # print(f"new_text: {new_text}")
                                last_full_code_result = ""  # 更新完整代码以备下次比较
                            elif last_content_type == "execution_output" and role == "tool" and name == "python" and content_type != None:
                                full_code_result = ''.join(content.get("text", ""))
                                if config.BOT_MODE_ENABLED and config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT == False:
                                    new_text = ""
                                else:
                                    new_text = full_code_result[len(last_full_code_result):]
                                # print(f"full_code_result: {full_code_result}")
                                # print(f"last_full_code_result: {last_full_code_result}")
                                # print(f"new_text: {new_text}")
                                last_full_code_result = full_code_result

                            # 其余Action执行输出特殊处理
                            if role == "tool" and name != "python" and name != "dalle.text2im" and last_content_type != "execution_output" and content_type != None:
                                new_text = ""
                                if last_content_type == "code":
                                    if config.BOT_MODE_ENABLED and config.BOT_MODE_ENABLED_CODE_BLOCK_OUTPUT == False:
                                        new_text = ""
                                    else:
                                        new_text = "\n```\n" + new_text

                        # 检查 new_text 中是否包含 <<ImageDisplayed>>
                        if "<<ImageDisplayed>>" in last_full_code_result:
                            # 进行提取操作
                            aggregate_result = message.get("metadata", {}).get("aggregate_result", {})
                            if aggregate_result:
                                messages = aggregate_result.get("messages", [])
                                for msg in messages:
                                    if msg.get("message_type") == "image":
                                        image_url = msg.get("image_url")
                                        if image_url:
                                            # 从 image_url 提取所需的字段
                                            image_file_id = image_url.split('://')[-1]
                                            logger.info(f"提取到的图片文件ID: {image_file_id}")
                                            if image_file_id != execution_output_image_id_buffer:
                                                image_url = f"{BASE_URL}{PROXY_API_PREFIX}/backend-api/files/{image_file_id}/download"

                                                ak = get_access_key(api_key)

                                                if not ak or ak == '':
                                                    return jsonify(
                                                        {"error": "Authorization header is missing or invalid"}), 401
                                                headers = {
                                                    "Authorization": f"Bearer {ak}"
                                                }
                                                image_response = requests.get(image_url, headers=headers)

                                                if image_response.status_code == 200:
                                                    download_url = image_response.json().get('download_url')
                                                    logger.debug(f"download_url: {download_url}")
                                                    if config.USE_OAIUSERCONTENT_URL == True:
                                                        execution_output_image_url_buffer = download_url

                                                    else:
                                                        # 从URL下载图片
                                                        # image_data = requests.get(download_url).content
                                                        image_download_response = requests.get(download_url)
                                                        # print(f"image_download_response: {image_download_response.text}")
                                                        if image_download_response.status_code == 200:
                                                            logger.debug(f"下载图片成功")
                                                            image_data = image_download_response.content
                                                            today_image_url = save_image(image_data)  # 保存图片，并获取文件名
                                                            execution_output_image_url_buffer = f"{config.UPLOAD_BASE_URL}/{today_image_url}"

                                                        else:
                                                            logger.error(
                                                                f"下载图片失败: {image_download_response.text}")

                                            execution_output_image_id_buffer = image_file_id

                        # 从 new_text 中移除 <<ImageDisplayed>>
                        new_text = new_text.replace("<<ImageDisplayed>>", "图片生成中，请稍后\n")

                        # print(f"收到数据: {data_json}")
                        # print(f"收到的完整文本: {full_text}")
                        # print(f"上次收到的完整文本: {last_full_text}")
                        # print(f"新的文本: {new_text}")

                        # 更新 last_content_type
                        if content_type != None:
                            last_content_type = content_type if role != "user" else last_content_type

                        model_slug = message.get("metadata", {}).get("model_slug") or model

                        if first_output:
                            new_data = {
                                "id": chat_message_id,
                                "object": "chat.completion.chunk",
                                "created": timestamp,
                                "model": model_slug,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"role": "assistant"},
                                        "finish_reason": None
                                    }
                                ]
                            }
                            q_data = 'data: ' + json.dumps(new_data, ensure_ascii=False) + '\n\n'
                            data_queue.put(q_data)
                            first_output = False

                        new_data = {
                            "id": chat_message_id,
                            "object": "chat.completion.chunk",
                            "created": timestamp,
                            "model": model_slug,
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
                        q_data = 'data: ' + json.dumps(new_data, ensure_ascii=False) + '\n\n'
                        data_queue.put(q_data)
                        last_data_time[0] = time.time()
                        if stop_event.is_set():
                            break
                    except json.JSONDecodeError:
                        # print("JSON 解析错误")
                        logger.info(f"发送数据: {complete_data}")
                        if complete_data == 'data: [DONE]\n\n':
                            logger.info(f"会话结束")
                            q_data = complete_data
                            data_queue.put(('all_new_text', all_new_text))
                            data_queue.put(q_data)
                            last_data_time[0] = time.time()
                            if stop_event.is_set():
                                break
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
            q_data = 'data: ' + json.dumps(new_data) + '\n\n'
            data_queue.put(q_data)
            last_data_time[0] = time.time()
        if buffer:
            # print(f"最后的数据: {buffer}")
            # delete_conversation(conversation_id, api_key)
            try:
                buffer_json = json.loads(buffer)
                logger.info(f"最后的缓存数据: {buffer_json}")
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
                q_data = 'data: ' + json.dumps(error_data) + '\n\n'
                data_queue.put(q_data)
                last_data_time[0] = time.time()
                complete_data = 'data: [DONE]\n\n'
                logger.info(f"会话结束")
                q_data = complete_data
                data_queue.put(('all_new_text', all_new_text))
                data_queue.put(q_data)
                last_data_time[0] = time.time()
            except:
                # print("JSON 解析错误")
                logger.info(f"发送最后的数据: {buffer}")
                error_data = {
                    "id": chat_message_id,
                    "object": "chat.completion.chunk",
                    "created": timestamp,
                    "model": "error",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "content": ''.join("```\n" + buffer + "\n```")
                            },
                            "finish_reason": None
                        }
                    ]
                }
                tmp = 'data: ' + json.dumps(error_data) + '\n\n'
                q_data = tmp
                data_queue.put(q_data)
                last_data_time[0] = time.time()
                complete_data = 'data: [DONE]\n\n'
                logger.info(f"会话结束")
                q_data = complete_data
                data_queue.put(('all_new_text', all_new_text))
                data_queue.put(q_data)
                last_data_time[0] = time.time()
    except Exception as e:
        logger.error(f"Exception: {e}")
        complete_data = 'data: [DONE]\n\n'
        logger.info(f"会话结束")
        q_data = complete_data
        data_queue.put(('all_new_text', all_new_text))
        data_queue.put(q_data)
        last_data_time[0] = time.time()


def keep_alive(last_data_time, stop_event, queue, model, chat_message_id):
    while not stop_event.is_set():
        if time.time() - last_data_time[0] >= 1:
            # logger.debug(f"发送保活消息")
            # 当前时间戳
            timestamp = int(time.time())
            new_data = {
                "id": chat_message_id,
                "object": "chat.completion.chunk",
                "created": timestamp,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": ''
                        },
                        "finish_reason": None
                    }
                ]
            }
            queue.put(f'data: {json.dumps(new_data)}\n\n')  # 发送保活消息
            last_data_time[0] = time.time()
        time.sleep(1)

    if stop_event.is_set():
        logger.debug(f"接受到停止信号，停止保活线程")
        return


def count_tokens(text, model_name):
    """
    Count the number of tokens for a given text using a specified model.

    :param text: The text to be tokenized.
    :param model_name: The name of the model to use for tokenization.
    :return: Number of tokens in the text for the specified model.
    """
    # 获取指定模型的编码器
    if model_name == 'gpt-3.5-turbo':
        model_name = 'gpt-3.5-turbo'
    else:
        model_name = 'gpt-4'
    encoder = tiktoken.encoding_for_model(model_name)

    # 编码文本并计算token数量
    token_list = encoder.encode(text)
    return len(token_list)


def count_total_input_words(messages, model):
    """
    Count the total number of words in all messages' content.
    """
    total_words = 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, list):  # 判断content是否为列表
            for item in content:
                if item.get("type") == "text":  # 仅处理类型为"text"的项
                    text_content = item.get("text", "")
                    total_words += count_tokens(text_content, model)
        elif isinstance(content, str):  # 处理字符串类型的content
            total_words += count_tokens(content, model)
        # 不处理其他类型的content

    return total_words