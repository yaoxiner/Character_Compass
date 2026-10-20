import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from deepseek_client import GenerationError, generate
from novel_core import (ROUTES, build_messages, merge_character_analyses, repeats,
                        request_ceiling, select_memory, split_text)
from storage import Store


class CoreTests(unittest.TestCase):
    def test_incomplete_sqlite_migration_resumes_without_losing_chapters(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            old = base / 'old.sqlite3'
            with closing(sqlite3.connect(old)) as db:
                db.execute('CREATE TABLE novels (id INTEGER, title TEXT, premise TEXT, opening TEXT, outline TEXT, bible TEXT, arc_plan TEXT, draft TEXT)')
                db.execute('CREATE TABLE chapters (id INTEGER, novel_id INTEGER, number INTEGER, title TEXT, body TEXT, summary TEXT)')
                db.execute('CREATE TABLE calls (id INTEGER, novel_id INTEGER)')
                db.execute('INSERT INTO novels VALUES (1,?,?,?,?,?,?,?)',
                           ('旧作', '设想', '开篇正文', '大纲', '{}', '弧线', '草稿'))
                db.execute('INSERT INTO chapters VALUES (1,1,1,?,?,?)',
                           ('第一章', '旧章节正文', '旧摘要'))
                db.commit()
            partial = Store(base / 'library')
            partial.create_novel('旧作', '设想', 1)
            (partial.folder(1) / 'opening.md').write_text('部分迁移', encoding='utf-8')
            resumed = Store(base / 'library', old)
            novel = resumed.novel_state(1)
            self.assertNotIn('opening', novel)
            self.assertEqual(novel['chapters'][0]['body'], '开篇正文\n\n旧章节正文')
            self.assertTrue((base / 'library' / '.sqlite-migrated.json').exists())
            self.assertTrue(old.exists())
            self.assertEqual(Store(base / 'library').novel_state(1)['chapters'][0]['body'],
                             '开篇正文\n\n旧章节正文')

    def test_model_routes_are_bounded_and_deliberate(self):
        self.assertEqual(ROUTES["analyze"].model, "deepseek-flash")
        self.assertFalse(ROUTES["analyze"].thinking)
        self.assertEqual(ROUTES["plan"].model, "deepseek-v4-pro")
        self.assertTrue(ROUTES["plan"].thinking)
        self.assertFalse(ROUTES["draft_pro"].thinking)
        self.assertLessEqual(max(route.max_tokens for route in ROUTES.values()), 4200)

    def test_memory_uses_summaries_not_entire_manuscript(self):
        chapters = [
            {"id": i, "number": i, "title": f"章节{i}",
             "summary": "林溪发现一封旧信" if i == 1 else f"事件{i}",
             "body": "秘密正文" * 1000}
            for i in range(1, 14)
        ]
        result = select_memory(chapters, "林溪约会时想起旧信", 500)
        self.assertIn("旧信", result)
        self.assertIn("第13章", result)
        self.assertNotIn("秘密正文", result)
        self.assertLessEqual(len(result), 500)

    def test_budget_reservation_blocks_second_call(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Store(Path(folder))
            db.create_novel("测试", "")
            call = db.reserve_call(1, "plan", "deepseek-v4-pro", .08, .10)
            with self.assertRaises(ValueError):
                db.reserve_call(1, "plan", "deepseek-v4-pro", .03, .10)
            db.finish_call(1, call, status="complete", amount=.04)
            self.assertAlmostEqual(db.spend_today(), .04)
            db.reserve_call(1, "draft", "deepseek-flash", .03, .10)

    def test_interrupted_call_keeps_checkpointed_prose(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Store(Path(folder))
            db.create_novel("测试", "")
            call = db.reserve_call(1, "draft", "deepseek-flash", .02, .10)
            db.save_partial(1, call, "她已走到雨中的街口。")
            db.finish_call(1, call, status="interrupted", amount=.02, note="测试中断")
            self.assertEqual(db.get_call(1, call)["partial_text"], "她已走到雨中的街口。")

    def test_repetition_and_whitespace_trip_guard(self):
        self.assertTrue(repeats(" " * 300))
        self.assertTrue(repeats("一段无意义重复文本。" * 80))
        self.assertTrue(repeats("雨后的钟声在街口回荡，没人回答。" * 20))
        self.assertFalse(repeats("她走进书店，看见他站在靠窗的位置。"))

    def test_prompt_contains_author_constraints(self):
        novel = {"title": "雨停之前", "premise": "悬疑恋爱",
                 "outline": "雨夜再会", "bible": '{"characters":[]}', "arc_plan": "关系缓慢靠近"}
        chapters = [{'id': 1, 'number': 1, 'title': '第一章', 'body': '她推开门。', 'summary': ''}]
        messages = build_messages("draft", novel, chapters, scene="第一次约会")
        self.assertIn("第一次约会", messages[1]["content"])
        self.assertIn("关系缓慢靠近", messages[1]["content"])
        self.assertGreater(request_ceiling(ROUTES["draft"], messages), 0)

    def test_long_text_split_preserves_tail_and_skill_evidence(self):
        original = ('第一段。\n' * 4000) + '最后的能力证据。'
        chunks = split_text(original)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 12000 for chunk in chunks))
        self.assertEqual(''.join(chunks), original)
        merged = merge_character_analyses([{'characters': [{'name': '阿岚',
            'traits': ['谨慎'], 'skills': [{'name': '追踪', 'category': '调查',
                                         'level': 2, 'evidence': '找到脚印'}]}]},
            {'characters': [{'name': '阿岚', 'traits': ['果断'],
                             'skills': [{'name': '追踪', 'level': 2}]}]}])
        person = merged['characters'][0]
        self.assertEqual(person['traits'], ['谨慎', '果断'])
        self.assertEqual(person['skills'][0]['evidence'], '找到脚印')

    def test_hundreds_of_chapters_have_small_directory_response(self):
        with tempfile.TemporaryDirectory() as folder:
            library = Store(Path(folder))
            library.create_novel('百万字小说', '')
            for number in range(1, 251):
                library.create_chapter(1, number, f'事件 {number}', '正文' * 2500)
            overview = library.novel_state(1, full=False)
            self.assertEqual(len(overview['chapters']), 250)
            self.assertEqual(sum(ch['body_chars'] for ch in overview['chapters']), 1_250_000)
            self.assertTrue(all('body' not in ch for ch in overview['chapters']))
            self.assertLess(len(json.dumps(overview, ensure_ascii=False)), 100_000)
            self.assertEqual(len(library.chapter(1, 250)['body']), 5000)


class FakeResponse:
    def __init__(self, events):
        self.lines = [("data: " + json.dumps(event, ensure_ascii=False) + "\n").encode() for event in events]
        self.lines.append(b"data: [DONE]\n")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        return iter(self.lines)


class ClientTests(unittest.TestCase):
    def test_stream_collects_visible_text_and_usage(self):
        events = [
            {"choices": [{"delta": {"reasoning_content": "hidden", "content": "她说"}}]},
            {"choices": [{"delta": {"content": "，好久不见。"}, "finish_reason": "stop"}]},
            {"usage": {"prompt_tokens": 20, "completion_tokens": 10}, "choices": []},
        ]
        with patch("deepseek_client.urllib.request.urlopen", return_value=FakeResponse(events)):
            result = generate("test-key", "https://api.deepseek.com", ROUTES["draft"],
                              [{"role": "user", "content": "继续"}])
        self.assertEqual(result.content, "她说，好久不见。")
        self.assertEqual(result.usage["completion_tokens"], 10)

    def test_stream_aborts_repeated_output(self):
        repeated = "人物反复说着同一句没有变化的话。" * 80
        events = [{"choices": [{"delta": {"content": repeated}}]}]
        with patch("deepseek_client.urllib.request.urlopen", return_value=FakeResponse(events)):
            with self.assertRaises(GenerationError) as caught:
                generate("test-key", "https://api.deepseek.com", ROUTES["draft"],
                         [{"role": "user", "content": "继续"}])
        self.assertIn("重复", str(caught.exception))

    def test_stream_checkpoints_during_generation(self):
        text = "有变化的场景描述" * 90
        events = [
            {"choices": [{"delta": {"content": text}}]},
            {"choices": [{"delta": {"content": "。"}, "finish_reason": "stop"}]},
        ]
        snapshots = []
        with patch("deepseek_client.urllib.request.urlopen", return_value=FakeResponse(events)):
            # 这个文本本身重复会被熔断，但持久化快照应在熔断前写入。
            with self.assertRaises(GenerationError):
                generate("test-key", "https://api.deepseek.com", ROUTES["draft"],
                         [{"role": "user", "content": "继续"}], on_progress=snapshots.append)
        self.assertTrue(snapshots)
        self.assertEqual(snapshots[0], text)


if __name__ == "__main__":
    unittest.main()
