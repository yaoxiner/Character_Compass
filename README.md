# Character Compass

本地运行的长篇小说创作工具。正文从第一章开始，作者可把一件完整事件写成数万字的长章，发布时再自行拆分。工具从第一章提取带证据的人物性格与技能，推演人物发展，再按照场景要求生成待审草稿。作者决定情节和定稿内容。

界面和桌面同伴采用同一套深海蓝、冰青、暖纸色设计。桌面同伴是独立的原生 Qt 透明悬浮角色（角色 128×192，固定画布 190×300），默认请求置顶，可抓住角色拖动；平时眨眼，自动打哈欠／伸懒腰至少间隔 5 分钟，点击会挥手并弹出白色对话卡片，推演人物时思考，写作时读书，完成后欢呼。角色默认从原素材读取细节并平滑渲染，高 DPI 屏幕提供对应分辨率的帧；角色仍为 128×192 的逻辑尺寸，不放大窗口。右键“显示画质”可立即切换“高清”或“像素”，切换时保留动作进度并记住选择。像素模式完整保留原先 64×96 缩小再放大的效果。拖动、挥手、欢呼、伸懒腰和落地分别使用八张连续姿势，拖动循环约 0.72 秒；拖动时会用抬手到头顶、甩到身侧的动漫式大幅摆臂和悬空交错蹬腿表现惊慌，松开后逐步站稳，再恢复之前的工作状态；松手时会检查屏幕边缘，保证双脚仍在可见范围内。卡片可显示 DeepSeek 余额，右键可刷新余额或收起同伴。写作台里的“显示桌面同伴”按钮可以重新唤起它，页面不再常驻另一张静态角色图。

![原生透明桌宠的离屏预览](docs/native-pet-preview.png)

[桌宠动作预览：支持暂停与逐帧查看](docs/companion-motion-preview.html)

## 直接运行软件

GitHub Actions 会分别生成 Windows 安装程序、Windows 便携包和 Linux 便携包。使用者**不需要安装 Python、pip 或项目依赖**；Python 和 Qt 渲染器随包一起提供。下载对应系统的构建产物后：

| 系统 | 解压后的启动文件 |
| --- | --- |
| Windows 64 位 | 运行 `CharacterCompass-Setup.exe`，安装程序会创建桌面快捷方式；便携版也可运行 `CharacterCompass-Windows/CharacterCompass.exe` |
| Linux x86_64 | 解压 `CharacterCompass-Linux-x86_64.tar.gz`，在 `CharacterCompass` 文件夹运行 `./install-desktop.sh` 创建桌面及应用菜单入口；也可直接运行 `./CharacterCompass` |

Linux 包在 Ubuntu 22.04 构建，仍需要目标电脑具备兼容的 glibc 和基础桌面图形库；无法保证任何发行版都零系统依赖。Windows 包内含 Qt WebEngine，不要求另装 WebView2。打包会比使用系统 WebView2 的方案更大。这是“用户无需装 Python 依赖”的代价。构建方式见 `.github/workflows/`。

**Windows exe 安装包：**上传源码到 `main` 或 `master` 后，Actions 会自动构建和验收。通过后下载 `CharacterCompass-Windows-Setup`，解压得到 `CharacterCompass-Setup.exe`。[构建、安装与验收说明](docs/windows-release.md)。

## 从源码运行（开发者）

Python 3.10+。建议使用虚拟环境。

```bash
python -m pip install -r requirements-desktop.txt
python desktop.py
```

同一命令适用于 Linux 与 Windows。桌面窗口使用 Qt；源码安装方法见 [pywebview 安装说明](https://pywebview.flowrl.com/guide/installation)。两个系统也都能使用无需 GUI 依赖的浏览器模式：

```bash
python app.py
```

浏览器打开 <http://127.0.0.1:8765>。服务只监听本机地址。无需 Key 就能编辑、保存和导入导出；AI 任务需要 Key。在左侧点击“设置 DeepSeek Key”即可连接或移除。Key 仅写入本机 `.env`，不会出现在页面响应或小说备份中。也可复制 `.env.example` 为 `.env` 后手动填写。

## 写作顺序

1. 新建小说后直接写第一章；故事设想与粗略大纲放在“故事设定”。粗略大纲仅供作者备忘，不发送给 AI，也不参与任何生成或推演。
2. 在“故事设定”填写世界观：时代、地理、势力、力量体系、能力代价和禁忌规则。保存后，它会完整参与 Flash / Pro 的场景生成与 Pro 人物发展推演，作为既定约束；世界观随小说备份一并导入导出。“分析第一章”用 Flash 提取性格、原文证据、欲望、恐惧、关系和有依据的技能。作者检查并修订人物档案；技能树按角色和类别展示，也可直接增补技能、调整等级。
3. “用 Pro 推演”根据世界观、人物档案和相关章节记忆给出人物弧线、关系变化、关键抉择。结果可编辑。
4. 描述具体场景，例如第一次约会。日常草稿用 Flash，重点场景可主动选 Pro。草稿不会自动覆盖章节正文。
5. 将草稿插入章节编辑器，修改后保存。点击“从整章正文提取记忆”，Flash 会提取事件、人物与关系变化、技能变化和伏笔。提取结果可校正错漏，修改正文后会提示重新提取。
6. 打开“章节记忆”查看全书按章排列的事实记录，可按章号、人物名、事件或伏笔搜索，筛选未提取、正文已修改或人物待更新的章节，并导出 Markdown。每页显示 30 章，不加载全书正文；浏览和导出不调用 AI。
7. 点击“从本章记忆更新人物”：Flash 只读取已保存的本章记忆及精简人物上下文，生成变化预览。勾选人物并确认后，已有基础性格、目标和自定义设定保留，变化按章写入人物成长记录，已确认的技能变化写入技能树。新人物可直接加入档案，无需手写 JSON。预览保存在本机，再次打开不重复计费；正文或记忆改变后需重新提取、核对。补录旧章不会回退较新章节记录的技能等级；重复确认不会重复追加同章成长记录。
8. 定期导出 JSON 备份。导入备份会创建新小说，不覆盖已有内容。

## 模型与成本

| 任务 | 模型 | 思考模式 | 单次输出上限 |
| --- | --- | --- | ---: |
| 第一章人物与技能提取 | `deepseek-flash` | 关闭 | 每段 2,600 token |
| 人物弧线推演 | `deepseek-v4-pro` | `low` | 4,200 token |
| 日常场景草稿 | `deepseek-flash` | 关闭 | 3,600 token |
| 重点场景草稿 | `deepseek-v4-pro` | 关闭 | 3,600 token |
| 章节记忆提取 | `deepseek-flash` | 关闭 | 每段及整章合并各 1,800 token |
| 从章节记忆提取人物变化 | `deepseek-flash` | 关闭 | 2,600 token，一次请求；重复打开预览为本地缓存 |

模型和思考模式依据 [DeepSeek 官方模型与价格页](https://api-docs.deepseek.com/quick_start/pricing/)及[思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode/)。截至 2026-10-19，峰时每百万输入/输出 token 价格：Flash $0.30/$1.20，Pro $1.32/$3.96。软件按峰时价估算，实际账单以 DeepSeek 为准。桌面同伴和侧栏通过[官方余额接口](https://api-docs.deepseek.com/api/get-user-balance/)显示余额，查询结果在本机缓存一分钟。

`.env` 默认 `DAILY_BUDGET_USD=1.00`、`MAX_CALL_USD=0.30`。预算只用于**发起前**判断；不会因为本地余额线达到阈值而截断生成。长章任务会先确定全部片段及合并请求的数量，再一次性预留整体估算上限；执行中不会因预算检查中途停止。完成后按返回的 token 用量更新估算。预算不是实际账单，尤其在网络中断且缺少用量回执时可能偏保守。每日预算按北京时间重置。

## 防止无效 token 消耗

- 场景草稿和人物弧线每次点击只发出一次模型请求。长章节的人物提取和记忆提取会按约 12,000 字符的固定片段执行，最多 16 段；记忆提取再合并一次。不会自动重试、无限循环或续写。
- 各任务有 `max_tokens`、约 120 秒总时限、30 秒网络空闲超时和约 26,000 字符的可见输出上限。
- 流式输出出现长段重复或连续空白时立即停止连接。已经产生的 token 仍可能计费，无法撤销。
- 正文每增加约 500 字符保存一次检查点；中断后可从“调用记录与成本”找回收到的文字。
- 章节目录只加载标题、字数和摘要；打开某一章时才读取它的完整正文。写作提示只选世界观、人物档案、相关章节记忆和最近一章结尾，不会每次上传整本书。本次章节 / 场景要求用于填写接下来一章要发生的事件，直接参与此次生成；填写内容可保存。章节记忆由 AI 从正文提取；作者可校正错漏，防止错误推测长期累积。

## 文件、迁移与 GitHub

小说正文以 Markdown 保存，元数据与调用记录以 JSON 保存；日常运行**不需要数据库**。

| 运行方式 | 默认作品目录 | Key 文件 |
| --- | --- | --- |
| 源码启动（Linux/Windows） | `data/library/` | 项目根目录 `.env` |
| Windows 打包版 | `%APPDATA%\CharacterCompass\library\` | `%APPDATA%\CharacterCompass\.env` |
| Linux 打包版 | `~/.local/share/CharacterCompass/library/` | `~/.local/share/CharacterCompass/.env` |

旧版 `data/novels.sqlite3` 首次运行时会自动迁移到 `data/library/`，旧数据库原样保留。旧“开篇正文”会并入第一章；若已有第一章，则接在旧开篇之后，旧 `opening.md` 原样保留。旧 JSON 备份导入时同样会合并。迁移中断可在下次启动继续。`data/`、`.env`、打包产物都被 `.gitignore` 排除，不会随普通 Git 提交上传。跨电脑迁移时可导出、导入 JSON 小说备份。

GitHub Actions 有 Linux/Windows 单元测试。Windows 安装包在推送到主分支、PR、手动运行或版本标签时构建，并验收打包窗口、高清桌宠、安装、快捷方式和卸载；Linux 提供手动或版本标签触发的桌面打包。每个平台须在对应系统构建。写作台使用 pywebview，桌宠使用独立的 Qt 透明窗口。Qt 对 Windows 透明顶层窗口要求无边框模式，代码已按 [Qt 官方说明](https://doc.qt.io/qt-6/qwidget.html)设置。Linux 有 X11/XWayland 时优先使用它，以支持准确定位、连续拖动和置顶；包内附带所需的 xcb-cursor 库及授权。纯 Wayland 使用 [Qt 的系统拖动接口](https://doc.qt.io/qt-6/qwindow.html#startSystemMove)，定位与置顶仍受合成器限制。窗口不使用随帧变化的可见 mask，X11 上的点击区域通过独立的 ShapeInput 设置。

## 开发检查

```bash
python -m unittest discover -s tests -v
python -m py_compile app.py desktop.py native_pet.py pet_animation.py pet_assets.py pet_platform.py storage.py deepseek_client.py novel_core.py
node --check web/app.js
```

主要文件：`app.py` 本地 API，`desktop.py` 跨平台启动与桌宠进程管理，`native_pet.py` 原生透明桌宠窗口，`pet_animation.py` 动作状态机，`pet_assets.py` 连续动作图集加载，`pet_platform.py` 桌宠平台与输入区域，`storage.py` Markdown/JSON 存储与旧库迁移，`novel_core.py` 模型任务和提示词，`deepseek_client.py` 流式输出保护，`web/` 写作页面与角色资源，`packaging/` 安装入口。旧章节检索使用关键词与最近摘要，尚未使用语义检索；人物分析结果仍需作者审核。
