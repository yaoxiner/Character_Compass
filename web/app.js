const $ = (id) => document.getElementById(id);
const state = { novel: null, chapterId: null, currentChapter: null, config: null,
  busy: false, dirty: false, chapterDirty: false, summaryDirty: false, memoryPage: 0, review: null };
let toastTimer;

function toast(message) {
  const el = $('toast'); el.textContent = message; el.classList.add('visible');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('visible'), 5000);
}

async function api(path, options = {}) {
  const response = await fetch('/api' + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  let data;
  try { data = await response.json(); } catch { throw new Error('服务器返回了无法读取的数据。'); }
  if (!response.ok) {
    const error = new Error(data.error || '请求失败。'); error.data = data; throw error;
  }
  return data;
}

function setBusy(value) {
  state.busy = value;
  document.querySelectorAll('button').forEach(button => {
    if (!button.classList.contains('tab') && !button.classList.contains('novel-item')) button.disabled = value;
  });
  if (!value) {
    $('save-chapter').disabled = !state.chapterId;
    $('summarize').disabled = !state.chapterId;
    $('delete-chapter').disabled = !state.chapterId;
    if (state.novel) { renderChapterList(); renderSkills(); renderSummaryStatus(); renderMemories(); }
    updateReviewButton();
  }
  $('saved-indicator').textContent = value ? '正在处理…' : '';
}

async function run(task) {
  if (state.busy) return;
  setBusy(true);
  try { await task(); } catch (error) { toast(error.message); }
  finally { setBusy(false); await refreshConfig(); }
}

async function refreshConfig() {
  try {
    state.config = await api('/config');
    const { used_today_usd: used, daily_budget_usd: budget, key_configured: key } = state.config;
    $('budget-label').textContent = `$${used.toFixed(3)} / $${budget.toFixed(2)}`;
    $('budget-fill').style.width = Math.min(100, 100 * used / Math.max(.001, budget)) + '%';
    $('key-status').textContent = key ? 'DeepSeek Key 已配置 · 数据保存在本机' : '尚未配置 DeepSeek Key · 点击下方设置';
  } catch { $('key-status').textContent = '配置读取失败'; }
}

async function refreshBalance() {
  const label = $('balance-status');
  label.textContent = '正在查询余额…';
  try {
    const result = await api('/balance');
    const entries = result.balance_infos || [];
    label.textContent = entries.length
      ? entries.map(item => `${item.currency} ${item.total_balance}`).join(' · ')
      : '暂无余额信息';
    label.classList.toggle('balance-low', !result.is_available);
  } catch (error) {
    label.textContent = error.message;
    label.classList.remove('balance-low');
  }
}

async function loadNovels(preferredId) {
  const novels = await api('/novels');
  const list = $('novel-list'); list.replaceChildren();
  for (const novel of novels) {
    const button = document.createElement('button'); button.className = 'novel-item';
    button.textContent = novel.title; button.dataset.id = novel.id;
    button.onclick = () => run(async () => {
      if ((state.dirty || state.chapterDirty) && !confirm('有未保存的内容。确定切换小说吗？')) return;
      await loadNovel(novel.id);
    });
    list.append(button);
  }
  if (novels.length) await loadNovel(preferredId && novels.some(n => n.id === preferredId) ? preferredId : novels[0].id);
  else { $('empty-state').hidden = false; $('workspace').hidden = true; $('project-title').textContent = '开始你的故事'; $('save-all').hidden = true; }
}

async function loadNovel(id) {
  const novel = await api('/novels/' + id); state.novel = novel; state.dirty = false;
  state.chapterDirty = false; state.summaryDirty = false;
  if (!novel.chapters.length) {
    const first = await api(`/novels/${id}/chapters`, {
      method: 'POST', body: { number: 1, title: '第一章', body: '' },
    });
    novel.chapters.push(first);
  }
  state.chapterId = novel.chapters[novel.chapters.length - 1].id;
  $('empty-state').hidden = true; $('workspace').hidden = false; $('save-all').hidden = false;
  $('project-title').textContent = novel.title;
  $('novel-title').value = novel.title;
  $('premise').value = novel.premise || '';
  $('outline').value = novel.outline || ''; $('bible').value = novel.bible || '';
  $('worldbuilding').value = novel.worldbuilding || '';
  $('scene').value = novel.scene_brief || '';
  $('arc-plan').value = novel.arc_plan || ''; $('draft-output').value = novel.draft || '';
  document.querySelectorAll('.novel-item').forEach(btn => btn.classList.toggle('active', Number(btn.dataset.id) === id));
  $('chapter-search').value = '';
  $('memory-search').value = ''; $('memory-filter').value = 'all'; state.memoryPage = 0;
  renderSkills();
  renderCharacterHistory(); renderMemories();
  await selectChapter(state.chapterId, true);
  $('saved-indicator').textContent = '已保存';
}

function renderSkills() {
  const root = $('skill-tree'); root.replaceChildren();
  let characters;
  try { characters = JSON.parse($('bible').value || '{}').characters || []; }
  catch { root.textContent = '人物档案 JSON 格式有误；修正后显示技能树。'; return; }
  if (!Array.isArray(characters)) characters = [];
  if (!characters.length) { root.textContent = '第一章分析后，重要角色的技能会显示在这里。'; return; }
  for (const [personIndex, person] of characters.entries()) {
    if (!person || typeof person !== 'object') continue;
    const card = document.createElement('div'); card.className = 'skill-person';
    const name = document.createElement('h4'); name.textContent = person.name || '未命名角色'; card.append(name);
    const groups = new Map();
    for (const [skillIndex, skill] of (Array.isArray(person.skills) ? person.skills : []).entries()) {
      if (!skill || typeof skill !== 'object') continue;
      const category = skill.category || '其他';
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category).push({ skill, skillIndex });
    }
    if (!groups.size) {
      const empty = document.createElement('p'); empty.className = 'skill-empty';
      empty.textContent = '暂无有原文依据的技能。'; card.append(empty);
    }
    for (const [category, entries] of groups) {
      const group = document.createElement('div'); group.className = 'skill-group';
      const heading = document.createElement('strong'); heading.textContent = category; group.append(heading);
      for (const { skill, skillIndex } of entries) {
        const row = document.createElement('div'); row.className = 'skill-row';
        const label = document.createElement('span'); label.textContent = skill.name || '未命名技能';
        if (skill.evidence) { const evidence = document.createElement('small'); evidence.textContent = skill.evidence; label.append(evidence); }
        const level = document.createElement('span'); level.className = 'skill-level';
        const count = Math.max(1, Math.min(5, Number(skill.level) || 1));
        level.textContent = '●'.repeat(count) + '○'.repeat(5 - count);
        const controls = document.createElement('span'); controls.className = 'skill-controls';
        for (const [symbol, next] of [['−', count - 1], ['＋', count + 1]]) {
          const button = document.createElement('button'); button.type = 'button';
          button.textContent = symbol; button.title = `${skill.name}等级调整为 ${next}`;
          button.disabled = state.busy || next < 1 || next > 5;
          button.onclick = () => editSkills(personIndex, skills => { skills[skillIndex].level = next; });
          controls.append(button);
        }
        const remove = document.createElement('button'); remove.type = 'button';
        remove.textContent = '×'; remove.title = `移除 ${skill.name}`; remove.disabled = state.busy;
        remove.onclick = () => {
          if (confirm(`移除“${skill.name}”技能记录？`)) editSkills(personIndex, skills => { skills.splice(skillIndex, 1); });
        };
        controls.append(remove);
        row.append(label, level, controls); group.append(row);
      }
      card.append(group);
    }
    const add = document.createElement('div'); add.className = 'skill-add';
    const skillName = document.createElement('input'); skillName.placeholder = '新增技能名称'; skillName.maxLength = 60;
    const category = document.createElement('input'); category.placeholder = '类别'; category.maxLength = 40;
    const evidence = document.createElement('input'); evidence.placeholder = '原文依据或章节'; evidence.maxLength = 200;
    const addButton = document.createElement('button'); addButton.type = 'button'; addButton.textContent = '添加';
    addButton.disabled = state.busy;
    addButton.onclick = () => {
      const value = skillName.value.trim();
      if (!value) { toast('先填写技能名称。'); return; }
      editSkills(personIndex, skills => skills.push({ name: value,
        category: category.value.trim() || '其他', level: 1, evidence: evidence.value.trim() }));
    };
    add.append(skillName, category, evidence, addButton); card.append(add);
    root.append(card);
  }
}

function editSkills(personIndex, change) {
  let bible;
  try { bible = JSON.parse($('bible').value); }
  catch { toast('先修正人物档案 JSON。'); return; }
  const person = bible.characters?.[personIndex];
  if (!person) return;
  if (!Array.isArray(person.skills)) person.skills = [];
  change(person.skills);
  $('bible').value = JSON.stringify(bible, null, 2);
  state.dirty = true;
  $('saved-indicator').textContent = '技能树有未保存的修改';
  renderSkills();
}

function renderChapterList() {
  const list = $('chapter-list'); list.replaceChildren();
  const chapters = [...state.novel.chapters].sort((a, b) => a.number - b.number);
  const query = $('chapter-search').value.trim().toLowerCase();
  const matches = chapters.filter(ch => !query || String(ch.number).includes(query) ||
    (ch.title || '').toLowerCase().includes(query));
  const selected = chapters.find(ch => ch.id === state.chapterId);
  const shown = matches.slice(0, 80);
  if (selected && !shown.some(ch => ch.id === selected.id) && !query) shown.unshift(selected);
  for (const chapter of shown) {
    const button = document.createElement('button'); button.className = 'chapter-pill';
    const title = document.createElement('span');
    title.textContent = `第 ${chapter.number} 章${chapter.title ? ' · ' + chapter.title : ''}`;
    const count = document.createElement('span'); count.textContent = `${(chapter.body_chars || 0).toLocaleString()} 字`;
    button.append(title, count);
    button.classList.toggle('active', chapter.id === state.chapterId);
    button.onclick = () => run(async () => { await selectChapter(chapter.id); });
    list.append(button);
  }
  $('chapter-list-note').textContent = matches.length > shown.length
    ? `找到 ${matches.length} 章，当前显示前 80 章；输入章号或标题继续定位。`
    : `找到 ${matches.length} 章。`;
  const total = chapters.reduce((sum, ch) => sum + (ch.body_chars || 0), 0);
  $('novel-stats').textContent = `共 ${chapters.length} 章 · 正文 ${total.toLocaleString()} 字`;
  const selectedIndex = chapters.findIndex(ch => ch.id === state.chapterId);
  $('prev-chapter').disabled = state.busy || selectedIndex <= 0;
  $('next-chapter').disabled = state.busy || selectedIndex >= chapters.length - 1;
}

function renderSummaryStatus() {
  const status = state.currentChapter?.summary_status;
  $('summary-status').textContent = {
    missing: '尚未提取。本章保存后，点击按钮即可从正文生成事实记录。',
    current: '已从当前正文提取；你可以校正错漏。',
    stale: '正文在上次提取后有修改，建议重新提取。',
    unknown: '这是旧版章节记忆，来源版本未记录；建议核对。',
  }[status] || '';
  $('update-characters').disabled = state.busy || status !== 'current';
  $('character-sync-status').textContent = {
    missing: '章节记忆尚未同步到人物档案。提取记忆后，点击上方按钮核对人物变化。',
    pending: '已有人物变化待核对，再次点击可打开预览，不重复调用 AI。',
    partial: '本章部分人物变化已写入，可再次打开预览确认其余人物。',
    empty: '已核对：本章记忆未提取到有依据的重要人物变化。',
    applied: '本章已确认的人物变化已写入档案；可再次打开预览查看或补选人物。',
    stale: '本章正文或记忆有变化；已有成长记录保留，请重新提取后核对更新。',
  }[state.currentChapter?.character_sync_status || 'missing'];
}

async function selectChapter(id, force = false) {
  if (!force && state.chapterDirty && !confirm('章节有未保存的修改。确定切换吗？')) return;
  const chapter = await api(`/novels/${state.novel.id}/chapters/${id}`);
  state.chapterId = id; state.currentChapter = chapter;
  state.chapterDirty = false; state.summaryDirty = false;
  $('chapter-number').value = chapter.number;
  $('chapter-title').value = chapter.title || '';
  $('chapter-body').value = chapter.body || '';
  $('chapter-summary').value = chapter.summary || '';
  renderChapterList(); renderSummaryStatus(); updateCounts();
}

function updateCounts() {
  $('draft-count').textContent = `${$('draft-output').value.length} 字`;
  $('chapter-count').textContent = `${$('chapter-body').value.length.toLocaleString()} 字`;
}

async function saveNovel() {
  if (!state.novel) return;
  const data = {
    title: $('novel-title').value.trim(), premise: $('premise').value, outline: $('outline').value,
    worldbuilding: $('worldbuilding').value,
    scene_brief: $('scene').value,
    bible: $('bible').value, arc_plan: $('arc-plan').value, draft: $('draft-output').value,
  };
  const updated = await api('/novels/' + state.novel.id, { method: 'PUT', body: data });
  state.novel = updated; state.dirty = false; $('saved-indicator').textContent = '已保存';
  $('project-title').textContent = updated.title;
  const nav = document.querySelector(`.novel-item[data-id="${updated.id}"]`);
  if (nav) nav.textContent = updated.title;
  renderCharacterHistory(); renderMemories();
}

async function saveChapter() {
  const id = state.chapterId;
  if (!id) throw new Error('先新建章节。');
  const data = { number: Number($('chapter-number').value), title: $('chapter-title').value,
    body: $('chapter-body').value };
  if (state.summaryDirty) data.summary = $('chapter-summary').value;
  const updated = await api(`/novels/${state.novel.id}/chapters/${id}`, {
    method: 'PUT', body: data,
  });
  const index = state.novel.chapters.findIndex(ch => ch.id === id);
  state.novel.chapters[index] = updated; state.currentChapter = updated;
  state.chapterDirty = false; state.summaryDirty = false;
  state.novel.chapters.sort((a, b) => a.number - b.number);
  renderChapterList(); renderSummaryStatus();
  renderMemories();
  $('saved-indicator').textContent = '章节已保存';
}

async function generate(task, extra = {}) {
  if (state.chapterDirty) await saveChapter();
  if (state.dirty) await saveNovel();
  const result = await api(`/novels/${state.novel.id}/generate`, {
    method: 'POST', body: { task, ...extra },
  });
  if (task === 'analyze') {
    $('bible').value = result.content; state.novel.bible = result.content;
    renderSkills(); switchTab('characters');
  }
  if (task === 'plan') { $('arc-plan').value = result.content; state.novel.arc_plan = result.content; }
  if (task === 'draft' || task === 'draft_pro') { $('draft-output').value = result.content; state.novel.draft = result.content; updateCounts(); }
  if (task === 'summarize') {
    $('chapter-summary').value = result.content;
    const current = state.novel.chapters.find(ch => ch.id === state.chapterId);
    const updated = await api(`/novels/${state.novel.id}/chapters/${state.chapterId}`);
    if (current) Object.assign(current, updated);
    state.currentChapter = updated;
    renderSummaryStatus(); renderMemories();
  }
  toast(result.cached ? '已打开保存的变化预览，本次未调用 AI。' : `完成 · ${result.model} · ${result.requests || 1} 次请求 · 估算 $${result.cost_usd_estimate.toFixed(4)}${result.finish_reason === 'length' ? '\n已达输出上限，建议检查结尾。' : ''}`);
  return result;
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(tab => {
    const active = tab.dataset.tab === name; tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.id === name));
  if (name === 'memories') renderMemories();
  if (name === 'characters') renderCharacterHistory();
}

const memoryLabels = {current: '记忆有效', missing: '尚未提取', stale: '正文已修改，记忆待更新', unknown: '旧版记忆待核对'};
function chapterHeading(chapter) { return `第 ${chapter.number} 章${chapter.title ? ' · ' + chapter.title : ''}`; }
function textElement(tag, text, className) {
  const element = document.createElement(tag); element.textContent = text;
  if (className) element.className = className;
  return element;
}
function renderMemories() {
  if (!state.novel) return;
  const chapters = [...state.novel.chapters].sort((a, b) => a.number - b.number);
  const count = status => chapters.filter(ch => ch.summary_status === status).length;
  $('memory-stats').textContent = `共 ${chapters.length} 章 · 记忆有效 ${count('current')} · 未提取 ${count('missing')} · 正文已修改 ${count('stale')} · 旧版待核对 ${count('unknown')}`;
  const query = $('memory-search').value.trim().toLowerCase();
  const filter = $('memory-filter').value;
  const matches = chapters.filter(ch => (!query || `${ch.number} ${ch.title} ${ch.summary}`.toLowerCase().includes(query)) &&
    (filter === 'all' || ch.summary_status === filter || (filter === 'unsynced' && ch.summary_status === 'current' && !['applied','empty'].includes(ch.character_sync_status))));
  const pages = Math.max(1, Math.ceil(matches.length / 30));
  state.memoryPage = Math.min(state.memoryPage, pages - 1);
  $('memory-page').textContent = `找到 ${matches.length} 章 · 第 ${state.memoryPage + 1} / ${pages} 页`;
  $('memory-prev').disabled = state.busy || state.memoryPage === 0;
  $('memory-next').disabled = state.busy || state.memoryPage >= pages - 1;
  const root = $('memory-list'); root.replaceChildren();
  if (!matches.length) root.append(textElement('p', '没有符合条件的章节。', 'hint'));
  for (const ch of matches.slice(state.memoryPage * 30, (state.memoryPage + 1) * 30)) {
    const card = document.createElement('details'); card.className = 'memory-entry';
    const heading = document.createElement('summary');
    heading.append(textElement('strong', chapterHeading(ch)), textElement('span', memoryLabels[ch.summary_status] || '尚未提取', `memory-badge ${ch.summary_status}`));
    card.append(heading);
    card.append(textElement('pre', ch.summary || '本章还没有记忆。进入章节，保存正文后提取。', 'memory-content'));
    card.append(textElement('p', {applied:'本章人物变化已写入档案。', partial:'部分人物已写入，其余变化待核对。', empty:'已核对，本章未提取到重要人物变化。', pending:'人物变化待核对，重新打开预览不消耗 token。'}[ch.character_sync_status] || '人物档案待核对更新。', 'hint'));
    const actions = document.createElement('div'); actions.className = 'memory-links';
    const open = textElement('button', '打开章节 →', 'button small subtle'); open.disabled = state.busy;
    open.onclick = () => run(async () => {
      if (state.chapterDirty) await saveChapter();
      await selectChapter(ch.id, true); switchTab('chapters');
    });
    const update = textElement('button', '核对并更新人物', 'button small primary');
    update.disabled = state.busy || ch.summary_status !== 'current';
    update.onclick = () => run(() => reviewCharacters(ch.id));
    actions.append(open, update); card.append(actions); root.append(card);
  }
}

function appendObservations(root, observation) {
  for (const [key, label] of [['traits','性格与选择'], ['relationships','关系'], ['desire','目标'], ['fear','顾虑'], ['voice','说话方式'], ['uncertain','待核对'], ['evidence','记忆依据']]) {
    const value = observation[key]; const text = Array.isArray(value) ? value.join('；') : value;
    if (text) root.append(textElement('p', `${label}：${text}`, 'observation-line'));
  }
}
function renderCharacterHistory() {
  const root = $('character-history'); root.replaceChildren();
  let people;
  try { people = JSON.parse($('bible').value || '{}').characters || []; }
  catch { root.append(textElement('p', '修正人物档案 JSON 后显示成长记录。', 'hint')); return; }
  if (!Array.isArray(people)) return;
  let hasHistory = false;
  for (const person of people) {
    const history = person?.chapter_history;
    if (!Array.isArray(history) || !history.length) continue;
    hasHistory = true;
    const details = document.createElement('details'); details.className = 'memory-entry';
    details.append(textElement('summary', `${person.name} · ${history.length} 章成长记录`));
    let loaded = false;
    details.addEventListener('toggle', () => {
      if (!details.open || loaded) return;
      loaded = true;
      for (const entry of [...history].sort((a,b) => a.chapter_number - b.chapter_number)) {
        const block = document.createElement('div'); block.className = 'history-entry';
        block.append(textElement('strong', `第 ${entry.chapter_number} 章 · ${entry.chapter_title || ''}`));
        const source = state.novel.chapters.find(ch => ch.id === entry.chapter_id);
        if (!source || source.body_hash !== entry.source_hash || (entry.summary_hash && source.summary_hash !== entry.summary_hash)) block.append(textElement('p', '来源章节或记忆已修改、删除，此记录待重新核对。', 'hint'));
        appendObservations(block, entry.observations || {});
        for (const skill of entry.observations?.skills || []) block.append(textElement('p', `技能：${skill.name} · ${skill.level}/5 · ${skill.evidence}`, 'observation-line'));
        details.append(block);
      }
    });
    root.append(details);
  }
  if (!hasHistory) root.append(textElement('p', '尚无成长记录。提取章节记忆后，核对人物变化并确认写入，这里就会按章展示。', 'hint'));
}

async function reviewCharacters(chapterId) {
  if (state.chapterDirty) await saveChapter();
  if (state.dirty) await saveNovel();
  if (state.chapterId !== chapterId) await selectChapter(chapterId, true);
  const result = await generate('character_updates', {chapter_id: chapterId});
  const proposal = result.proposal;
  state.review = {chapterId, proposal, bible_hash: result.bible_hash};
  const updated = await api(`/novels/${state.novel.id}/chapters/${chapterId}`);
  state.currentChapter = updated;
  Object.assign(state.novel.chapters.find(ch => ch.id === chapterId), updated);
  renderSummaryStatus(); renderMemories();
  $('character-review-source').textContent = `${chapterHeading(updated)} · Flash · 读取本章记忆与精简人物上下文；关闭后可免费重新打开此预览。`;
  const root = $('character-review-list'); root.replaceChildren();
  const people = JSON.parse($('bible').value || '{}').characters || [];
  for (const observation of proposal.characters) {
    const old = people.find(person => person.name === observation.name);
    const card = document.createElement('div'); card.className = 'review-person';
    const label = document.createElement('label'); label.className = 'review-choice';
    const check = document.createElement('input'); check.type = 'checkbox'; check.value = observation.name;
    check.checked = !proposal.applied_names.includes(observation.name);
    check.addEventListener('change', updateReviewButton);
    label.append(check, textElement('strong', `${observation.name} · ${old ? '追加成长记录' : '新增人物'}${proposal.applied_names.includes(observation.name) ? '（已写入）' : ''}`));
    card.append(label); appendObservations(card, observation);
    for (const skill of observation.skills) {
      const previous = old?.skills?.find(s => s.name === skill.name);
      const newer = previous && previous.source_chapter > updated.number;
      card.append(textElement('p', `技能「${skill.name}」：${previous ? previous.level + '/5' : '未记录'} → ${newer ? '保留新章等级 ' + previous.level + '/5，仅记录本章观察' : skill.level + '/5'}；依据：${skill.evidence}`, 'skill-change'));
    }
    root.append(card);
  }
  if (!proposal.characters.length) root.append(textElement('p', '本章记忆中未提取到有依据的重要人物变化，无需写入。', 'hint'));
  updateReviewButton(); $('character-review-dialog').showModal();
}
function updateReviewButton() {
  $('apply-character-updates').disabled = state.busy || !$('character-review-list').querySelector('input:checked');
}

async function createNovel() {
  const title = $('new-title').value.trim(); if (!title) return;
  const novel = await api('/novels', { method: 'POST', body: { title, premise: $('new-premise').value } });
  $('create-dialog').close(); $('create-form').reset(); await loadNovels(novel.id); switchTab('chapters');
  toast('小说已创建。现在可以直接写第一章。');
}

async function showUsage() {
  const entries = await api(`/novels/${state.novel.id}/calls`);
  const list = $('usage-list'); list.replaceChildren(); $('recovery-box').hidden = true;
  if (!entries.length) list.textContent = '还没有调用记录。';
  for (const item of entries) {
    const row = document.createElement('div'); row.className = 'usage-row';
    const title = document.createElement('span'); title.textContent = `${item.task} · ${item.status}`;
    const model = document.createElement('span'); model.textContent = item.model;
    const amount = document.createElement('span'); amount.textContent = `$${item.charged_usd.toFixed(4)}`;
    row.append(title, model, amount); list.append(row);
    if (item.partial_chars > 0) {
      const recover = document.createElement('button'); recover.className = 'recover-link';
      recover.textContent = '查看内容';
      recover.onclick = async () => {
        try {
          const call = await api(`/novels/${state.novel.id}/calls/${item.id}`);
          $('recovery-text').value = call.partial_text;
          $('recovery-box').hidden = false;
          $('recovery-box').scrollIntoView({ behavior: 'smooth' });
        } catch (error) { toast(error.message); }
      };
      row.append(recover);
    }
  }
  $('usage-dialog').showModal();
}

document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => switchTab(tab.dataset.tab)));
['novel-title','premise','outline','worldbuilding','scene','bible','arc-plan','draft-output'].forEach(id => $(id).addEventListener('input', () => {
  state.dirty = true; $('saved-indicator').textContent = '有未保存的修改'; updateCounts();
  if (id === 'bible') renderSkills();
}));
['chapter-number','chapter-title','chapter-body','chapter-summary'].forEach(id => $(id).addEventListener('input', () => {
  state.chapterDirty = true; $('saved-indicator').textContent = '章节有未保存的修改'; updateCounts();
  if (id === 'chapter-summary') state.summaryDirty = true;
}));
$('chapter-search').addEventListener('input', renderChapterList);
for (const id of ['memory-search', 'memory-filter']) $(id).addEventListener('input', () => { state.memoryPage = 0; renderMemories(); });
$('memory-prev').onclick = () => { state.memoryPage--; renderMemories(); };
$('memory-next').onclick = () => { state.memoryPage++; renderMemories(); };
$('view-memories').onclick = $('go-memories').onclick = () => switchTab('memories');
$('update-characters').onclick = () => run(() => reviewCharacters(state.chapterId));
$('close-character-review').onclick = () => $('character-review-dialog').close();
$('apply-character-updates').onclick = () => run(async () => {
  const review = state.review;
  const names = [...$('character-review-list').querySelectorAll('input:checked')].map(input => input.value);
  const result = await api(`/novels/${state.novel.id}/chapters/${review.chapterId}/characters`, {
    method: 'PUT', body: {names, proposal_id: review.proposal.id, bible_hash: review.bible_hash},
  });
  $('bible').value = result.bible; state.novel.bible = result.bible;
  Object.assign(state.novel.chapters.find(ch => ch.id === review.chapterId), result.chapter);
  if (state.chapterId === review.chapterId) state.currentChapter = result.chapter;
  $('character-review-dialog').close();
  renderSkills(); renderCharacterHistory(); renderSummaryStatus(); renderMemories();
  toast(`已保存 ${names.length} 个人物的本章变化，档案与技能树已更新。`);
});
$('export-memories').onclick = () => run(async () => {
  if (state.chapterDirty) await saveChapter();
  const lines = [`# ${state.novel.title} · 章节记忆`, ''];
  for (const ch of [...state.novel.chapters].sort((a,b) => a.number - b.number)) {
    lines.push(`## ${chapterHeading(ch)}`, '', `状态：${memoryLabels[ch.summary_status]}`, '', ch.summary || '尚未提取。', '');
  }
  const url = URL.createObjectURL(new Blob([lines.join('\n')], {type: 'text/markdown;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = `character-compass-${state.novel.id}-memories.md`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('全书章节记忆已导出，未调用 AI。');
});
$('new-novel').onclick = $('empty-create').onclick = () => $('create-dialog').showModal();
$('close-dialog').onclick = () => $('create-dialog').close();
$('close-usage').onclick = () => $('usage-dialog').close();
$('copy-recovery').onclick = async () => {
  try { await navigator.clipboard.writeText($('recovery-text').value); toast('内容已复制。'); }
  catch { $('recovery-text').select(); toast('请选择文本并复制。'); }
};
$('create-form').addEventListener('submit', event => { event.preventDefault(); run(createNovel); });
$('save-all').onclick = () => run(async () => { await saveNovel(); toast('设定与待审草稿已保存。'); });
$('analyze').onclick = () => run(async () => {
  if ($('bible').value.trim() && !confirm('这次分析会替换当前人物档案。继续吗？')) return;
  await generate('analyze');
});
$('plan').onclick = () => run(async () => {
  if ($('arc-plan').value.trim() && !confirm('这次推演会替换当前人物发展路线。继续吗？')) return;
  await generate('plan');
});
$('draft').onclick = () => run(async () => {
  try { await generate($('draft-model').value, { scene: $('scene').value }); }
  catch (error) {
    if (error.data?.partial) { $('draft-output').value = error.data.partial; state.dirty = true; updateCounts(); }
    throw error;
  }
});
$('insert-draft').onclick = () => run(async () => {
  const text = $('draft-output').value.trim(); if (!text) throw new Error('还没有可插入的草稿。');
  if (!state.chapterId) {
    const next = Math.max(0, ...state.novel.chapters.map(ch => ch.number)) + 1;
    const chapter = await api(`/novels/${state.novel.id}/chapters`, { method: 'POST', body: { number: next, title: '', body: '' } });
    state.novel.chapters.push(chapter); await selectChapter(chapter.id, true);
  }
  $('chapter-body').value += ($('chapter-body').value.trim() ? '\n\n' : '') + text;
  state.chapterDirty = true; updateCounts(); toast('已插入章节编辑器。修改后点击“保存章节”。');
});
$('add-chapter').onclick = () => run(async () => {
  if (state.chapterDirty) await saveChapter();
  const next = Math.max(0, ...state.novel.chapters.map(ch => ch.number)) + 1;
  const chapter = await api(`/novels/${state.novel.id}/chapters`, { method: 'POST', body: { number: next, title: '', body: '' } });
  state.novel.chapters.push(chapter); await selectChapter(chapter.id, true); toast(`第 ${next} 章已创建。`);
});
$('save-chapter').onclick = () => run(async () => { await saveChapter(); toast('章节已保存。'); });
$('summarize').onclick = () => run(async () => { await saveChapter(); await generate('summarize', { chapter_id: state.chapterId }); });
$('delete-chapter').onclick = () => run(async () => {
  if (!state.chapterId || !confirm('确定永久删除当前章节正文和记忆吗？建议先导出备份。')) return;
  const id = state.chapterId;
  await api(`/novels/${state.novel.id}/chapters/${id}`, { method: 'DELETE' });
  state.novel.chapters = state.novel.chapters.filter(ch => ch.id !== id);
  if (!state.novel.chapters.length) {
    const first = await api(`/novels/${state.novel.id}/chapters`, {
      method: 'POST', body: { number: 1, title: '第一章', body: '' },
    });
    state.novel.chapters.push(first);
  }
  await selectChapter(state.novel.chapters[state.novel.chapters.length - 1].id, true);
  toast('章节已删除。');
});
for (const [buttonId, offset] of [['prev-chapter', -1], ['next-chapter', 1]]) {
  $(buttonId).onclick = () => run(async () => {
    const chapters = [...state.novel.chapters].sort((a, b) => a.number - b.number);
    const index = chapters.findIndex(ch => ch.id === state.chapterId);
    const target = chapters[index + offset];
    if (target) await selectChapter(target.id);
  });
}
$('show-usage').onclick = () => run(showUsage);
$('refresh-balance').onclick = refreshBalance;
$('configure-key').onclick = () => $('key-dialog').showModal();
$('close-key').onclick = () => $('key-dialog').close();
$('key-form').addEventListener('submit', event => {
  event.preventDefault();
  run(async () => {
    await api('/config/key', {method:'POST', body:{key:$('api-key').value}});
    $('api-key').value = '';
    $('key-dialog').close();
    await refreshBalance();
    toast('DeepSeek 连接已更新。');
  });
});
$('open-pet').onclick = async () => {
  if (!window.pywebview?.api?.open_pet) {
    toast('请从桌面软件打开写作台，再启动桌面同伴。');
    return;
  }
  try { await window.pywebview.api.open_pet(); }
  catch { toast('桌面同伴启动失败，请检查桌面程序日志。'); }
};
$('export-novel').onclick = () => run(async () => {
  if (state.dirty) await saveNovel();
  if (state.chapterDirty) await saveChapter();
  const backup = await api(`/novels/${state.novel.id}/export`);
  const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob); const a = document.createElement('a');
  a.href = url; a.download = `character-compass-${state.novel.id}.json`;
  a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast('小说备份已导出。');
});
$('import-novel').onclick = () => $('import-file').click();
$('import-file').addEventListener('change', () => run(async () => {
  const file = $('import-file').files[0]; if (!file) return;
  if (file.size > 100_000_000) throw new Error('备份文件超过 100 MB。');
  let backup;
  try { backup = JSON.parse(await file.text()); } catch { throw new Error('文件不是有效 JSON。'); }
  const novel = await api('/novels/import', { method: 'POST', body: backup });
  $('import-file').value = ''; await loadNovels(novel.id); toast('备份已导入为新小说。');
}));
window.addEventListener('beforeunload', event => { if (state.dirty || state.chapterDirty) { event.preventDefault(); event.returnValue = ''; } });
run(async () => { await refreshConfig(); await loadNovels(); });
