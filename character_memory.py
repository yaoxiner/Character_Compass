"""章节观察合入人物档案；基础设定保留，变化按章留痕。"""
import copy
import json
from hashlib import sha256

from novel_core import merge_character_analyses


def parse_observations(content):
    value = json.loads(content)
    rows = value.get('characters') if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) > 12:
        raise ValueError('人物变化必须是 characters 数组，最多 12 人。')
    names = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str):
            raise ValueError('人物变化缺少姓名。')
        name = row['name'].strip()
        if not name or name in names or len(name) > 100:
            raise ValueError('人物姓名为空、重复或过长。')
        names.add(name)
        for field in ('traits', 'evidence', 'relationships', 'uncertain'):
            values = row.get(field, [])
            if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
                raise ValueError('人物观察字段应为文本数组。')
        for field in ('desire', 'fear', 'voice'):
            if not isinstance(row.get(field, ''), str):
                raise ValueError('人物目标、顾虑与说话方式应为文本。')
        if not any(x.strip() for x in row.get('evidence', [])):
            raise ValueError('每个人物变化都需要章节记忆依据。')
        skills = row.get('skills', [])
        if not isinstance(skills, list) or any(not isinstance(x, dict) or
                not isinstance(x.get('name'), str) or not isinstance(x.get('evidence'), str)
                or not x['evidence'].strip() or type(x.get('level')) is not int or
                not 1 <= x['level'] <= 5 for x in skills):
            raise ValueError('技能变化需要名称、1—5 级和章节依据。')
    return merge_character_analyses([value])['characters']


def merge_observations(bible, observations, chapter):
    """确认后调用。重复确认替换同章记录；补旧章不会回退新章技能。"""
    result = copy.deepcopy(bible)
    if not isinstance(result, dict) or not isinstance(result.get('characters', []), list):
        raise ValueError('人物档案需要是包含 characters 数组的 JSON。')
    characters = result.setdefault('characters', [])
    if any(not isinstance(p, dict) for p in characters):
        raise ValueError('人物档案中有无效的人物。')
    for observation in observations:
        person = next((p for p in characters if p.get('name') == observation['name']), None)
        if person is None:
            person = copy.deepcopy(observation)
            person['skills'] = []
            characters.append(person)
        history = person.setdefault('chapter_history', [])
        if not isinstance(history, list) or not isinstance(person.setdefault('skills', []), list):
            raise ValueError('人物的 skills 和 chapter_history 需要是数组。')
        history[:] = [h for h in history if h.get('chapter_id') != chapter['id']]
        history.append({'chapter_id': chapter['id'], 'chapter_number': chapter['number'],
                        'chapter_title': chapter['title'],
                        'source_hash': chapter['body_hash'],
                        'summary_hash': sha256(chapter['summary'].encode('utf-8')).hexdigest(),
                        'observations': copy.deepcopy(observation)})
        history.sort(key=lambda h: h.get('chapter_number', 0))
        for found in observation['skills']:
            skill = next((s for s in person['skills'] if s.get('name') == found['name']), None)
            update = {**found, 'source_chapter': chapter['number']}
            if skill is None:
                person['skills'].append(update)
            elif skill.get('source_chapter', 0) <= chapter['number']:
                skill.update(update)
    return result
