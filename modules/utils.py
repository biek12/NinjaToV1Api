
import json
import uuid

# 读取配置文件
def load_config(file_path):
    """
    读取配置文件
    :return 配置文件的JSON对象
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def generate_unique_id(prefix):
    """
    生成全局唯一ID
    """
    # 生成一个随机的 UUID
    random_uuid = uuid.uuid4()
    # 将 UUID 转换为字符串，并移除其中的短横线
    random_uuid_str = str(random_uuid).replace('-', '')
    # 结合前缀和处理过的 UUID 生成最终的唯一 ID
    unique_id = f"{prefix}-{random_uuid_str}"
    return unique_id


def unicode_to_chinese(unicode_string):
    # 首先将字符串转换为标准的 JSON 格式字符串
    json_formatted_str = json.dumps(unicode_string)
    # 然后将 JSON 格式的字符串解析回正常的字符串
    return json.loads(json_formatted_str)


import re


# 辅助函数：检查是否为合法的引用格式或正在构建中的引用格式
def is_valid_citation_format(text):
    # 完整且合法的引用格式，允许紧跟另一个起始引用标记
    if re.fullmatch(r'\u3010\d+\u2020(source|\u6765\u6e90)\u3011\u3010?', text):
        return True

    # 完整且合法的引用格式

    if re.fullmatch(r'\u3010\d+\u2020(source|\u6765\u6e90)\u3011', text):
        return True

    # 合法的部分构建格式
    if re.fullmatch(r'\u3010(\d+)?(\u2020(source|\u6765\u6e90)?)?', text):
        return True

    # 不合法的格式
    return False


# 辅助函数：检查是否为完整的引用格式
# 检查是否为完整的引用格式
def is_complete_citation_format(text):
    return bool(re.fullmatch(r'\u3010\d+\u2020(source|\u6765\u6e90)\u3011\u3010?', text))


def is_valid_sandbox_combined_corrected_final_v2(text):
    # 更新正则表达式以包含所有合法格式
    patterns = [
        r'.*\(sandbox:\/[^)]*\)?',  # sandbox 后跟路径，包括不完整路径
        r'.*\(',  # 只有 "(" 也视为合法格式
        r'.*\(sandbox(:|$)',  # 匹配 "(sandbox" 或 "(sandbox:"，确保后面不跟其他字符或字符串结束
        r'.*\(sandbox:.*\n*',  # 匹配 "(sandbox:" 后跟任意数量的换行符
    ]

    # 检查文本是否符合任一合法格式
    return any(bool(re.fullmatch(pattern, text)) for pattern in patterns)


def is_complete_sandbox_format(text):
    # 完整格式应该类似于 (sandbox:/xx/xx/xx 或 (sandbox:/xx/xx)
    pattern = r'.*\(sandbox\:\/[^)]+\)\n*'  # 匹配 "(sandbox:" 后跟任意数量的换行符
    return bool(re.fullmatch(pattern, text))
