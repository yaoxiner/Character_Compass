import json
import unittest

from character_memory import merge_observations, parse_observations
from novel_core import build_messages


class CharacterMemoryTests(unittest.TestCase):
    def test_world_rules_constrain_both_draft_models_and_planning(self):
        # 约束不截断后半段，避免末尾禁忌悄悄丢失。
        world = '设定' * 6000 + '禁止复活；施法消耗记忆。'
        for task in ('draft', 'draft_pro', 'plan'):
            messages = build_messages(task, {'title': '世界', 'worldbuilding': world}, [], scene='约会')
            self.assertIn(world, messages[-1]['content'])
            self.assertIn('世界观设定', messages[0]['content'])

    def test_saved_facts_characters_world_constrain_writing_but_outline_stays_private(self):
        novel = {'title': '约束', 'worldbuilding': '禁止复活', 'outline': '两人最终和解',
                 'bible': '{"characters":[{"name":"阿岚","traits":["谨慎"]}]}'}
        chapters = [{'id': 1, 'number': 1, 'title': '真相', 'summary': '阿岚已经得知真相。',
                     'summary_status': 'current'}, {'id': 2, 'number': 2, 'title': '旧稿',
                     'summary': '不应再使用的旧事实', 'summary_status': 'stale'}]
        for task in ('draft', 'draft_pro', 'plan'):
            messages = build_messages(task, novel, chapters, scene='约会')
            user = messages[-1]['content']
            for value in ('禁止复活', '谨慎', '阿岚已经得知真相'):
                self.assertIn(value, user)
            self.assertNotIn('两人最终和解', str(messages))
            self.assertNotIn('不应再使用的旧事实', user)
            self.assertIn('未来', messages[0]['content'])
        for task in ('draft', 'draft_pro'):
            messages = build_messages(task, novel, chapters, scene='本章在书店约会后发现信件')
            self.assertIn('本章在书店约会后发现信件', messages[-1]['content'])
            self.assertIn('直接任务', messages[0]['content'])

    def test_backfilling_old_chapter_keeps_later_skill_level(self):
        bible = {'characters': [{'name': '阿岚', 'traits': ['谨慎'],
            'skills': [{'name': '剑术', 'level': 4, 'source_chapter': 10}], 'custom': '保留'}]}
        observation = {'name': '阿岚', 'traits': ['初次尝试'], 'evidence': ['第一次拔剑'],
            'skills': [{'name': '剑术', 'level': 1, 'category': '战斗', 'evidence': '初次拔剑'}]}
        chapter = {'id': 2, 'number': 2, 'title': '起点', 'body_hash': 'hash', 'summary': '初次拔剑'}
        merged = merge_observations(bible, [observation], chapter)
        person = merged['characters'][0]
        self.assertEqual(person['skills'][0]['level'], 4)
        self.assertEqual(person['chapter_history'][0]['observations']['skills'][0]['level'], 1)
        self.assertNotIn('chapter_history', bible['characters'][0])
        self.assertEqual(person['traits'], ['谨慎'])

    def test_observations_require_evidence_and_valid_skill_levels(self):
        for row in [{'name': '阿岚'}, {'name': '阿岚', 'evidence': ['救人'],
                     'skills': [{'name': '剑术', 'level': 8, 'evidence': '救人'}]}]:
            with self.assertRaises(ValueError):
                parse_observations(json.dumps({'characters': [row]}, ensure_ascii=False))
        self.assertEqual(parse_observations('{"characters": []}'), [])

    def test_writing_context_uses_recent_character_history_without_sending_all_history(self):
        history = [{'chapter_number': i, 'observations': {'evidence': [f'事件-{i}-标记']}}
                   for i in range(1, 301)]
        novel = {'title': '长篇', 'bible': json.dumps({'characters': [
            {'name': '阿岚', 'traits': ['谨慎'], 'chapter_history': history}]}, ensure_ascii=False)}
        prompt = str(build_messages('draft', novel, [], scene='阿岚约会'))
        self.assertIn('事件-300-标记', prompt)
        self.assertNotIn('事件-1-标记', prompt)
        self.assertIn('谨慎', prompt)
