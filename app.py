"""Character Compass 本地 API；浏览器或桌面窗口共用。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.parse import urlparse

from deepseek_client import GenerationError, generate
from character_memory import parse_observations
from novel_core import (ROUTES, actual_cost, build_messages, merge_character_analyses,
                        request_ceiling, split_text)
from storage import Store, body_hash, write_text

SOURCE_ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', SOURCE_ROOT))
WEB = RESOURCE_ROOT / 'web'
if getattr(sys, 'frozen', False):
    user_base = Path(os.environ.get('APPDATA', Path.home() / '.local' / 'share'))
    DATA_ROOT = user_base / 'CharacterCompass' / 'library'
    ENV_FILE = user_base / 'CharacterCompass' / '.env'
else:
    DATA_ROOT = SOURCE_ROOT / 'data' / 'library'
    ENV_FILE = SOURCE_ROOT / '.env'
LEGACY_SQLITE = SOURCE_ROOT / 'data' / 'novels.sqlite3'


def load_env():
    path = Path(os.environ.get('CHARACTER_COMPASS_ENV_FILE', ENV_FILE))
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
_store = None
_balance_cache = {'time': 0.0, 'result': None}
_balance_lock = Lock()
_activity = {'state': 'idle', 'task': '', 'model': ''}
_activity_lock = Lock()


def save_api_key(key: str):
    """只在本机 .env 保存 Key；现有预算配置原样保留。"""
    if len(key) > 300 or any(char.isspace() for char in key):
        raise ApiError('API Key 格式无效。')
    path = Path(os.environ.get('CHARACTER_COMPASS_ENV_FILE', ENV_FILE))
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    lines = [line for line in lines if line.split('=', 1)[0].strip() != 'DEEPSEEK_API_KEY']
    lines.insert(0, 'DEEPSEEK_API_KEY=' + key)
    write_text(path, '\n'.join(lines) + '\n')
    os.environ['DEEPSEEK_API_KEY'] = key
    with _balance_lock:
        _balance_cache.update(time=0.0, result=None)


def store():
    global _store
    if _store is None:
        _store = Store(DATA_ROOT, LEGACY_SQLITE)
    return _store


def balance():
    """调用 DeepSeek 官方只读余额接口，缓存一分钟；不返回 Key。"""
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if not key:
        raise ApiError('未配置 DeepSeek API Key。')
    with _balance_lock:
        if _balance_cache['result'] is not None and monotonic() - _balance_cache['time'] < 60:
            return _balance_cache['result']
        req = urllib.request.Request('https://api.deepseek.com/user/balance',
                 headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise ApiError(f'余额查询失败（HTTP {exc.code}）。', 502) from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ApiError('余额查询失败，请检查网络和 Key。', 502) from exc
        entries = []
        for item in data.get('balance_infos', []):
            entries.append({key: item.get(key, '') for key in
                ('currency', 'total_balance', 'granted_balance', 'topped_up_balance')})
        result = {'is_available': bool(data.get('is_available')), 'balance_infos': entries}
        _balance_cache.update(time=monotonic(), result=result)
        return result


class ApiError(Exception):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


class Handler(BaseHTTPRequestHandler):
    server_version = 'CharacterCompass/0.2'

    def log_message(self, fmt, *args):
        if self.path.startswith('/api/activity'):
            return
        print('[HTTP] ' + fmt % args)

    def send_json(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            raise ApiError('Content-Length 无效。')
        if length < 1 or length > 100_000_000:
            raise ApiError('请求内容为空或过大。')
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError('请求不是有效 JSON。')
        if not isinstance(value, dict):
            raise ApiError('请求必须是 JSON 对象。')
        return value

    def field(self, data, name, limit):
        text = data.get(name, '')
        if not isinstance(text, str) or len(text) > limit:
            raise ApiError(f'{name} 必须是文本，最多 {limit} 字符。')
        return text

    def static(self, path):
        allowed = {'/': 'index.html', '/index.html': 'index.html', '/style.css': 'style.css',
                   '/app.js': 'app.js', '/assets/icon.svg': 'assets/icon.svg'}
        name = allowed.get(path)
        if name is None:
            raise ApiError('未找到页面。', 404)
        file = WEB / name
        if not file.exists():
            raise ApiError('页面资源不存在。', 404)
        data = file.read_bytes()
        extension = file.suffix
        mime = {'.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript',
                '.svg': 'image/svg+xml', '.png': 'image/png'}[extension]
        self.send_response(200)
        self.send_header('Content-Type', mime + ('' if extension == '.png' else '; charset=utf-8'))
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def route(self, method):
        path = urlparse(self.path).path
        if not path.startswith('/api/'):
            if method != 'GET':
                raise ApiError('方法不允许。', 405)
            self.static(path)
            return
        parts = path.strip('/').split('/')
        data_store = store()
        if parts == ['api', 'config'] and method == 'GET':
            self.send_json({'key_configured': bool(os.environ.get('DEEPSEEK_API_KEY')),
                'daily_budget_usd': float(os.environ.get('DAILY_BUDGET_USD', '1.00')),
                'max_call_usd': float(os.environ.get('MAX_CALL_USD', '0.30')),
                'used_today_usd': data_store.spend_today(),
                'model_routes': {name: route.model for name, route in ROUTES.items()}})
            return
        if parts == ['api', 'config', 'key'] and method == 'POST':
            key = self.field(self.read_json(), 'key', 300).strip()
            save_api_key(key)
            self.send_json({'key_configured': bool(key)})
            return
        if parts == ['api', 'balance'] and method == 'GET':
            self.send_json(balance())
            return
        if parts == ['api', 'activity'] and method == 'GET':
            with _activity_lock:
                self.send_json(dict(_activity))
            return
        if parts == ['api', 'novels']:
            if method == 'GET':
                self.send_json(data_store.list_novels()); return
            if method == 'POST':
                data = self.read_json()
                title = self.field(data, 'title', 150).strip()
                if not title:
                    raise ApiError('请填写小说标题。')
                self.send_json(data_store.create_novel(title, self.field(data, 'premise', 3000)), 201)
                return
        if parts == ['api', 'novels', 'import'] and method == 'POST':
            backup = self.read_json()
            source = backup.get('novel')
            if backup.get('format') != 'character-compass-v1' or not isinstance(source, dict):
                raise ApiError('不是 Character Compass v1 备份。')
            title = self.field(source, 'title', 150).strip()
            if not title:
                raise ApiError('备份缺少小说标题。')
            fields = {key: self.field(source, key, limit) for key, limit in {
                'premise': 3000, 'outline': 50000, 'worldbuilding': 50000, 'scene_brief': 2500,
                'bible': 5000000, 'arc_plan': 50000, 'draft': 50000}.items()}
            legacy_opening = self.field(source, 'opening', 150000) if 'opening' in source else ''
            chapters = source.get('chapters', [])
            if not isinstance(chapters, list) or len(chapters) > 10000:
                raise ApiError('章节列表无效或过长。')
            validated, numbers, chapter_ids = [], set(), set()
            for item in chapters:
                if not isinstance(item, dict) or not isinstance(item.get('number'), int):
                    raise ApiError('备份中有无效章节。')
                number = item['number']
                if not 1 <= number <= 10000 or number in numbers:
                    raise ApiError('备份中的章节序号重复或越界。')
                numbers.add(number)
                chapter_id = item.get('id', len(validated) + 1)
                if type(chapter_id) is not int or chapter_id < 1 or chapter_id in chapter_ids:
                    raise ApiError('备份中的章节编号无效或重复。')
                chapter_ids.add(chapter_id)
                memory = {}
                if 'summary_source_hash' in item:
                    source_hash = item['summary_source_hash']
                    if source_hash is not None and (not isinstance(source_hash, str) or len(source_hash) != 64):
                        raise ApiError('备份的章节记忆来源无效。')
                    memory['summary_source_hash'] = source_hash
                candidate = item.get('character_update')
                if candidate is not None:
                    try:
                        if not isinstance(candidate, dict):
                            raise ValueError()
                        for key in ('id', 'body_hash', 'summary_hash'):
                            if not isinstance(candidate.get(key), str) or len(candidate[key]) != 64:
                                raise ValueError()
                        observations = parse_observations(json.dumps(candidate, ensure_ascii=False))
                        applied = candidate.get('applied_names', [])
                        if not isinstance(applied, list) or any(not isinstance(n, str) for n in applied) or not set(applied).issubset({p['name'] for p in observations}):
                            raise ValueError()
                        memory['character_update'] = {**candidate, 'characters': observations, 'applied_names': applied}
                    except (ValueError, TypeError):
                        raise ApiError('备份中的人物变化记录无效。')
                validated.append((number, self.field(item, 'title', 150),
                    self.field(item, 'body', 150000), self.field(item, 'summary', 10000), chapter_id, memory))
            novel = data_store.create_novel(title, fields['premise'])
            novel_id = novel['id']
            data_store.update_novel(novel_id, {key: val for key, val in fields.items() if key != 'premise'})
            for chapter in validated:
                created = data_store.create_chapter(novel_id, *chapter[:3], summary=chapter[3], chapter_id=chapter[4])
                data_store.restore_chapter_memory(novel_id, created['id'], chapter[5])
            if legacy_opening:
                data_store.merge_legacy_opening(novel_id, legacy_opening)
            self.send_json(data_store.novel_state(novel_id, full=False), 201)
            return
        if len(parts) < 3 or parts[1] != 'novels':
            raise ApiError('未找到接口。', 404)
        try:
            novel_id = int(parts[2])
        except ValueError:
            raise ApiError('小说编号无效。')
        novel = data_store.novel_state(novel_id, full=False)
        if novel is None:
            raise ApiError('小说不存在。', 404)
        if len(parts) == 3:
            if method == 'GET':
                self.send_json(novel); return
            if method == 'PUT':
                data = self.read_json()
                allowed = {'title': 150, 'premise': 3000,
                           'outline': 50000, 'worldbuilding': 50000, 'scene_brief': 2500,
                           'bible': 5000000, 'arc_plan': 50000, 'draft': 50000}
                updates = {key: self.field(data, key, limit) for key, limit in allowed.items() if key in data}
                if not updates or ('title' in updates and not updates['title'].strip()):
                    raise ApiError('没有可保存的字段，或标题为空。')
                data_store.update_novel(novel_id, updates)
                self.send_json(data_store.novel_state(novel_id, full=False)); return
        if len(parts) == 4 and parts[3] == 'chapters' and method == 'POST':
            data = self.read_json()
            number = data.get('number')
            if not isinstance(number, int) or not 1 <= number <= 10000:
                raise ApiError('章节序号必须是 1 到 10000 的整数。')
            try:
                chapter = data_store.create_chapter(novel_id, number,
                    self.field(data, 'title', 150), self.field(data, 'body', 150000))
            except ValueError as exc:
                raise ApiError(str(exc))
            self.send_json(chapter, 201); return
        if len(parts) == 5 and parts[3] == 'chapters':
            try:
                chapter_id = int(parts[4])
            except ValueError:
                raise ApiError('章节编号无效。')
            chapter = data_store.chapter(novel_id, chapter_id)
            if chapter is None:
                raise ApiError('章节不存在。', 404)
            if method == 'GET':
                self.send_json(chapter); return
            if method == 'PUT':
                data = self.read_json()
                allowed = {'title': 150, 'body': 150000, 'summary': 10000}
                updates = {key: self.field(data, key, limit) for key, limit in allowed.items() if key in data}
                if 'number' in data:
                    if not isinstance(data['number'], int) or not 1 <= data['number'] <= 10000:
                        raise ApiError('章节序号必须是 1 到 10000 的整数。')
                    updates['number'] = data['number']
                if not updates:
                    raise ApiError('没有可保存的字段。')
                try:
                    self.send_json(data_store.update_chapter(novel_id, chapter_id, updates))
                except ValueError as exc:
                    raise ApiError(str(exc)) from exc
                return
            if method == 'DELETE':
                data_store.delete_chapter(novel_id, chapter_id)
                self.send_json({'deleted': True}); return
        if len(parts) == 6 and parts[3] == 'chapters' and parts[5] == 'characters' and method == 'PUT':
            try:
                chapter_id = int(parts[4])
                data = self.read_json()
                names = data.get('names')
                if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
                    raise ValueError('人物选择无效。')
                self.send_json(data_store.apply_character_proposal(novel_id, chapter_id,
                    self.field(data, 'proposal_id', 100), names, self.field(data, 'bible_hash', 100)))
            except ValueError as exc:
                raise ApiError(str(exc), 409) from exc
            return
        if len(parts) == 4 and parts[3] == 'calls' and method == 'GET':
            self.send_json(data_store.list_calls(novel_id)); return
        if len(parts) == 5 and parts[3] == 'calls' and method == 'GET':
            try:
                call_id = int(parts[4])
            except ValueError:
                raise ApiError('调用编号无效。')
            call = data_store.get_call(novel_id, call_id)
            if call is None:
                raise ApiError('调用不存在。', 404)
            self.send_json(call); return
        if len(parts) == 4 and parts[3] == 'export' and method == 'GET':
            self.send_json({'format': 'character-compass-v1',
                            'novel': data_store.novel_state(novel_id, full=True)}); return
        if len(parts) == 4 and parts[3] == 'generate' and method == 'POST':
            self.handle_generate(data_store, novel, self.read_json()); return
        raise ApiError('未找到接口。', 404)

    def handle_generate(self, data_store, novel, data):
        task = data.get('task')
        if task not in ROUTES:
            raise ApiError('不支持这个生成任务。')
        chapters = list(novel['chapters'])
        chapter_id = None
        if task in ('draft', 'draft_pro'):
            scene = self.field(data, 'scene', 2500).strip()
            if not scene:
                raise ApiError('先写这次场景的要求。')
        elif task in ('summarize', 'character_updates'):
            chapter_id = data.get('chapter_id')
            chapter = data_store.chapter(novel['id'], chapter_id) if isinstance(chapter_id, int) else None
            if not chapter or not chapter['body'].strip():
                raise ApiError('先保存本章正文。')
            if task == 'character_updates':
                if chapter['summary_status'] != 'current':
                    raise ApiError('请先从当前正文提取章节记忆，再更新人物。')
                try:
                    bible = json.loads(novel['bible']) if novel['bible'].strip() else {'characters': []}
                    if not isinstance(bible, dict) or not isinstance(bible.get('characters', []), list):
                        raise ValueError()
                except ValueError:
                    raise ApiError('请先修正人物档案 JSON，再提取人物变化。')
                proposal = chapter.get('character_update')
                if proposal and chapter['character_sync_status'] != 'stale':
                    self.send_json({'proposal': proposal, 'bible_hash': body_hash(novel['bible']),
                                    'cached': True, 'content': '', 'model': ROUTES[task].model,
                                    'cost_usd_estimate': 0, 'requests': 0, 'finish_reason': 'stop'})
                    return
                scene = chapter['summary']
            else:
                scene = chapter['body']
        elif task == 'analyze':
            first = next((ch for ch in chapters if ch['number'] == 1), None)
            chapter = data_store.chapter(novel['id'], first['id']) if first else None
            if not chapter or not chapter['body'].strip():
                raise ApiError('先保存第一章正文。')
            scene = chapter['body']
        else:
            scene = ''
        key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        if not key:
            raise ApiError('未配置 DEEPSEEK_API_KEY。请在左侧设置 DeepSeek Key。')
        route = ROUTES[task]
        if task in ('plan', 'draft', 'draft_pro') and chapters:
            wanted = 1 if task == 'plan' else -1
            chapter = next((ch for ch in chapters if ch['number'] == wanted), None) if wanted == 1 else chapters[-1]
            if chapter:
                loaded = data_store.chapter(novel['id'], chapter['id'])
                chapters = [loaded if ch['id'] == chapter['id'] else ch for ch in chapters]
        pieces = split_text(scene) if task in ('analyze', 'summarize') else [scene]
        if len(pieces) > 16:
            raise ApiError('本章超过 16 个分析片段，请先拆成较短章节。')
        requests = [build_messages(task, novel, chapters, scene=part) for part in pieces]
        ceilings = [request_ceiling(route, messages) for messages in requests]
        if task == 'summarize' and len(pieces) > 1:
            estimate = '\n\n'.join(f'片段{i + 1}：' + 'x' * (route.max_tokens * 4)
                                    for i in range(len(pieces)))
            ceilings.append(request_ceiling(route, build_messages('summarize_merge', novel,
                                                                    chapters, scene=estimate)))
        ceiling = sum(ceilings)
        max_call = float(os.environ.get('MAX_CALL_USD', '0.30'))
        if ceiling > max_call:
            raise ApiError(f'本次共需 {len(ceilings)} 次 Flash/Pro 请求，预估上限 ${ceiling:.4f} '
                           f'超过单次限额 ${max_call:.2f}。可调整本地 MAX_CALL_USD 后重试。')
        try:
            call_id = data_store.reserve_call(novel['id'], task, route.model, ceiling,
                                float(os.environ.get('DAILY_BUDGET_USD', '1.00')))
        except ValueError as exc:
            raise ApiError(str(exc))
        with _activity_lock:
            _activity.update(state='writing', task=task, model=route.model)
        spent = 0.0
        usage = {'prompt_tokens': 0, 'completion_tokens': 0,
                 'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 0}
        outputs = []
        current_ceiling = 0.0
        current_charged = False
        finish_reason = 'stop'
        try:
            def model_call(messages, estimate, *, json_mode=False):
                nonlocal spent, current_ceiling, current_charged, finish_reason
                current_ceiling = estimate
                current_charged = False
                prefix = '\n\n'.join(outputs)
                result = generate(key, os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
                    route, messages, json_output=json_mode,
                    on_progress=lambda text: data_store.save_partial(novel['id'], call_id,
                        prefix + ('\n\n' if prefix else '') + text))
                spent += actual_cost(route, result.usage) if result.usage else estimate
                current_charged = True
                for field in usage:
                    usage[field] += int(result.usage.get(field) or 0)
                finish_reason = result.finish_reason
                if task in ('analyze', 'summarize', 'character_updates') and result.finish_reason == 'length':
                    raise GenerationError('片段输出达到长度上限，未覆盖整章；已停止保存记忆。',
                                          partial=result.content, billed_unknown=False)
                return result.content.strip()

            analyses = []
            for messages, estimate in zip(requests, ceilings):
                content = model_call(messages, estimate, json_mode=(task in ('analyze', 'character_updates')))
                if task == 'analyze':
                    try:
                        parsed = json.loads(content)
                        if not isinstance(parsed, dict) or not isinstance(parsed.get('characters'), list):
                            raise ValueError()
                    except (json.JSONDecodeError, ValueError):
                        raise GenerationError('人物分析没有返回可用 JSON；可从调用记录找回内容。',
                                              partial=content, billed_unknown=False)
                    analyses.append(parsed)
                outputs.append(content)
                data_store.save_partial(novel['id'], call_id, '\n\n'.join(outputs))

            extra_result = {}
            if task == 'character_updates':
                content = outputs[0]
                try:
                    observations = parse_observations(content)
                    proposal = data_store.save_character_proposal(novel['id'], chapter_id,
                        observations, chapter['body_hash'], body_hash(chapter['summary']))
                except (ValueError, TypeError) as exc:
                    raise GenerationError('人物变化未保存：' + str(exc), partial=content,
                                          billed_unknown=False) from exc
                extra_result = {'proposal': proposal, 'bible_hash': body_hash(novel['bible'])}
            elif task == 'analyze':
                content = json.dumps(merge_character_analyses(analyses), ensure_ascii=False, indent=2)
                data_store.update_novel(novel['id'], {'bible': content})
            elif task == 'plan':
                content = outputs[0]
                data_store.update_novel(novel['id'], {'arc_plan': content})
            elif task == 'summarize':
                if len(outputs) > 1:
                    notes = '\n\n'.join(f'片段{i + 1}：\n{value}' for i, value in enumerate(outputs))
                    messages = build_messages('summarize_merge', novel, chapters, scene=notes)
                    content = model_call(messages, ceilings[-1])
                else:
                    content = outputs[0]
                with data_store.lock:
                    latest = data_store.chapter(novel['id'], chapter_id)
                    if not latest or latest['body_hash'] != chapter['body_hash']:
                        raise GenerationError('生成期间正文已修改，记忆未覆盖；结果可在调用记录找回。',
                                              partial=content, billed_unknown=False)
                    data_store.update_chapter(novel['id'], chapter_id, {'summary': content})
            else:
                content = outputs[0]
                data_store.update_novel(novel['id'], {'draft': content})
            data_store.finish_call(novel['id'], call_id, 'complete', spent, usage,
                  '输出达到上限，可能截断' if finish_reason == 'length' else '', content)
            self.send_json({'content': content, 'model': route.model,
                            'cost_usd_estimate': spent, 'finish_reason': finish_reason,
                            'usage': usage, 'requests': len(ceilings), **extra_result})
        except GenerationError as exc:
            amount = spent
            if not current_charged:
                amount += (actual_cost(route, exc.usage) if exc.usage else
                           current_ceiling if exc.billed_unknown else 0)
            partial = '\n\n'.join(outputs + ([exc.partial] if exc.partial else []))
            failed_usage = {field: value + int(exc.usage.get(field) or 0)
                            for field, value in usage.items()}
            data_store.finish_call(novel['id'], call_id, 'stopped', amount, failed_usage,
                                   str(exc), partial)
            raise ApiError(str(exc), 502, partial=partial,
                           cost_usd_estimate=amount, model=route.model)
        except Exception:
            data_store.finish_call(novel['id'], call_id, 'interrupted', ceiling,
                                   note='意外中断，按预留上限占用预算')
            raise
        finally:
            with _activity_lock:
                _activity.update(state='idle', task='', model='')

    def do_GET(self): self.run_request('GET')
    def do_POST(self): self.run_request('POST')
    def do_PUT(self): self.run_request('PUT')
    def do_DELETE(self): self.run_request('DELETE')

    def run_request(self, method):
        try:
            host = self.headers.get('Host', '')
            origin = self.headers.get('Origin', '')
            if host and host.split(':', 1)[0].lower() not in ('127.0.0.1', 'localhost'):
                raise ApiError('只允许本机访问。', 403)
            if origin and urlparse(origin).hostname not in ('127.0.0.1', 'localhost'):
                raise ApiError('请求来源不允许。', 403)
            self.route(method)
        except ApiError as exc:
            self.send_json({'error': str(exc), **exc.extra}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            print(f'[ERROR] {type(exc).__name__}: {exc}')
            try:
                self.send_json({'error': '服务器处理失败，请查看终端日志。'}, 500)
            except (BrokenPipeError, ConnectionResetError):
                pass


def main():
    data_store = store()
    port = int(os.environ.get('PORT', '8765'))
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Character Compass 已启动：http://127.0.0.1:{port}')
    print(f'作品目录：{data_store.root}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止。')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
