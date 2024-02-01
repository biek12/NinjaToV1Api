import hashlib
import json
from io import BytesIO

import requests
from PIL import Image
from flask import jsonify

from auth import get_access_key
from init import logger, redis_client


def get_image_dimensions(file_content):
    with Image.open(BytesIO(file_content)) as img:
        return img.width, img.height


def determine_file_use_case(mime_type):
    multimodal_types = ["image/jpeg", "image/webp", "image/png", "image/gif"]
    my_files_types = ["text/x-php", "application/msword", "text/x-c", "text/html",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                      "application/json", "text/javascript", "application/pdf",
                      "text/x-java", "text/x-tex", "text/x-typescript", "text/x-sh",
                      "text/x-csharp", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                      "text/x-c++", "application/x-latext", "text/markdown", "text/plain",
                      "text/x-ruby", "text/x-script.python"]

    if mime_type in multimodal_types:
        return "multimodal"
    elif mime_type in my_files_types:
        return "my_files"
    else:
        return "ace_upload"


def upload_file(file_content, mime_type, api_key, base_url, proxy_api_prefix):
    logger.debug("文件上传开始")

    width = None
    height = None
    if mime_type.startswith('image/'):
        try:
            width, height = get_image_dimensions(file_content)
        except Exception as e:
            logger.error(f"图片信息获取异常, 切换为text/plain： {e}")
            mime_type = 'text/plain'

    # logger.debug(f"文件内容: {file_content}")
    file_size = len(file_content)
    logger.debug(f"文件大小: {file_size}")
    file_extension = get_file_extension(mime_type)
    logger.debug(f"文件扩展名: {file_extension}")
    sha256_hash = hashlib.sha256(file_content).hexdigest()
    logger.debug(f"sha256_hash: {sha256_hash}")
    file_name = f"{sha256_hash}{file_extension}"
    logger.debug(f"文件名: {file_name}")

    logger.debug(f"Use Case: {determine_file_use_case(mime_type)}")

    if determine_file_use_case(mime_type) == "ace_upload":
        mime_type = ''
        logger.debug(f"非已知文件类型，MINE置空")

    # 第1步：调用/backend-api/files接口获取上传URL
    upload_api_url = f"{base_url}{proxy_api_prefix}/backend-api/files"
    upload_request_payload = {
        "file_name": file_name,
        "file_size": file_size,
        "use_case": determine_file_use_case(mime_type)
    }

    ak = get_access_key(api_key)

    if not ak or ak == '':
        return jsonify({"error": "Authorization header is missing or invalid"}), 401
    headers = {
        "Authorization": f"Bearer {ak}"
    }
    upload_response = requests.post(upload_api_url, json=upload_request_payload, headers=headers)
    logger.debug(f"upload_response: {upload_response.text}")
    if upload_response.status_code != 200:
        raise Exception("Failed to get upload URL")

    upload_data = upload_response.json()
    upload_url = upload_data.get("upload_url")
    logger.debug(f"upload_url: {upload_url}")
    file_id = upload_data.get("file_id")
    logger.debug(f"file_id: {file_id}")

    # 第2步：上传文件
    put_headers = {
        'Content-Type': mime_type,
        'x-ms-blob-type': 'BlockBlob'  # 添加这个头部
    }
    put_response = requests.put(upload_url, data=file_content, headers=put_headers)
    if put_response.status_code != 201:
        logger.debug(f"put_response: {put_response.text}")
        logger.debug(f"put_response status_code: {put_response.status_code}")
        raise Exception("Failed to upload file")

    # 第3步：检测上传是否成功并检查响应
    check_url = f"{base_url}{proxy_api_prefix}/backend-api/files/{file_id}/uploaded"
    check_response = requests.post(check_url, json={}, headers=headers)
    logger.debug(f"check_response: {check_response.text}")
    if check_response.status_code != 200:
        raise Exception("Failed to check file upload completion")

    check_data = check_response.json()
    if check_data.get("status") != "success":
        raise Exception("File upload completion check not successful")

    return {
        "file_id": file_id,
        "file_name": file_name,
        "size_bytes": file_size,
        "mimeType": mime_type,
        "width": width,
        "height": height
    }


def get_file_metadata(file_content, mime_type, api_key, base_url, proxy_api_prefix):
    sha256_hash = hashlib.sha256(file_content).hexdigest()
    logger.debug(f"sha256_hash: {sha256_hash}")
    # 首先尝试从Redis中获取数据
    cached_data = redis_client.get(sha256_hash)
    if cached_data is not None:
        # 如果在Redis中找到了数据，解码后直接返回
        logger.info(f"从Redis中获取到文件缓存数据")
        cache_file_data = json.loads(cached_data.decode())

        tag = True
        file_id = cache_file_data.get("file_id")
        # 检测之前的文件是否仍然有效
        check_url = f"{base_url}{proxy_api_prefix}/backend-api/files/{file_id}/uploaded"

        ak = get_access_key(api_key)

        if not ak or ak == '':
            return jsonify({"error": "Authorization header is missing or invalid"}), 401
        headers = {
            "Authorization": f"Bearer {ak}"
        }
        check_response = requests.post(check_url, json={}, headers=headers)
        logger.debug(f"check_response: {check_response.text}")
        if check_response.status_code != 200:
            tag = False

        check_data = check_response.json()
        if check_data.get("status") != "success":
            tag = False
        if tag:
            logger.info(f"Redis中的文件缓存数据有效，将使用缓存数据")
            return cache_file_data
        else:
            logger.info(f"Redis中的文件缓存数据已失效，重新上传文件")

    else:
        logger.info(f"Redis中没有找到文件缓存数据")
    # 如果Redis中没有，上传文件并保存新数据
    new_file_data = upload_file(file_content, mime_type, api_key, base_url, proxy_api_prefix)
    mime_type = new_file_data.get('mimeType')
    # 为图片类型文件添加宽度和高度信息
    if mime_type.startswith('image/'):
        width, height = get_image_dimensions(file_content)
        new_file_data['width'] = width
        new_file_data['height'] = height

    # 将新的文件数据存入Redis
    redis_client.set(sha256_hash, json.dumps(new_file_data))

    return new_file_data


def get_file_extension(mime_type):
    # 基于 MIME 类型返回文件扩展名的映射表
    extension_mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "text/x-php": ".php",
        "application/msword": ".doc",
        "text/x-c": ".c",
        "text/html": ".html",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/json": ".json",
        "text/javascript": ".js",
        "application/pdf": ".pdf",
        "text/x-java": ".java",
        "text/x-tex": ".tex",
        "text/x-typescript": ".ts",
        "text/x-sh": ".sh",
        "text/x-csharp": ".cs",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "text/x-c++": ".cpp",
        "application/x-latext": ".latex",  # 这里可能需要根据实际情况调整
        "text/markdown": ".md",
        "text/plain": ".txt",
        "text/x-ruby": ".rb",
        "text/x-script.python": ".py",
        # 其他 MIME 类型和扩展名...
    }
    return extension_mapping.get(mime_type, "")


my_files_types = [
    "text/x-php", "application/msword", "text/x-c", "text/html",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/json", "text/javascript", "application/pdf",
    "text/x-java", "text/x-tex", "text/x-typescript", "text/x-sh",
    "text/x-csharp", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/x-c++", "application/x-latext", "text/markdown", "text/plain",
    "text/x-ruby", "text/x-script.python"
]