"""小说正文保存为 Markdown，设定和调用记录保存为 JSON。"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import hashlib
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8), name='Asia/Shanghai')
FILES = {'outline': 'outline.md', 'bible': 'characters.json',
         'arc_plan': 'arc_plan.md', 'draft': 'draft.md', 'worldbuilding': 'worldbuilding.md',
         'scene_brief': 'scene_brief.md'}


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def now():
    return datetime.now(TZ).isoformat()


def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.saving-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path: Path, data: dict):
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_text(path: Path):
    return path.read_text(encoding='utf-8') if path.exists() else ''


class Store:
    def __init__(self, root: Path, legacy_sqlite: Path | None = None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        if legacy_sqlite and legacy_sqlite.exists() and not (root / '.sqlite-migrated.json').exists():
            self.migrate_sqlite(legacy_sqlite)
        self.migrate_existing_openings()
        self.reconcile_interrupted()

    def folder(self, novel_id: int):
        return self.root / 'novels' / str(novel_id)

    def meta_path(self, novel_id: int):
        return self.folder(novel_id) / 'project.json'

    def meta(self, novel_id: int):
        path = self.meta_path(novel_id)
        return read_json(path) if path.exists() else None

    def list_novels(self):
        with self.lock:
            folder = self.root / 'novels'
            if not folder.exists():
                return []
            items = []
            for path in folder.glob('*/project.json'):
                meta = read_json(path)
                items.append({key: meta[key] for key in ('id', 'title', 'premise', 'updated_at')})
            return sorted(items, key=lambda row: row['updated_at'], reverse=True)

    def novel_state(self, novel_id: int, *, full: bool = True):
        with self.lock:
            meta = self.meta(novel_id)
            if meta is None:
                return None
            base = self.folder(novel_id)
            result = {key: value for key, value in meta.items() if key != 'chapters'}
            result.update({field: read_text(base / file) for field, file in FILES.items()})
            ordered = sorted(meta['chapters'], key=lambda item: item['number'])
            result['chapters'] = [self.chapter(novel_id, row['id']) if full else
                                  self.chapter_brief(novel_id, row) for row in ordered]
            return result

    def chapter_brief(self, novel_id: int, item: dict):
        summary = read_text(self.folder(novel_id) / 'summaries' / f"{item['id']}.md")
        source = item.get('summary_source_hash')
        status = ('missing' if not summary else 'current' if source and
                  source == item.get('body_hash') else 'stale' if source else 'unknown')
        proposal = item.get('character_update')
        sync = 'missing'
        if proposal:
            sync = ('stale' if status != 'current' or proposal['summary_hash'] != body_hash(summary)
                    or proposal['body_hash'] != item.get('body_hash') else 'empty' if not proposal['characters']
                    else 'applied' if len(proposal.get('applied_names', [])) == len(proposal['characters'])
                    else 'partial' if proposal.get('applied_names') else 'pending')
        brief = {key: value for key, value in item.items() if key != 'character_update'}
        return {**brief, 'novel_id': novel_id, 'summary': summary, 'summary_status': status,
                'summary_hash': body_hash(summary),
                'character_sync_status': sync}

    def migrate_existing_openings(self):
        for novel in self.list_novels():
            novel_id = novel['id']
            base = self.folder(novel_id)
            old = base / 'opening.md'
            marker = base / '.opening-migrated.json'
            if old.exists() and not marker.exists():
                self.merge_legacy_opening(novel_id, read_text(old))
            meta = self.meta(novel_id)
            changed = False
            for item in meta['chapters']:
                if 'body_hash' not in item or 'body_chars' not in item:
                    body = read_text(base / 'chapters' / f"{item['id']}.md")
                    item['body_hash'] = body_hash(body)
                    item['body_chars'] = len(body)
                    changed = True
            if changed:
                write_json(self.meta_path(novel_id), meta)

    def merge_legacy_opening(self, novel_id: int, opening: str):
        """把旧开篇放入第一章；旧文件仍保留，迁移可重复执行。"""
        with self.lock:
            base = self.folder(novel_id)
            marker = base / '.opening-migrated.json'
            if opening.strip():
                meta = self.meta(novel_id)
                first = next((row for row in meta['chapters'] if row['number'] == 1), None)
                if first is None:
                    self.create_chapter(novel_id, 1, '第一章', opening)
                else:
                    current = self.chapter(novel_id, first['id'])['body']
                    if not current.startswith(opening):
                        merged = opening + ('\n\n' + current if current.strip() else '')
                        self.update_chapter(novel_id, first['id'], {'body': merged})
            write_json(marker, {'migrated_at': now()})

    def create_novel(self, title: str, premise: str, novel_id: int | None = None):
        with self.lock:
            if novel_id is None:
                ids = [row['id'] for row in self.list_novels()]
                novel_id = max(ids, default=0) + 1
            if self.meta(novel_id):
                raise ValueError('小说编号已存在。')
            stamp = now()
            write_json(self.meta_path(novel_id), {'id': novel_id, 'title': title, 'premise': premise,
                       'chapters': [], 'created_at': stamp, 'updated_at': stamp})
            return self.novel_state(novel_id, full=False)

    def update_novel(self, novel_id: int, changes: dict):
        with self.lock:
            meta = self.meta(novel_id)
            if meta is None:
                raise KeyError(novel_id)
            for key, value in changes.items():
                if key in FILES:
                    write_text(self.folder(novel_id) / FILES[key], value)
                elif key in ('title', 'premise'):
                    meta[key] = value
            meta['updated_at'] = now()
            write_json(self.meta_path(novel_id), meta)
            return self.novel_state(novel_id, full=False)

    def chapter(self, novel_id: int, chapter_id: int):
        meta = self.meta(novel_id)
        item = next((row for row in meta['chapters'] if row['id'] == chapter_id), None) if meta else None
        if item is None:
            return None
        base = self.folder(novel_id)
        body = read_text(base / 'chapters' / f'{chapter_id}.md')
        result = self.chapter_brief(novel_id, item)
        result['body'] = body
        result['character_update'] = item.get('character_update')
        if result['summary_status'] == 'unknown' and item.get('summary_source_hash'):
            result['summary_status'] = ('current' if item['summary_source_hash'] ==
                                        body_hash(body) else 'stale')
        return result

    def create_chapter(self, novel_id: int, number: int, title: str, body: str,
                       summary: str = '', chapter_id: int | None = None):
        with self.lock:
            meta = self.meta(novel_id)
            if meta is None:
                raise KeyError(novel_id)
            if any(item['number'] == number for item in meta['chapters']):
                raise ValueError('该章节序号已存在。')
            if chapter_id is None:
                chapter_id = max((item['id'] for item in meta['chapters']), default=0) + 1
            base = self.folder(novel_id)
            write_text(base / 'chapters' / f'{chapter_id}.md', body)
            write_text(base / 'summaries' / f'{chapter_id}.md', summary)
            digest = body_hash(body)
            item = {'id': chapter_id, 'number': number, 'title': title,
                    'body_hash': digest, 'body_chars': len(body), 'updated_at': now()}
            if summary:
                item['summary_source_hash'] = digest
            meta['chapters'].append(item)
            meta['updated_at'] = item['updated_at']
            write_json(self.meta_path(novel_id), meta)
            return self.chapter(novel_id, chapter_id)

    def save_character_proposal(self, novel_id, chapter_id, observations, source_hash, summary_hash):
        with self.lock:
            chapter = self.chapter(novel_id, chapter_id)
            if (not chapter or chapter['body_hash'] != source_hash or body_hash(chapter['summary']) != summary_hash
                    or chapter['summary_status'] != 'current'):
                raise ValueError('正文或章节记忆已修改，请重新提取人物变化。')
            meta = self.meta(novel_id)
            item = next(row for row in meta['chapters'] if row['id'] == chapter_id)
            proposal = {'body_hash': source_hash, 'summary_hash': summary_hash,
                        'characters': observations, 'applied_names': [], 'created_at': now()}
            proposal['id'] = body_hash(json.dumps(proposal, ensure_ascii=False, sort_keys=True))
            item['character_update'] = proposal
            write_json(self.meta_path(novel_id), meta)
            return proposal

    def restore_chapter_memory(self, novel_id, chapter_id, memory):
        """导入备份时保留摘要来源与已缓存的核对结果。"""
        with self.lock:
            meta = self.meta(novel_id)
            item = next(row for row in meta['chapters'] if row['id'] == chapter_id)
            for key in ('summary_source_hash', 'character_update'):
                if key in memory:
                    item[key] = memory[key]
            write_json(self.meta_path(novel_id), meta)

    def apply_character_proposal(self, novel_id, chapter_id, proposal_id, names, bible_hash):
        from character_memory import merge_observations
        with self.lock:
            chapter = self.chapter(novel_id, chapter_id)
            if not chapter:
                raise ValueError('章节不存在。')
            proposal = chapter.get('character_update')
            if not proposal or proposal['id'] != proposal_id:
                raise ValueError('人物变化已更新，请重新打开预览。')
            if chapter['character_sync_status'] == 'stale':
                raise ValueError('正文或记忆已修改，请重新提取记忆和人物变化。')
            text = read_text(self.folder(novel_id) / FILES['bible'])
            if body_hash(text) != bible_hash:
                raise ValueError('人物档案已修改，请重新打开预览后确认。')
            available = {p['name'] for p in proposal['characters']}
            if not names or not set(names).issubset(available):
                raise ValueError('请选择本次提取到的人物。')
            try:
                bible = json.loads(text) if text.strip() else {'characters': []}
                merged = merge_observations(bible,
                    [p for p in proposal['characters'] if p['name'] in names], chapter)
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError('人物档案格式有误，请先修正 JSON：' + str(exc)) from exc
            updated = json.dumps(merged, ensure_ascii=False, indent=2)
            # 先保存档案，再标记状态；即使中断，重复确认也不会重复追加同章记录。
            self.update_novel(novel_id, {'bible': updated})
            meta = self.meta(novel_id)
            item = next(row for row in meta['chapters'] if row['id'] == chapter_id)
            item['character_update']['applied_names'] = sorted(set(proposal['applied_names']) | set(names))
            write_json(self.meta_path(novel_id), meta)
            return {'bible': updated, 'chapter': self.chapter(novel_id, chapter_id)}

    def update_chapter(self, novel_id: int, chapter_id: int, changes: dict):
        with self.lock:
            meta = self.meta(novel_id)
            item = next((row for row in meta['chapters'] if row['id'] == chapter_id), None) if meta else None
            if item is None:
                raise KeyError(chapter_id)
            if 'number' in changes and any(row['number'] == changes['number'] and
                                           row['id'] != chapter_id for row in meta['chapters']):
                raise ValueError('该章节序号已存在。')
            base = self.folder(novel_id)
            if 'body' in changes:
                write_text(base / 'chapters' / f'{chapter_id}.md', changes['body'])
                item['body_hash'] = body_hash(changes['body'])
                item['body_chars'] = len(changes['body'])
            if 'summary' in changes:
                write_text(base / 'summaries' / f'{chapter_id}.md', changes['summary'])
                item['summary_source_hash'] = item.get('body_hash') if changes['summary'] else None
            if 'title' in changes:
                item['title'] = changes['title']
            if 'number' in changes:
                item['number'] = changes['number']
            item['updated_at'] = meta['updated_at'] = now()
            write_json(self.meta_path(novel_id), meta)
            return self.chapter(novel_id, chapter_id)

    def delete_chapter(self, novel_id: int, chapter_id: int):
        with self.lock:
            meta = self.meta(novel_id)
            if meta is None or not any(row['id'] == chapter_id for row in meta['chapters']):
                raise KeyError(chapter_id)
            meta['chapters'] = [row for row in meta['chapters'] if row['id'] != chapter_id]
            meta['updated_at'] = now()
            write_json(self.meta_path(novel_id), meta)
            for folder in ('chapters', 'summaries'):
                (self.folder(novel_id) / folder / f'{chapter_id}.md').unlink(missing_ok=True)

    def call_path(self, novel_id: int, call_id: int):
        return self.folder(novel_id) / 'calls' / f'{call_id}.json'

    def get_call(self, novel_id: int, call_id: int):
        path = self.call_path(novel_id, call_id)
        return read_json(path) if path.exists() else None

    def calls(self, novel_id: int):
        folder = self.folder(novel_id) / 'calls'
        return [read_json(path) for path in folder.glob('*.json')] if folder.exists() else []

    def list_calls(self, novel_id: int):
        with self.lock:
            result = []
            for call in sorted(self.calls(novel_id), key=lambda row: row['id'], reverse=True)[:30]:
                record = {key: value for key, value in call.items() if key != 'partial_text'}
                record['partial_chars'] = len(call.get('partial_text', ''))
                result.append(record)
            return result

    def spend_today(self):
        with self.lock:
            day = datetime.now(TZ).date().isoformat()
            return sum(float(call['charged_usd']) for novel in self.list_novels()
                       for call in self.calls(novel['id']) if call['created_at'][:10] == day)

    def reserve_call(self, novel_id: int, task: str, model: str, ceiling: float, daily_budget: float):
        with self.lock:
            used = self.spend_today()
            if used + ceiling > daily_budget + 1e-9:
                raise ValueError(f'今日预算不足：已占用 ${used:.4f}，本次最多约 ${ceiling:.4f}，上限 ${daily_budget:.2f}。')
            call_id = max((call['id'] for call in self.calls(novel_id)), default=0) + 1
            write_json(self.call_path(novel_id, call_id), {
                'id': call_id, 'novel_id': novel_id, 'task': task, 'model': model,
                'status': 'running', 'reserved_usd': ceiling, 'charged_usd': ceiling,
                'input_tokens': 0, 'output_tokens': 0, 'created_at': now(),
                'note': '', 'partial_text': ''})
            return call_id

    def save_partial(self, novel_id: int, call_id: int, content: str):
        with self.lock:
            call = self.get_call(novel_id, call_id)
            if call and call['status'] == 'running':
                call['partial_text'] = content[:26000]
                write_json(self.call_path(novel_id, call_id), call)

    def finish_call(self, novel_id: int, call_id: int, status: str, amount: float,
                    usage: dict | None = None, note: str = '', partial: str | None = None):
        with self.lock:
            call = self.get_call(novel_id, call_id)
            if call is None:
                raise KeyError(call_id)
            usage = usage or {}
            call.update(status=status, charged_usd=amount,
                        input_tokens=int(usage.get('prompt_tokens') or 0),
                        output_tokens=int(usage.get('completion_tokens') or 0), note=note[:300])
            if partial is not None:
                call['partial_text'] = partial[:26000]
            write_json(self.call_path(novel_id, call_id), call)

    def reconcile_interrupted(self):
        with self.lock:
            for novel in self.list_novels():
                for call in self.calls(novel['id']):
                    if call['status'] == 'running':
                        call['status'] = 'interrupted'
                        call['note'] = '服务重启，按预留上限占用预算'
                        write_json(self.call_path(novel['id'], call['id']), call)

    def migrate_sqlite(self, source: Path):
        """迁移旧版本已有内容，原数据库原样保留作为备份。"""
        with self.lock, closing(sqlite3.connect(source)) as db:
            db.row_factory = sqlite3.Row
            novels = [dict(row) for row in db.execute('SELECT * FROM novels ORDER BY id')]
            for old in novels:
                existing = self.meta(old['id'])
                if existing and existing['title'] != old['title']:
                    raise RuntimeError(f'旧数据迁移与小说编号 {old["id"]} 冲突；原数据库仍保留。')
                if not existing:
                    self.create_novel(old['title'], old.get('premise') or '', old['id'])
                else:
                    self.update_novel(old['id'], {'premise': old.get('premise') or ''})
                self.update_novel(old['id'], {key: old.get(key) or '' for key in FILES})
                for row in db.execute('SELECT * FROM chapters WHERE novel_id=? ORDER BY number', (old['id'],)):
                    chapter = dict(row)
                    if self.chapter(old['id'], chapter['id']):
                        self.update_chapter(old['id'], chapter['id'], {key: chapter[key]
                             for key in ('title', 'body', 'summary')})
                    else:
                        self.create_chapter(old['id'], chapter['number'], chapter['title'],
                                            chapter['body'], chapter['summary'], chapter['id'])
                self.merge_legacy_opening(old['id'], old.get('opening') or '')
                for row in db.execute('SELECT * FROM calls WHERE novel_id=? ORDER BY id', (old['id'],)):
                    call = dict(row)
                    call.setdefault('partial_text', '')
                    write_json(self.call_path(old['id'], call['id']), call)
            write_json(self.root / '.sqlite-migrated.json', {
                'source': str(source), 'migrated_at': now(), 'novel_count': len(novels)})
