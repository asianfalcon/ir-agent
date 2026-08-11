#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AceCamp Research Client for OpenClaw
提供问答和文章及知识库搜索搜索功能
"""

import json
import os
import sys
from collections import OrderedDict
from datetime import datetime
from typing import Dict, List, Optional, Any

try:
    import requests
except ImportError:
    print('缺少依赖 requests，请先执行: python3 -m pip install requests', file=sys.stderr)
    sys.exit(1)

try:
    import urllib3
except ImportError:  # pragma: no cover
    urllib3 = None


if urllib3 is not None:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Skill 版本号。需与 SKILL.md frontmatter 的 version 保持一致；
# 用户拿到压缩包后可通过 `python3 scripts/acecamp_client.py version` 判断是否需要更新。
SKILL_VERSION = '1.0.0'


def _skill_md_path() -> str:
    """返回同包 SKILL.md 的绝对路径（scripts/ 的上一级目录）。"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SKILL.md')


def read_skill_md_version() -> Optional[str]:
    """读取 SKILL.md frontmatter 中的 version 字段；读不到返回 None。"""
    path = _skill_md_path()
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            in_frontmatter = False
            for raw_line in handle:
                line = raw_line.strip()
                if line == '---':
                    if in_frontmatter:
                        break
                    in_frontmatter = True
                    continue
                if in_frontmatter and line.startswith('version:'):
                    return line.split(':', 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def version_mismatch() -> Optional[str]:
    """若脚本常量与 SKILL.md 版本不一致，返回提示文案；一致或无法读取时返回 None。"""
    md_version = read_skill_md_version()
    if md_version is not None and md_version != SKILL_VERSION:
        return (f'版本不一致: 脚本 SKILL_VERSION={SKILL_VERSION}，'
                f'但 SKILL.md version={md_version}。请同步两处版本号。')
    return None


if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


class AceCampClient:
    """AceCamp API 客户端"""

    def __init__(self, api_key: str, base_url: str, timeout: int = 300, verify_ssl: bool = True):
        """
        初始化客户端

        Args:
            api_key: API Key
            base_url: API 基础 URL
            timeout: 请求超时时间（秒）
            verify_ssl: 是否校验证书
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'AceCamp-OpenClaw-Client/1.0'
        })

    def ask(
        self,
        question: str,
        mode: str = 'fast',
        search_scope: Optional[List[str]] = None,
        top_k: int = 8,
        include_references: bool = True,
        references: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        问答接口
        
        Args:
            question: 问题
            mode: 模式，fast 或 deep
            search_scope: 搜索范围
            top_k: 返回引用数量
            include_references: 是否包含引用
            references: 指定参考资料
            
        Returns:
            包含 answer 和 references 的字典
        """
        url = f'{self.base_url}/api/v1/personal/ask_stream'
        payload = {
            'question': question,
            'mode': mode,
        }

        if search_scope:
            payload['search_scope'] = search_scope
        if references:
            payload['references'] = references

        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=(10, self.timeout),
                verify=self.verify_ssl,
                stream=True,
                headers={'Accept': 'text/event-stream'}
            )
            response.raise_for_status()

            response.encoding = 'utf-8'

            result = self._collect_stream_answer(response)
            result['references'] = result['references'][:top_k] if include_references else []
            result['usage']['mode'] = mode
            return result
        except requests.exceptions.Timeout:
            return {
                'answer': '请求超时，请稍后重试（可尝试调大 timeout 参数）',
                'references':[],
                'usage': {}
            }
        except requests.exceptions.RequestException as e:
            return {
                'answer': f'请求失败: {str(e)}',
                'references':[],
                'usage': {}
            }

    def ask_raw(
        self,
        question: str,
        mode: str = 'fast',
        search_scope: Optional[List[str]] = None,
        top_k: int = 8,
        include_references: bool = True,
        references: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """问答接口，直接返回 AceCamp 原始答案文本。"""
        return self.ask(
            question=question,
            mode=mode,
            search_scope=search_scope,
            top_k=top_k,
            include_references=include_references,
            references=references
        )

    def _collect_stream_answer(self, response: requests.Response) -> Dict[str, Any]:
        answer_parts: List[str] =[]
        reasoning_parts: List[str] = []
        references: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        event_name = None
        data_lines: List[str] =[]

        print("⏳ 正在请求 AceCamp (Deep 模式耗时较长，请耐心等待)...\n", file=sys.stderr, flush=True)

        def flush_event() -> Optional[Dict[str, Any]]:
            nonlocal event_name, data_lines
            if not event_name:
                data_lines =[]
                return None

            raw_data = '\n'.join(data_lines)
            payload = None
            if raw_data:
                try:
                    payload = json.loads(raw_data)
                except json.JSONDecodeError:
                    payload = None

            parsed = {
                'event': event_name,
                'payload': payload
            }
            event_name = None
            data_lines =[]
            return parsed

        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue

            line = raw_line.strip()
            if not line:
                parsed = flush_event()
                if not parsed:
                    continue

                if parsed['event'] == 'stream-close':
                    break

                if parsed['event'] != 'stream-connect' or not parsed['payload']:
                    continue

                payload = parsed['payload']
                if payload.get('type') == 'error':
                    message = payload.get('data', {}).get('message') or '系统异常，请稍后重试'
                    return {
                        'answer': message,
                        'references':[],
                        'usage': {'error': message}
                    }

                data = payload.get('data') or {}
                completion = data.get('completion') or ''
                message_type = data.get('type') or 'content'

                if message_type == 'reasoning':
                    reasoning_parts.append(completion)
                    print(".", end="", file=sys.stderr, flush=True)
                else:
                    answer_parts.append(completion)
                    print("█", end="", file=sys.stderr, flush=True)

                for ref in data.get('references') or[]:
                    if not isinstance(ref, dict):
                        continue
                    key = json.dumps(ref, sort_keys=True, ensure_ascii=False)
                    references[key] = ref
                continue

            if line.startswith('event:'):
                event_name = line.split(':', 1)[1].strip()
            elif line.startswith('data:'):
                data_lines.append(line.split(':', 1)[1].strip())

        answer = ''.join(answer_parts).strip()
        usage: Dict[str, Any] = {}
        if reasoning_parts:
            usage['reasoning'] = ''.join(reasoning_parts).strip()

        return {
            'answer': answer or '抱歉，处理您的问题时出现了错误，请稍后重试。',
            'references': list(references.values()),
            'usage': usage
        }

    def search_articles(
        self,
        query: str,
        limit: int = 5,
        offset: int = 0,
        search_scope: Optional[List[str]] = None,
        original_query: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """搜索文章接口（兼容旧版）"""
        return self.search(
            query=query,
            types=['Article'],
            limit=limit,
            offset=offset,
            search_scope=search_scope,
            original_query=original_query,
            start_date=start_date,
            end_date=end_date
        )

    def knowledge_search(
        self,
        keyword: str,
        source_type: str = 'Note',
        page: int = 1,
        per_page: int = 10,
        version: Optional[str] = None,
        ack: Optional[str] = None
    ) -> Dict[str, Any]:
        """知识库搜索接口（通过 Personal API 复用网页同一搜索逻辑）"""
        url = f'{self.base_url}/api/v1/personal/knowledge_search'
        payload: Dict[str, Any] = {
            'keyword': keyword,
            'type': source_type,
            'page': page,
            'per_page': per_page,
            'page_size': per_page
        }
        if version:
            payload['version'] = version
        if ack:
            payload['ack'] = ack

        try:
            response = self.session.get(url, params=payload, timeout=self.timeout, verify=self.verify_ssl)
            response.raise_for_status()
            response.encoding = 'utf-8'
            result = response.json()

            if result.get('ret') and result.get('data') is not None:
                return result['data']
            return {
                'items': [],
                'meta': {
                    'returned': 0,
                    'error': result.get('msg', '未知错误')
                }
            }
        except requests.exceptions.RequestException as e:
            return {
                'items': [],
                'meta': {
                    'returned': 0,
                    'error': str(e)
                }
            }

    def search(
        self,
        query: str,
        types: Optional[List[str]] = None,
        limit: int = 5,
        offset: int = 0,
        search_scope: Optional[List[str]] = None,
        original_query: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        平台文章搜索接口（Personal API search）

        Args:
            query: 搜索关键词
            types: 搜索类型列表（当前后端仅返回 Article）
            limit: 返回数量
            offset: 偏移量
            search_scope: 搜索范围
            original_query: 用户原始问题/原文
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            包含 items 和 meta 的字典
        """
        url = f'{self.base_url}/api/v1/personal/search'
        original_query = original_query or query
        payload = {
            'query': query,
            'limit': limit,
            'offset': offset
        }

        if types:
            payload['types'] = types
        if search_scope:
            payload['search_scope'] = search_scope
        payload['original_query'] = original_query
        if start_date:
            payload['start_date'] = start_date
        if end_date:
            payload['end_date'] = end_date

        try:
            response = self.session.post(url, json=payload, timeout=self.timeout, verify=self.verify_ssl)
            response.raise_for_status()
            response.encoding = 'utf-8'
            result = response.json()

            if result.get('ret') and result.get('data'):
                return result['data']
            else:
                return {
                    'items':[],
                    'meta': {
                        'limit': limit,
                        'offset': offset,
                        'returned': 0,
                        'has_more': False,
                        'error': result.get('msg', '未知错误')
                    }
                }
        except requests.exceptions.Timeout:
            return {
                'items':[],
                'meta': {
                    'limit': limit,
                    'offset': offset,
                    'returned': 0,
                    'has_more': False,
                    'error': '请求超时'
                }
            }
        except requests.exceptions.RequestException as e:
            return {
                'items':[],
                'meta': {
                    'limit': limit,
                    'offset': offset,
                    'returned': 0,
                    'has_more': False,
                    'error': str(e)
                }
            }

    def notebooks(
        self,
        keyword: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> Dict[str, Any]:
        """文件夹列表接口"""
        url = f'{self.base_url}/api/v1/personal/notebooks'
        payload = {'limit': limit, 'offset': offset}
        if keyword:
            payload['keyword'] = keyword

        try:
            response = self.session.get(url, params=payload, timeout=self.timeout, verify=self.verify_ssl)
            response.raise_for_status()
            result = response.json()
            if result.get('ret') and result.get('data'):
                return result['data']
            return {'items': [], 'meta': {'returned': 0, 'has_more': False, 'error': result.get('msg', '未知错误')}}
        except requests.exceptions.RequestException as e:
            return {'items': [], 'meta': {'returned': 0, 'has_more': False, 'error': str(e)}}

    def notes(
        self,
        notebook_id: Optional[int] = None,
        keyword: Optional[str] = None,
        sort_by: str = 'updated_at',
        limit: int = 10,
        offset: int = 0
    ) -> Dict[str, Any]:
        """文档列表接口"""
        url = f'{self.base_url}/api/v1/personal/notes'
        payload = {'limit': limit, 'offset': offset, 'sort_by': sort_by}
        if notebook_id:
            payload['notebook_id'] = notebook_id
        if keyword:
            payload['keyword'] = keyword

        try:
            response = self.session.get(url, params=payload, timeout=self.timeout, verify=self.verify_ssl)
            response.raise_for_status()
            result = response.json()
            if result.get('ret') and result.get('data'):
                return result['data']
            return {'items': [], 'meta': {'returned': 0, 'has_more': False, 'error': result.get('msg', '未知错误')}}
        except requests.exceptions.RequestException as e:
            return {'items': [], 'meta': {'returned': 0, 'has_more': False, 'error': str(e)}}

    def note_detail(self, note_id: int) -> Dict[str, Any]:
        """文档详情接口"""
        url = f'{self.base_url}/api/v1/personal/notes/{note_id}'

        try:
            response = self.session.get(url, timeout=self.timeout, verify=self.verify_ssl)
            response.raise_for_status()
            result = response.json()
            if result.get('ret') and result.get('data') is not None:
                return result['data']
            if result.get('ret') and result.get('data') == {}:
                return {'error': '未找到文档，请确认使用的是 knowledge_search 返回的知识库文档 ID'}
            return {'error': result.get('msg', '未知错误')}
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    def recent_meetings(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        registered: Optional[bool] = None,
        organization_id: Optional[int] = None,
        event_type_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """近期会议列表接口"""
        url = f'{self.base_url}/api/v1/personal/recent_meetings'
        payload: Dict[str, Any] = {}
        if start_date:
            payload['start_date'] = start_date
        if end_date:
            payload['end_date'] = end_date
        if registered is not None:
            payload['registered'] = registered
        if organization_id is not None:
            payload['organization_id'] = organization_id
        if event_type_ids:
            payload['event_type_ids'] = event_type_ids

        try:
            response = self.session.get(url, params=payload, timeout=self.timeout, verify=self.verify_ssl)
            response.raise_for_status()
            result = response.json()
            if result.get('ret') and result.get('data'):
                return result['data']
            return {
                'items': [],
                'meta': {
                    'returned': 0,
                    'error': result.get('msg', '未知错误')
                }
            }
        except requests.exceptions.RequestException as e:
            return {
                'items': [],
                'meta': {
                    'returned': 0,
                    'error': str(e)
                }
            }


def load_config() -> Dict[str, str]:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')

    if not os.path.exists(config_path):
        raise FileNotFoundError(f'配置文件不存在: {config_path}')

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    if not config.get('api_key'):
        raise ValueError('请在 config.json 中配置 api_key')
    if not config.get('base_url'):
        raise ValueError('请在 config.json 中配置 base_url')

    if 'timeout' in config and (not isinstance(config['timeout'], int) or config['timeout'] <= 0):
        raise ValueError('config.json 中的 timeout 必须为正整数')

    if 'verify_ssl' in config and not isinstance(config['verify_ssl'], bool):
        raise ValueError('config.json 中的 verify_ssl 必须为 true 或 false')

    return config


def check_env() -> int:
    """检查运行环境和配置。"""
    issues: List[str] =[]

    if sys.version_info < (3, 9):
        issues.append(f'Python 版本过低: {sys.version.split()[0]}，建议使用 3.9+')

    if urllib3 is None:
        issues.append('缺少 urllib3，建议执行: python3 -m pip install urllib3')

    mismatch = version_mismatch()
    if mismatch:
        issues.append(mismatch)

    try:
        config = load_config()
    except Exception as error:  # pragma: no cover
        issues.append(str(error))
        config = None

    if config:
        print('环境检查通过:')
        print(f"- skill_version: {SKILL_VERSION}")
        print(f"- python: {sys.executable}")
        print(f"- version: {sys.version.split()[0]}")
        print(f"- base_url: {config['base_url']}")
        print(f"- timeout: {config.get('timeout', 300)}")
        print(f"- verify_ssl: {config.get('verify_ssl', True)}")
        print(f"- api_key: {'已配置' if config.get('api_key') else '未配置'}")

    if issues:
        print('环境检查失败:', file=sys.stderr)
        for issue in issues:
            print(f'- {issue}', file=sys.stderr)
        return 1

    return 0


def argument_value(args: List[str], *flags: str) -> Optional[str]:
    for flag in flags:
        if flag in args:
            flag_idx = args.index(flag)
            if flag_idx + 1 < len(args):
                return args[flag_idx + 1]
    return None


def argument_present(args: List[str], *flags: str) -> bool:
    return any(flag in args for flag in flags)


def positional_argument(args: List[str], command: str) -> Optional[str]:
    filtered: List[str] =[]
    skip_next = False
    for idx, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if idx == 0 and arg == command:
            continue
        if arg.startswith('--'):
            skip_next = True
            continue
        filtered.append(arg)

    return filtered[0] if filtered else None


def in_verbatim_mode(args: List[str]) -> bool:
    return not argument_present(args, '--allow-formatting')


def format_ask_response(result: Dict[str, Any]) -> str:
    """格式化问答响应"""
    lines =[]

    # 答案
    lines.append("## 答案\n")
    lines.append(result.get('answer', ''))
    lines.append("")

    # 引用
    references = result.get('references',[])
    if references:
        lines.append("## 引用来源\n")
        for idx, ref in enumerate(references, 1):
            lines.append(f"[{idx}] {ref.get('title', '未知标题')}")
            if ref.get('url'):
                lines.append(f"    链接: {ref['url']}")
            if ref.get('snippet'):
                lines.append(f"    摘要: {ref['snippet'][:100]}...")
            lines.append("")

    # 使用信息
    usage = result.get('usage', {})
    if usage:
        lines.append(f"检索命中: {usage.get('search_hits', 0)} 条")
        if usage.get('mode'):
            lines.append(f"模式: {usage['mode']}")
        if usage.get('agent'):
            lines.append(f"链路: {usage['agent']}")

    return '\n'.join(lines)


def format_ask_raw_response(result: Dict[str, Any], include_references: bool = True) -> str:
    """格式化原始问答响应，优先直出 AceCamp 原始 answer。"""
    lines = [result.get('answer', '')]

    references = result.get('references', []) if include_references else[]
    if references:
        lines.append('')
        lines.append('引用来源:')
        for idx, ref in enumerate(references, 1):
            title = ref.get('title', '未知标题')
            url = ref.get('url')
            lines.append(f'[{idx}] {title}')
            if url:
                lines.append(url)

    return '\n'.join(lines).strip()


def format_search_response(result: Dict[str, Any]) -> str:
    """格式化搜索响应"""
    lines = []

    items = result.get('items',[])
    meta = result.get('meta', {})

    if not items:
        error = meta.get('error', '未找到相关文章')
        return f"未找到结果: {error}"

    lines.append(f"## 搜索结果 (共 {len(items)} 篇)\n")

    for idx, item in enumerate(items, 1):
        type_label = {'article': '文章'}.get(item.get('type', ''), '')
        type_tag = f" [{type_label}]" if type_label else ''
        lines.append(f"### {idx}. {item.get('title', '未知标题')}{type_tag}")
        lines.append(f"发布时间: {item.get('published_at', '未知')}")
        if item.get('organization_name'):
            lines.append(f"作者: {item['organization_name']}")
        if item.get('snippet'):
            lines.append(f"\n{item['snippet']}\n")

        lines.append("")

    # 分页信息
    if meta.get('has_more'):
        lines.append(f"还有更多结果，使用 offset={meta.get('offset', 0) + meta.get('returned', 0)} 查看")

    return '\n'.join(lines)


def format_search_verbatim_response(result: Dict[str, Any]) -> str:
    items = result.get('items', [])
    meta = result.get('meta', {})

    if not items:
        error = meta.get('error', '未找到相关文章')
        return f"未找到结果: {error}"

    lines = [f"搜索结果 (共 {len(items)} 篇)"]
    for idx, item in enumerate(items, 1):
        type_label = {'article': '文章'}.get(item.get('type', ''), item.get('type', ''))
        lines.append(f"{idx}. {item.get('title', '未知标题')} {type_label}".strip())
        lines.append(f"发布时间: {item.get('published_at', '未知')}")
        if item.get('organization_name'):
            lines.append(f"作者: {item['organization_name']}")
        if item.get('snippet'):
            lines.append(str(item['snippet']))
        lines.append('---')

    if meta.get('has_more'):
        lines.append(f"还有更多结果，使用 offset={meta.get('offset', 0) + meta.get('returned', 0)} 查看")

    return '\n'.join(lines).rstrip('-\n')


def extract_knowledge_note_id(item: Dict[str, Any]) -> Optional[int]:
    record = item.get('record', {}) or {}
    source = record.get('source', {}) or {}
    source_type = record.get('source_type') or source.get('source_type')
    if source_type != 'Note':
        return None

    note_id = source.get('id') or record.get('source_id')
    if note_id in (None, ''):
        return None

    try:
        return int(note_id)
    except (TypeError, ValueError):
        return None


def format_knowledge_search_response(result: Dict[str, Any]) -> str:
    """格式化知识库搜索响应（与网页 knowledge/search 一致）"""
    items = result.get('items', [])
    meta = result.get('meta', {})

    if not items:
        error = meta.get('error', '未找到相关知识库内容')
        return f"未找到结果: {error}"

    lines = [f"## 知识库搜索结果 (共 {len(items)} 条)\n"]
    for idx, item in enumerate(items, 1):
        record = item.get('record', {}) or {}
        source = record.get('source', {}) or {}
        title = source.get('title') or '无标题'
        note_id = extract_knowledge_note_id(item)
        if note_id is not None:
            lines.append(f"### {idx}. {title} [知识库文档 ID: {note_id}]")
        else:
            lines.append(f"### {idx}. {title} [知识库文档]")

        updated_at = source.get('updated_at') or source.get('created_at')
        if updated_at:
            lines.append(f"更新时间: {updated_at}")

        notebooks = source.get('notebooks') or []
        if notebooks:
            lines.append(f"文件夹: {', '.join(nb.get('name', '') for nb in notebooks if nb.get('name'))}")

        content_fragments = []
        highlight = item.get('highlight') or {}
        content_fragments.extend(highlight.get('content') or [])
        content_fragments.extend(highlight.get('title') or [])

        inner_hits = item.get('inner_hits') or {}
        for key in ('attachments', 'notebooks'):
            for inner_item in inner_hits.get(key, []):
                inner_highlight = inner_item.get('highlight') or {}
                for values in inner_highlight.values():
                    content_fragments.extend(values or [])

        if not content_fragments and source.get('content'):
            content_fragments.append(str(source['content'])[:400])

        if content_fragments:
            lines.append('')
            lines.extend(content_fragments)

        if note_id is not None:
            lines.append('')
            lines.append(f"查看详情: python3 scripts/acecamp_client.py note_detail --id {note_id}")

        lines.append('')

    return '\n'.join(lines).strip()


def format_knowledge_search_verbatim_response(result: Dict[str, Any]) -> str:
    items = result.get('items', [])
    meta = result.get('meta', {})

    if not items:
        error = meta.get('error', '未找到相关知识库内容')
        return f"未找到结果: {error}"

    lines = [f"知识库搜索结果 (共 {len(items)} 条)"]
    for idx, item in enumerate(items, 1):
        record = item.get('record', {}) or {}
        source = record.get('source', {}) or {}
        title = source.get('title') or '无标题'
        note_id = extract_knowledge_note_id(item)
        header = f"{idx}. {title}"
        if note_id is not None:
            header += f" [知识库文档 ID: {note_id}]"
        lines.append(header)

        updated_at = source.get('updated_at') or source.get('created_at')
        if updated_at:
            lines.append(f"更新时间: {updated_at}")

        notebooks = source.get('notebooks') or []
        if notebooks:
            lines.append(f"文件夹: {', '.join(nb.get('name', '') for nb in notebooks if nb.get('name'))}")

        content_fragments = []
        highlight = item.get('highlight') or {}
        content_fragments.extend(highlight.get('content') or [])
        content_fragments.extend(highlight.get('title') or [])

        inner_hits = item.get('inner_hits') or {}
        for key in ('attachments', 'notebooks'):
            for inner_item in inner_hits.get(key, []):
                inner_highlight = inner_item.get('highlight') or {}
                for values in inner_highlight.values():
                    content_fragments.extend(values or [])

        if not content_fragments and source.get('content'):
            content_fragments.append(str(source['content']))

        lines.extend(fragment for fragment in content_fragments if fragment)

        if note_id is not None:
            lines.append(f"查看详情: python3 scripts/acecamp_client.py note_detail --id {note_id}")
        lines.append('---')

    return '\n'.join(lines).rstrip('-\n')


def format_recent_meetings_response(result: Dict[str, Any]) -> str:
    """格式化近期会议响应"""
    items = result.get('items', [])
    meta = result.get('meta', {})

    if not items:
        error = meta.get('error')
        return f"未找到近期会议{f': {error}' if error else ''}"

    lines = [f"## 近期会议 (共 {len(items)} 场)\n"]
    for idx, item in enumerate(items, 1):
        lines.append(f"### {idx}. {item.get('name', '未知会议')}")
        if item.get('time_range'):
            lines.append(f"时间段: {item['time_range']}")
        else:
            start_time = item.get('start_time')
            end_time = item.get('end_time')
            if start_time:
                lines.append(f"开始时间: {format_timestamp(start_time)}")
            if end_time:
                lines.append(f"结束时间: {format_timestamp(end_time)}")
        lines.append(f"会议形式: {item.get('meeting_way', '未知')}")
        lines.append(f"已报名: {'是' if item.get('is_registered') else '否'}")
        if item.get('registration_state'):
            lines.append(f"报名状态: {item['registration_state']}")
        if item.get('join_url'):
            lines.append(f"参会链接: {item['join_url']}")
        if item.get('offline_address'):
            lines.append(f"线下地址: {item['offline_address']}")
        lines.append("")

    return '\n'.join(lines)


def format_timestamp(value: Any) -> str:
    """将 unix 时间戳格式化为可读时间。"""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).strftime('%Y/%m/%d %H:%M')

    if isinstance(value, str) and value.isdigit():
        return datetime.fromtimestamp(int(value)).strftime('%Y/%m/%d %H:%M')

    return str(value)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python acecamp_client.py ask <question> [--mode fast|deep] [--scope certified,brokers] [--top-k 8]")
        print("  python acecamp_client.py ask_raw <question> [--mode fast|deep][--scope certified,brokers] [--top-k 8]")
        print("  python acecamp_client.py ask_summary <question> [--mode fast|deep] [--scope certified,brokers] [--top-k 8]")
        print("  python acecamp_client.py ask <question> --references '[{\"type\":\"Article\",\"id\":123}]'")
        print("  python acecamp_client.py search <query> [--limit 5] [--offset 0] [--scope certified,brokers] [--original-query \"用户原始问题\"]")
        print("  python acecamp_client.py knowledge_search --keyword \"存储 调价\" [--type Note] [--page 1] [--per-page 10]")
        print("  默认 search/knowledge_search 为强直出模式；仅在需要兼容旧格式时追加 --allow-formatting")
        print("  python acecamp_client.py recent_meetings [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--registered true|false] [--organization-id ID] [--event-type-ids 1,2,3]")
        print("  python acecamp_client.py notebooks [--keyword KEYWORD] [--limit 10] [--offset 0]")
        print("  python acecamp_client.py notes [--notebook-id ID] [--keyword KEYWORD] [--sort-by updated_at|created_at] [--limit 10] [--offset 0]")
        print("  python acecamp_client.py note_detail <id>")
        print("  python acecamp_client.py check_env")
        print("  python acecamp_client.py version")
        sys.exit(1)

    if sys.argv[1] in ('version', '--version', '-v'):
        print(SKILL_VERSION)
        mismatch = version_mismatch()
        if mismatch:
            print(f'警告: {mismatch}', file=sys.stderr)
        sys.exit(0)

    if sys.argv[1] == 'check_env':
        sys.exit(check_env())

    # 加载配置
    try:
        config = load_config()
    except Exception as e:
        print(f"配置错误: {e}")
        sys.exit(1)

    # 创建客户端
    client = AceCampClient(
        api_key=config['api_key'],
        base_url=config['base_url'],
        timeout=config.get('timeout', 300),
        verify_ssl=config.get('verify_ssl', True)
    )

    command = sys.argv[1]
    cli_args = sys.argv[1:]

    if command in ('ask', 'ask_raw', 'ask_summary'):
        question = argument_value(cli_args, '--question') or positional_argument(cli_args, command)
        if not question:
            print("请提供问题")
            sys.exit(1)

        mode = 'fast'
        top_k = 8
        search_scope = None
        references = None
        include_references = argument_present(cli_args, '--include-references')

        raw_mode = argument_value(cli_args, '--mode')
        if raw_mode:
            mode = raw_mode

        raw_top_k = argument_value(cli_args, '--top-k')
        if raw_top_k:
            top_k = int(raw_top_k)

        raw_scope = argument_value(cli_args, '--scope', '--search-scope', '--search_scope')
        if raw_scope:
            if ',' in raw_scope:
                search_scope = [item.strip() for item in raw_scope.split(',') if item.strip()]
            else:
                values: List[str] =[]
                if '--scope' in cli_args:
                    start = cli_args.index('--scope') + 1
                elif '--search-scope' in cli_args:
                    start = cli_args.index('--search-scope') + 1
                else:
                    start = -1
                if start != -1:
                    for arg in cli_args[start:]:
                        if arg.startswith('--'):
                            break
                        values.append(arg.strip())
                search_scope = values or [raw_scope.strip()]

        raw_references = argument_value(cli_args, '--references')
        if raw_references:
            references = json.loads(raw_references)

        result = client.ask_raw(
            question,
            mode=mode,
            search_scope=search_scope,
            top_k=top_k,
            include_references=include_references or (command != 'ask_summary'),
            references=references
        )
        if command in ('ask', 'ask_raw'):
            print(format_ask_raw_response(result, include_references=include_references))
        else:
            print(format_ask_response(result))

    elif command == 'search':
        verbatim_mode = in_verbatim_mode(cli_args)
        original_query_input = argument_value(cli_args, '--query') or positional_argument(cli_args, command)
        if not original_query_input:
            print("请提供搜索关键词")
            sys.exit(1)

        query = original_query_input

        types = None
        limit = 5
        offset = 0
        search_scope = None
        original_query = None
        start_date = None
        end_date = None

        raw_types = argument_value(cli_args, '--types')
        if raw_types:
            types =[item.strip() for item in raw_types.split(',') if item.strip()]

        raw_limit = argument_value(cli_args, '--limit')
        if raw_limit:
            limit = int(raw_limit)

        raw_offset = argument_value(cli_args, '--offset')
        if raw_offset:
            offset = int(raw_offset)

        raw_scope = argument_value(cli_args, '--scope', '--search-scope', '--search_scope')
        if raw_scope:
            if ',' in raw_scope:
                search_scope =[item.strip() for item in raw_scope.split(',') if item.strip()]
            else:
                values =[]
                if '--scope' in cli_args:
                    start = cli_args.index('--scope') + 1
                elif '--search-scope' in cli_args:
                    start = cli_args.index('--search-scope') + 1
                elif '--search_scope' in cli_args:
                    start = cli_args.index('--search_scope') + 1
                else:
                    start = -1
                if start != -1:
                    for arg in cli_args[start:]:
                        if arg.startswith('--'):
                            break
                        values.append(arg.strip())
                search_scope = values or [raw_scope.strip()]

        raw_start_date = argument_value(cli_args, '--start-date', '--start_date')
        if raw_start_date:
            start_date = raw_start_date

        raw_original_query = argument_value(cli_args, '--original-query', '--original_query')
        if raw_original_query:
            original_query = raw_original_query
        else:
            original_query = original_query_input

        raw_end_date = argument_value(cli_args, '--end-date', '--end_date')
        if raw_end_date:
            end_date = raw_end_date

        result = client.search(
            query,
            types=types,
            limit=limit,
            offset=offset,
            search_scope=search_scope,
            original_query=original_query,
            start_date=start_date,
            end_date=end_date
        )
        print(format_search_verbatim_response(result) if verbatim_mode else format_search_response(result))

    elif command == 'knowledge_search':
        verbatim_mode = in_verbatim_mode(cli_args)
        keyword = argument_value(cli_args, '--keyword', '--query') or positional_argument(cli_args, command)
        if not keyword:
            print('请提供知识库搜索关键词')
            sys.exit(1)

        source_type = argument_value(cli_args, '--type') or 'Note'
        page = int(argument_value(cli_args, '--page') or '1')
        per_page = int(argument_value(cli_args, '--per-page', '--per_page', '--page-size', '--page_size') or '10')
        version = argument_value(cli_args, '--version')
        ack = argument_value(cli_args, '--ack')

        result = client.knowledge_search(
            keyword=keyword,
            source_type=source_type,
            page=page,
            per_page=per_page,
            version=version,
            ack=ack
        )
        print(format_knowledge_search_verbatim_response(result) if verbatim_mode else format_knowledge_search_response(result))

    elif command == 'recent_meetings':
        start_date = argument_value(cli_args, '--start-date', '--start_date')
        end_date = argument_value(cli_args, '--end-date', '--end_date')
        raw_registered = argument_value(cli_args, '--registered')
        registered = None
        if raw_registered is not None:
            registered = raw_registered.lower() == 'true'
        organization_id = argument_value(cli_args, '--organization-id')
        if organization_id is not None:
            organization_id = int(organization_id)
        raw_event_type_ids = argument_value(cli_args, '--event-type-ids')
        event_type_ids = None
        if raw_event_type_ids:
            event_type_ids = [int(item.strip()) for item in raw_event_type_ids.split(',') if item.strip()]

        result = client.recent_meetings(
            start_date=start_date,
            end_date=end_date,
            registered=registered,
            organization_id=organization_id,
            event_type_ids=event_type_ids
        )
        print(format_recent_meetings_response(result))

    elif command == 'notebooks':
            keyword = argument_value(cli_args, '--keyword')
            limit = int(argument_value(cli_args, '--limit') or '10')
            offset = int(argument_value(cli_args, '--offset') or '0')
            result = client.notebooks(keyword=keyword, limit=limit, offset=offset)
            items = result.get('items',[])
            meta = result.get('meta', {})

            if not items:
                print("未找到文件夹")
            else:
                print(f"## 文件夹列表 (共 {len(items)} 个)\n")
                for item in items:
                    print(f"-[{item['id']}] {item['name']} ({item.get('note_count', 0)} 文档)")
                    if item.get('description'):
                        print(f"  描述: {item['description']}")

                if meta.get('has_more'):
                    next_offset = meta.get('offset', 0) + meta.get('returned', 0)
                    print(f"\n*还有更多文件夹，需要我为您继续翻页查看吗？(使用 --offset {next_offset})*")

    elif command == 'notes':
            notebook_id = argument_value(cli_args, '--notebook-id')
            if notebook_id:
                notebook_id = int(notebook_id)
            keyword = argument_value(cli_args, '--keyword')
            sort_by = argument_value(cli_args, '--sort-by') or 'updated_at'
            limit = int(argument_value(cli_args, '--limit') or '10')
            offset = int(argument_value(cli_args, '--offset') or '0')
            result = client.notes(notebook_id=notebook_id, keyword=keyword, sort_by=sort_by, limit=limit, offset=offset)
            items = result.get('items',[])
            meta = result.get('meta', {})

            if not items:
                print("未找到文档")
            else:
                print(f"## 文档列表 (共 {len(items)} 篇)\n")
                for item in items:
                    print(f"-[{item['id']}] {item['title']}")
                    if item.get('notebook_name'):
                        print(f"  文件夹: {item['notebook_name']}")
                    print(f"  更新时间: {item.get('updated_at')}")

                if meta.get('has_more'):
                    next_offset = meta.get('offset', 0) + meta.get('returned', 0)
                    print(f"\n*还有更多文档，需要我为您继续翻页查看吗？(使用 --offset {next_offset})*")

    elif command == 'note_detail':
            # 优先解析 --id 参数，同时兼容旧版的位置参数传法
            note_id_str = argument_value(cli_args, '--id') or positional_argument(cli_args, command)
            if not note_id_str:
                print("请提供文档 ID，例如: --id 12345")
                sys.exit(1)
            note_id = int(note_id_str)
            result = client.note_detail(note_id)
            if 'error' in result:
                print(f"获取文档失败: {result['error']}")
            else:
                print(f"## {result.get('title', '无标题')}\n")
                if result.get('notebooks'):
                    print(f"所属文件夹: {', '.join(nb['name'] for nb in result['notebooks'])}\n")
                if result.get('content'):
                    print(f"正文内容:\n{result['content']}")
                else:
                    print("正文内容为空")

    else:
        print(f"未知命令: {command}")
        print("支持的命令: ask, ask_raw, ask_summary, search, knowledge_search, recent_meetings, notebooks, notes, note_detail, check_env, version")
        sys.exit(1)


if __name__ == '__main__':
    main()
