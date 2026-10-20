import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import Handler
from deepseek_client import GenerationError, GenerationResult
from storage import Store
from storage import body_hash


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch("app._store", Store(Path(self.temp.name) / "library"))
        self.key_patch = patch.dict("app.os.environ", {"DEEPSEEK_API_KEY": ""})
        self.path_patch.start(); self.key_patch.start()

    def tearDown(self):
        self.key_patch.stop(); self.path_patch.stop(); self.temp.cleanup()

    def request(self, path, method="GET", body=None):
        payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
        handler = object.__new__(Handler)
        handler.path = path
        handler.headers = {"Content-Length": str(len(payload))}
        handler.rfile = io.BytesIO(payload)
        handler.wfile = io.BytesIO()
        handler.send_response = lambda status: setattr(handler, "status", status)
        handler.send_header = lambda *_: None
        handler.end_headers = lambda: None
        handler.run_request(method)
        return handler.status, json.loads(handler.wfile.getvalue())

    def test_author_text_round_trip_and_backup_restore(self):
        status, novel = self.request("/api/novels", "POST", {"title": "雨停之前", "premise": "一段关系"})
        self.assertEqual(status, 201)
        novel_id = novel["id"]
        status, _ = self.request(f"/api/novels/{novel_id}", "PUT", {
            "outline": "两人约会，后来决裂。",
            "worldbuilding": "能力消耗记忆，不能复活死者。",
            "scene_brief": "本章两人在书店约会，最后发现匿名信。",
            "bible": "人物设定", "arc_plan": "缓慢变化", "draft": "待审草稿",
        })
        self.assertEqual(status, 200)
        status, chapter = self.request(f"/api/novels/{novel_id}/chapters", "POST",
                                      {"number": 1, "title": "第一章", "body": "正文原样保留。"})
        self.assertEqual(status, 201)
        status, backup = self.request(f"/api/novels/{novel_id}/export")
        self.assertEqual(backup["novel"]["chapters"][0]["body"], "正文原样保留。")
        status, restored = self.request("/api/novels/import", "POST", backup)
        self.assertEqual(status, 201)
        self.assertNotEqual(restored["id"], novel_id)
        self.assertEqual(restored["draft"], "待审草稿")
        self.assertEqual(restored['worldbuilding'], '能力消耗记忆，不能复活死者。')
        self.assertEqual(restored['scene_brief'], '本章两人在书店约会，最后发现匿名信。')
        _, restored_chapter = self.request(f"/api/novels/{restored['id']}/chapters/{restored['chapters'][0]['id']}")
        self.assertEqual(restored_chapter["body"], "正文原样保留。")

    def test_generation_requires_key_without_spending(self):
        _, novel = self.request("/api/novels", "POST", {"title": "测试"})
        self.request(f"/api/novels/{novel['id']}/chapters", "POST",
                     {"number": 1, "title": "第一章", "body": "他坐下。"})
        status, error = self.request(f"/api/novels/{novel['id']}/generate", "POST", {"task": "analyze"})
        self.assertEqual(status, 400)
        self.assertIn("DEEPSEEK_API_KEY", error["error"])
        _, calls = self.request(f"/api/novels/{novel['id']}/calls")
        self.assertEqual(calls, [])

    def test_interrupted_generation_keeps_partial_in_ledger(self):
        _, novel = self.request("/api/novels", "POST", {"title": "测试"})
        self.request(f"/api/novels/{novel['id']}/chapters", "POST",
                     {"number": 1, "title": "第一章", "body": "他坐下。"})

        def fake_generate(*_, on_progress, **__):
            partial = "他在街角停住。" * 80
            on_progress(partial)
            raise GenerationError("检测到重复输出", partial=partial)

        with patch.dict("app.os.environ", {"DEEPSEEK_API_KEY": "test-key"}), \
             patch("app.generate", side_effect=fake_generate):
            status, error = self.request(f"/api/novels/{novel['id']}/generate", "POST",
                                         {"task": "analyze"})
        self.assertEqual(status, 502)
        self.assertIn("重复", error["error"])
        _, calls = self.request(f"/api/novels/{novel['id']}/calls")
        self.assertEqual(calls[0]["status"], "stopped")
        self.assertGreater(calls[0]["partial_chars"], 500)
        _, call = self.request(f"/api/novels/{novel['id']}/calls/{calls[0]['id']}")
        self.assertEqual(call["partial_text"], error["partial"])

    def test_analysis_saves_character_evidence(self):
        _, novel = self.request("/api/novels", "POST", {"title": "测试"})
        self.request(f"/api/novels/{novel['id']}/chapters", "POST",
                     {"number": 1, "title": "第一章", "body": "阿岚把最后一块面包留给了弟弟。"})
        content = json.dumps({"characters": [{"name": "阿岚", "traits": ["体贴"],
                   "evidence": ["把最后一块面包留给了弟弟"]}]}, ensure_ascii=False)
        fake_result = GenerationResult(content, {"prompt_tokens": 120, "completion_tokens": 80,
                                                "prompt_cache_hit_tokens": 0}, "stop")
        with patch.dict("app.os.environ", {"DEEPSEEK_API_KEY": "test-key"}), \
             patch("app.generate", return_value=fake_result) as mocked:
            status, response = self.request(f"/api/novels/{novel['id']}/generate", "POST",
                                            {"task": "analyze"})
        self.assertEqual(status, 200)
        self.assertEqual(mocked.call_args.args[2].model, "deepseek-flash")
        self.assertIn("阿岚", response["content"])
        _, saved = self.request(f"/api/novels/{novel['id']}")
        self.assertEqual(json.loads(saved["bible"])["characters"][0]["name"], "阿岚")

    def test_long_chapter_is_loaded_on_demand_and_fully_summarized(self):
        _, novel = self.request('/api/novels', 'POST', {'title': '长篇'})
        body = '甲' * 12500 + '\n' + '乙' * 12500 + '\n末段发生了结局。'
        _, chapter = self.request(f"/api/novels/{novel['id']}/chapters", 'POST',
                                  {'number': 1, 'title': '漫长的一天', 'body': body})
        _, overview = self.request(f"/api/novels/{novel['id']}")
        self.assertNotIn('body', overview['chapters'][0])
        self.assertEqual(overview['chapters'][0]['body_chars'], len(body))
        _, loaded = self.request(f"/api/novels/{novel['id']}/chapters/{chapter['id']}")
        self.assertEqual(loaded['body'], body)

        messages_seen = []
        def fake_generate(_key, _url, _route, messages, **_kwargs):
            messages_seen.append(messages[-1]['content'])
            return GenerationResult(f'第 {len(messages_seen)} 段记录。',
                                    {'prompt_tokens': 100, 'completion_tokens': 30}, 'stop')

        with patch.dict('app.os.environ', {'DEEPSEEK_API_KEY': 'test-key'}), \
             patch('app.generate', side_effect=fake_generate):
            status, result = self.request(f"/api/novels/{novel['id']}/generate", 'POST',
                                          {'task': 'summarize', 'chapter_id': chapter['id']})
        self.assertEqual(status, 200)
        self.assertEqual(result['requests'], 4)
        self.assertIn('末段发生了结局', messages_seen[2])
        self.assertIn('片段记录', messages_seen[3])
        _, loaded = self.request(f"/api/novels/{novel['id']}/chapters/{chapter['id']}")
        self.assertEqual(loaded['summary_status'], 'current')
        self.request(f"/api/novels/{novel['id']}/chapters/{chapter['id']}", 'PUT',
                     {'body': body + '尾声。'})
        _, changed = self.request(f"/api/novels/{novel['id']}/chapters/{chapter['id']}")
        self.assertEqual(changed['summary_status'], 'stale')

    def test_legacy_backup_opening_is_merged_into_chapter_one(self):
        _, restored = self.request('/api/novels/import', 'POST', {
            'format': 'character-compass-v1', 'novel': {'title': '旧作', 'premise': '',
            'opening': '旧开篇。', 'chapters': [{'number': 1, 'title': '第一章',
                                             'body': '旧章节后半。', 'summary': ''}]},
        })
        _, chapter = self.request(f"/api/novels/{restored['id']}/chapters/{restored['chapters'][0]['id']}")
        self.assertEqual(chapter['body'], '旧开篇。\n\n旧章节后半。')

    def test_character_update_is_reviewed_cached_and_preserves_author_settings(self):
        _, novel = self.request('/api/novels', 'POST', {'title': '人物成长'})
        prefix = f"/api/novels/{novel['id']}"
        original = json.dumps({'characters': [{'name': '阿岚', 'traits': ['谨慎'],
            'desire': '找回家人', 'author_note': '作者设定',
            'skills': [{'name': '剑术', 'level': 1, 'evidence': '第一章'}]}]}, ensure_ascii=False)
        self.request(prefix, 'PUT', {'bible': original})
        _, chapter = self.request(prefix + '/chapters', 'POST',
                                  {'number': 2, 'title': '保护同伴', 'body': '正文独有标记，绝不上传到人物记忆任务。'})
        chapter_path = prefix + f"/chapters/{chapter['id']}"
        self.request(chapter_path, 'PUT', {'summary': '阿岚挺身保护同伴，熟练用剑挡住进攻。'})
        observation = {'name': '阿岚', 'traits': ['敢于承担风险'], 'desire': '保护同伴',
            'evidence': ['挺身保护同伴'], 'relationships': ['更加信任同伴'],
            'skills': [{'name': '剑术', 'category': '战斗', 'level': 3, 'evidence': '用剑挡住进攻'}]}
        fake = GenerationResult(json.dumps({'characters': [observation]}, ensure_ascii=False),
                                {'prompt_tokens': 100, 'completion_tokens': 80}, 'stop')
        with patch.dict('app.os.environ', {'DEEPSEEK_API_KEY': 'test-key'}), patch('app.generate', return_value=fake) as mocked:
            status, preview = self.request(prefix + '/generate', 'POST', {'task': 'character_updates', 'chapter_id': chapter['id']})
            self.assertEqual(status, 200, preview)
            self.assertEqual(mocked.call_args.args[2].model, 'deepseek-flash')
            self.assertTrue(mocked.call_args.kwargs['json_output'])
            self.assertNotIn('正文独有标记', str(mocked.call_args.args[3]))
            _, repeated = self.request(prefix + '/generate', 'POST', {'task': 'character_updates', 'chapter_id': chapter['id']})
            self.assertTrue(repeated['cached'])
            self.assertEqual(repeated['requests'], 0)
            self.assertEqual(mocked.call_count, 1)
        _, unchanged = self.request(prefix)
        self.assertEqual(unchanged['bible'], original)
        payload = {'names': ['阿岚'], 'proposal_id': preview['proposal']['id'], 'bible_hash': preview['bible_hash']}
        status, applied = self.request(chapter_path + '/characters', 'PUT', payload)
        self.assertEqual(status, 200, applied)
        person = json.loads(applied['bible'])['characters'][0]
        self.assertEqual(person['traits'], ['谨慎'])
        self.assertEqual(person['desire'], '找回家人')
        self.assertEqual(person['author_note'], '作者设定')
        self.assertEqual(person['skills'][0]['level'], 3)
        self.assertEqual(person['chapter_history'][0]['observations']['traits'], ['敢于承担风险'])
        self.assertEqual(applied['chapter']['character_sync_status'], 'applied')
        payload['bible_hash'] = body_hash(applied['bible'])
        status, again = self.request(chapter_path + '/characters', 'PUT', payload)
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(again['bible'])['characters'][0]['chapter_history']), 1)
        _, backup = self.request(prefix + '/export')
        _, restored = self.request('/api/novels/import', 'POST', backup)
        self.assertEqual(restored['chapters'][0]['character_sync_status'], 'applied')
        self.assertEqual(restored['bible'], again['bible'])
        self.request(chapter_path, 'PUT', {'summary': '作者纠正了事件。'})
        status, rejected = self.request(chapter_path + '/characters', 'PUT', payload)
        self.assertEqual(status, 409)
        self.assertIn('记忆已修改', rejected['error'])

    def test_stale_summary_and_concurrent_bible_edits_are_not_overwritten(self):
        _, novel = self.request('/api/novels', 'POST', {'title': '版本检查'})
        prefix = f"/api/novels/{novel['id']}"
        _, chapter = self.request(prefix + '/chapters', 'POST', {'number': 1, 'body': '阿岚救人。'})
        path = prefix + f"/chapters/{chapter['id']}"
        self.request(path, 'PUT', {'summary': '阿岚救人。'})
        from app import store
        proposal = store().save_character_proposal(novel['id'], chapter['id'],
            [{'name': '阿岚', 'evidence': ['救人'], 'skills': []}], chapter['body_hash'], body_hash('阿岚救人。'))
        self.request(prefix, 'PUT', {'bible': '{"characters": [], "note": "新修改"}'})
        status, error = self.request(path + '/characters', 'PUT',
            {'names': ['阿岚'], 'proposal_id': proposal['id'], 'bible_hash': body_hash('')})
        self.assertEqual(status, 409)
        self.assertIn('人物档案已修改', error['error'])
        self.request(path, 'PUT', {'body': '实际没有救人。'})
        with patch('app.generate') as mocked:
            status, error = self.request(prefix + '/generate', 'POST', {'task': 'character_updates', 'chapter_id': chapter['id']})
            self.assertEqual(status, 400)
            mocked.assert_not_called()
        _, backup = self.request(prefix + '/export')
        _, restored = self.request('/api/novels/import', 'POST', backup)
        self.assertEqual(restored['chapters'][0]['summary_status'], 'stale')

    def test_local_key_setting_and_balance_do_not_reveal_secret(self):
        secret = 'sk-local-test-key'
        env_file = Path(self.temp.name) / '.env'
        fake_balance = io.BytesIO(json.dumps({'is_available': True, 'balance_infos': [
            {'currency': 'CNY', 'total_balance': '12.34', 'granted_balance': '2.34',
             'topped_up_balance': '10.00'}]}).encode())
        with patch.dict('app.os.environ', {'CHARACTER_COMPASS_ENV_FILE': str(env_file)}), \
             patch('app.urllib.request.urlopen', return_value=fake_balance) as urlopen:
            status, saved = self.request('/api/config/key', 'POST', {'key': secret})
            self.assertEqual(status, 200)
            self.assertEqual(saved, {'key_configured': True})
            status, result = self.request('/api/balance')
            self.assertEqual(status, 200)
            self.assertEqual(result['balance_infos'][0]['total_balance'], '12.34')
            self.assertNotIn(secret, json.dumps(result))
            self.assertIn(secret, urlopen.call_args.args[0].get_header('Authorization'))
        self.assertIn(secret, env_file.read_text())


if __name__ == "__main__":
    unittest.main()
