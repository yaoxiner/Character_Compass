"""长篇小说上下文、预算和模型路由；不依赖第三方包。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


MODEL_FLASH = "deepseek-flash"
MODEL_PRO = "deepseek-v4-pro"

# 按官方峰时价格预估（USD / 百万 token）；实际账单以 DeepSeek 为准。
PEAK_PRICES = {
    MODEL_FLASH: {"input": 0.30, "output": 1.20},
    MODEL_PRO: {"input": 1.32, "output": 3.96},
}


@dataclass(frozen=True)
class Route:
    model: str
    thinking: bool
    max_tokens: int
    effort: str | None = None


ROUTES = {
    "analyze": Route(MODEL_FLASH, False, 2600),
    "plan": Route(MODEL_PRO, True, 4200, "low"),
    "draft": Route(MODEL_FLASH, False, 3600),
    "draft_pro": Route(MODEL_PRO, False, 3600),
    "summarize": Route(MODEL_FLASH, False, 1800),
    "character_updates": Route(MODEL_FLASH, False, 2600),
}


def split_text(text: str, limit: int = 12000) -> list[str]:
    """在段落边界拆分长章；每个字符恰好进入一个片段。"""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            newline = text.rfind('\n', start + limit // 2, end)
            if newline > start:
                end = newline + 1
        chunks.append(text[start:end])
        start = end
    return chunks


def merge_character_analyses(parts: list[dict]) -> dict:
    """按角色姓名合并定长片段的观察，不再调用模型做无限迭代。"""
    characters = {}
    questions = []
    for part in parts:
        for question in part.get('open_questions') or []:
            if isinstance(question, str) and question not in questions:
                questions.append(question)
        for found in part.get('characters') or []:
            if not isinstance(found, dict) or not isinstance(found.get('name'), str):
                continue
            name = found['name'].strip()
            if not name:
                continue
            current = characters.setdefault(name, {'name': name, 'traits': [], 'evidence': [],
                'desire': '', 'fear': '', 'voice': '', 'relationships': [], 'uncertain': [],
                'skills': []})
            for key in ('desire', 'fear', 'voice'):
                if not current[key] and isinstance(found.get(key), str):
                    current[key] = found[key]
            for key in ('traits', 'evidence', 'relationships', 'uncertain'):
                for value in found.get(key) or []:
                    if isinstance(value, str) and value and value not in current[key]:
                        current[key].append(value)
            for skill in found.get('skills') or []:
                if not isinstance(skill, dict) or not isinstance(skill.get('name'), str):
                    continue
                skill_name = skill['name'].strip()
                if skill_name and not any(row.get('name') == skill_name for row in current['skills']):
                    try:
                        level = int(skill.get('level') or 1)
                    except (TypeError, ValueError):
                        level = 1
                    current['skills'].append({'name': skill_name,
                        'category': str(skill.get('category') or '其他'),
                        'level': max(1, min(5, level)),
                        'evidence': str(skill.get('evidence') or '')})
    return {'characters': list(characters.values()), 'open_questions': questions}


def conservative_tokens(text: str) -> int:
    """用 UTF-8 字节数作输入 token 上界的保守代理，供本地预算闸门使用。"""
    return len(text.encode("utf-8")) + 32


def peak_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PEAK_PRICES[model]
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


def request_ceiling(route: Route, messages: list[dict]) -> float:
    payload = json.dumps(messages, ensure_ascii=False)
    return peak_cost(route.model, conservative_tokens(payload), route.max_tokens)


def actual_cost(route: Route, usage: dict) -> float:
    hit = int(usage.get("prompt_cache_hit_tokens") or 0)
    prompt = int(usage.get("prompt_tokens") or 0)
    miss = int(usage.get("prompt_cache_miss_tokens") or max(0, prompt - hit))
    output = int(usage.get("completion_tokens") or 0)
    hit_price = 0.006 if route.model == MODEL_FLASH else 0.044
    return (hit * hit_price + miss * PEAK_PRICES[route.model]["input"]
            + output * PEAK_PRICES[route.model]["output"]) / 1_000_000


def repeats(text: str) -> bool:
    if len(text) >= 256 and not text[-256:].strip():
        return True
    compact = re.sub(r"\s+", " ", text[-2400:])
    # 不依赖固定段长；模型可能反复输出任意长度的句子或段落。
    for size in range(12, 401):
        copies = 5 if size < 30 else 3
        if len(compact) >= size * copies and compact[-size * copies:] == compact[-size:] * copies:
            return True
    return False


def select_memory(chapters: list[dict], scene: str, limit: int = 10500) -> str:
    """最近章节优先，加上与当前任务有字词交集的旧摘要。"""
    if not chapters:
        return "尚无已保存章节。"
    terms = set(re.findall(r"[\u4e00-\u9fff]{2,4}|[A-Za-z]{3,}", scene.lower()))
    recent_ids = {row["id"] for row in chapters[-5:]}
    ranked = []
    for row in chapters:
        if row.get('summary_status') == 'stale':
            continue
        summary = row.get("summary") or ""
        if not summary:
            continue
        score = sum(1 for term in terms if term in summary.lower())
        ranked.append((row["id"] in recent_ids, score, row["number"], row))
    chosen = sorted(ranked, reverse=True)[:16]
    chosen.sort(key=lambda item: item[2])
    pieces = []
    remaining = limit
    for _, _, _, row in chosen:
        piece = f"第{row['number']}章 {row['title']}：{row['summary']}\n"
        if len(piece) > remaining:
            continue
        pieces.append(piece)
        remaining -= len(piece)
    return "".join(pieces) or "暂无章节摘要。"


def build_messages(task: str, novel: dict, chapters: list[dict], *, scene: str = "") -> list[dict]:
    first = next((row for row in chapters if row['number'] == 1), None)
    first_body = (first or {}).get('body') or ''
    first_excerpt = first_body[:4000] + ('\n…\n' + first_body[-2000:] if len(first_body) > 6000 else '')
    world = novel.get('worldbuilding') or '作者尚未填写世界观设定。'
    bible = character_context(novel.get("bible") or "")
    plan = (novel.get("arc_plan") or "")[:9000]
    if task == "analyze":
        system = (
            "你是长篇小说人物编辑。只从原文提取证据，不要把推测写成既定事实。"
            "仅输出有效 JSON，格式：{\"characters\":[{\"name\":\"\",\"traits\":[\"\"],"
            "\"evidence\":[\"原文证据\"],\"desire\":\"\",\"fear\":\"\",\"voice\":\"\","
            "\"relationships\":[\"\"],\"uncertain\":[\"\"],\"skills\":[{\"name\":\"能力名称\","
            "\"category\":\"类别\",\"level\":1,\"evidence\":\"原文证据\"}]}],"
            "\"open_questions\":[\"\"]}。技能等级为1到5，只记录正文明确展示的能力，未展示的不要猜。"
            "每段最多记录六个重要角色，证据简短。未知字段填空字符串或空数组，内容用中文。"
        )
        user = f"小说标题：{novel['title']}\n故事设想：{novel.get('premise','')}\n第一章正文片段：\n{scene}"
    elif task == "plan":
        system = (
            "你是长篇小说策划编辑。根据已确定的人物性格推演变化，给出可供作者选择的路线。"
            "不要把推演当作既定事实；避免人物突然变性格。"
            "遵守作者的世界观设定，不得违背力量体系、时代背景及世界规则。"
            "同时遵守人物档案和章节记忆，记忆中已发生的事实不得改写。"
            "未来推演不得写成已经发生。成长记录用于理解人物当前变化。"
            "用 Markdown 输出：人物起点、内在冲突、关键选择与代价、三阶段弧线、关系变化、"
            "伏笔回收、需要作者决定的分叉。每个转折说明因果。"
        )
        memory = select_memory(chapters, bible[:2500])
        user = f"标题：{novel['title']}\n设想：{novel.get('premise','')}\n世界观设定（既定约束）：{world}\n第一章节选：{first_excerpt}\n人物档案：{bible}\n相关章节记忆（已发生事实）：{memory}"
    elif task in ("draft", "draft_pro"):
        system = (
            "你是协助作者的长篇小说写作搭档。只写当前场景的小说正文，不作说明，不提前写完未来章节。"
            "人物言行必须符合档案和已发生情节；变化要有触发事件。保持既有视角、文风和关系进度。"
            "世界观设定是既定约束，严格遵守时代、地理、力量体系、能力代价和禁忌规则，不能为推动剧情临时破例。"
            "人物档案及章节记忆也是约束：不得改写已发生事实，不得把人物发展计划的未来事件当成既成事实。"
            "结合人物成长记录理解当前变化，不因初始性格忽略已有的发展。"
            "本次章节/场景要求是此次生成的直接任务，按作者指定的事件、顺序、出场人物和视角推进；"
            "在世界观和已发生事实允许的范围内执行，不提前写完未要求的后续情节。"
            "若用户指定约会，就写有具体行动、对话、细节和情绪变化的约会场景；不凭空添加重大设定。"
            "结尾留自然的下一步空间，避免重复段落。"
        )
        memory = select_memory(chapters, scene)
        last = (chapters[-1].get("body") or "")[-3500:] if chapters else ''
        user = (
            f"标题：{novel['title']}\n故事设想：{novel.get('premise','')}\n"
            f"世界观设定（既定约束）：{world}\n"
            f"人物档案：{bible}\n人物发展计划：{plan}\n相关章节摘要：{memory}\n"
            f"最近一章结尾：{last}\n本次章节 / 场景要求（此次直接任务）：{scene[:2500]}\n"
            "请写约 1200—2000 字的正文；有冲突时优先遵守已保存的正文和人物证据。"
        )
    elif task == "character_updates":
        system = (
            '你是小说人物档案记录员，只从提供的章节记忆提取人物观察，不续写，不推测。'
            '仅输出有效 JSON：{"characters":[{"name":"正式姓名", "traits":["本章性格表现或变化"],'
            '"evidence":["章节记忆中的具体事件依据"],"desire":"本章明确的目标",'
            '"fear":"","voice":"","relationships":["本章关系变化"],"uncertain":[], '
            '"skills":[{"name":"能力名称","category":"类别","level":1,"evidence":"记忆依据"}]}]}。'
            '最多六个重要角色。每个角色必须有 evidence；没有依据就不列入。'
            '有已知正式姓名时沿用，禁止把不确定的别名强行合并。未知字段填空字符串或空数组。'
            '技能仅记录记忆明确展示的新能力或等级变化，等级1到5；没有变化则 skills 为空数组。'
            '不把未来计划当成已发生事实，证据简短，全部用中文。'
        )
        user = f"标题：{novel['title']}\n已有人物档案（用于识别姓名与技能）：{bible}\n本章记忆：\n{scene}"
    elif task == "summarize":
        system = (
            "你是小说连续性记录员。只记录正文明确发生的事实，不替作者续写。"
            "用简短 Markdown 列出：事件、人物选择及性格变化、关系变化、技能变化及原文依据、"
            "确定的新事实、未解决问题与伏笔。没有的项目可以略去。每段控制在 600 字内。"
        )
        user = f"标题：{novel['title']}\n本章正文片段：\n{scene}"
    elif task == "summarize_merge":
        system = (
            "你是小说连续性记录员。把按顺序提供的片段记录合并成整章记忆。"
            "只保留已发生的事实，合并重复项，不把片段间的猜测当事实。"
            "用 Markdown 写事件顺序、人物与关系变化、技能变化、伏笔和悬而未决事项；"
            "控制在 800 到 1200 字。"
        )
        user = f"标题：{novel['title']}\n片段记录：\n{scene}"
    else:
        raise ValueError("未知任务")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def character_context(text: str, limit: int = 14000) -> str:
    """历史按章长期保存；请求只携带每人近期变化，避免整本档案重复上传。"""
    try:
        value = json.loads(text)
        people = value['characters']
        if not isinstance(people, list):
            return text[:limit]
        compact = []
        for person in people:
            record = {k: v for k, v in person.items() if k != 'chapter_history'}
            history = person.get('chapter_history') or []
            record['chapter_history'] = history[-2:]
            compact.append(record)
        return json.dumps({'characters': compact}, ensure_ascii=False)[:limit]
    except (ValueError, KeyError, TypeError, AttributeError):
        return text[:limit]
