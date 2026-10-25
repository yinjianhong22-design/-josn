# -*- coding: utf-8 -*-

# 数据简表解析、照片简表提取和模板匹配共用的列名归一规则。
COLUMN_ROLE_SYNONYMS = {
    'specified': ('规定值', '标准值', '允许偏差'),
    'measured': ('实测',),
    'pass_rate': ('合格率', '通过率'),
}


def normalize_column_role(name):
    """列名 -> specified/measured/pass_rate; 无法路由返回 None。"""
    import re
    normalized = re.sub(r'\s+', '', str(name or ''))
    for role, synonyms in COLUMN_ROLE_SYNONYMS.items():
        if any(word in normalized for word in synonyms):
            return role
    return None
