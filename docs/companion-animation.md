# 桌面同伴动作素材

原始十张角色 PNG 保留为角色设计与生成参考。当前运行时使用待机、眨眼、思考、阅读四张基础姿势，以及五套连续动作图集，共 44 张可播放姿势。每套图集都是 4×2 的透明 PNG，包含八张中间姿势。图集由 OpenAI 内置 imagegen 根据本项目角色参考图生成，第一版完整提示词和参考图列表见 [companion-sequence-prompts.json](companion-sequence-prompts.json)，当前动漫式惊慌动作的提示词见 [companion-drag-anime-v3-prompt.json](companion-drag-anime-v3-prompt.json)。

| 动作 | 保存路径 | 连续姿势 | 播放时长 |
| --- | --- | ---: | ---: |
| 拖动 | [companion-drag-anime-v3.png](../web/assets/companion-drag-anime-v3.png) | 8 | 0.72 秒，9 个时间步，循环 |
| 点击挥手 | [companion-wave-sequence.png](../web/assets/companion-wave-sequence.png) | 8 | 1.12 秒 |
| 完成欢呼 | [companion-cheer-sequence.png](../web/assets/companion-cheer-sequence.png) | 8 | 1.16 秒 |
| 伸懒腰（自动间隔至少 5 分钟） | [companion-stretch-sequence.png](../web/assets/companion-stretch-sequence.png) | 8 | 1.60 秒，顶点略停顿 |
| 松手恢复 | [companion-recover-sequence.png](../web/assets/companion-recover-sequence.png) | 8 | 1.12 秒 |

惊慌动作恢复睁大的蓝眼和张嘴表情，双手从头顶经水平位置甩到身侧，配合悬空交错蹬腿和头胸反摆。手臂换向处增加水平经过帧。实际动漫片段的逐帧观察与动作拆解见 [参考记录](companion-motion-study.md)。

加载图集时，先限制在各自的格子内，再按透明度提取完整人物主体，移除邻帧混入的头发、衣角和散落像素；主体周围保留一像素的抗锯齿过渡。这个处理覆盖全部五套动作，每套图集共用一个裁切框与缩放比例。

默认使用原素材高清渲染：在原先的 128×192 分析画布上生成主体蒙版和公共裁切框，颜色、服装线条和眼睛细节从原图读取，不再先缩到 64×96。根据屏幕 DPI 生成对应的帧，2 倍 DPI 为 256×384 物理像素，角色仍占 128×192 逻辑尺寸，窗口继续为 190×300。所有图片只在载入或首次切换画质时处理，播放时直接绘制缓存。

右键同伴 →“显示画质”→“像素 · 恢复上一版效果”，可立即恢复此前 64×96 缩小再放大的渲染方式。切换不重置当前动作进度或移动窗口，选择通过 Qt 的本机设置保存。源码测试也可设置 `CHARACTER_COMPASS_PET_QUALITY=pixel` 临时指定像素模式。高清和像素模式共用原有动作顺序、拖动锚点、置顶与屏幕边界逻辑。画面只显示一个角色，不叠加两张姿势。

[打开可暂停、逐帧查看的动作预览](companion-motion-preview.html) · [查看全部帧](companion-motion-preview.png) · [白色对话卡片预览](native-pet-preview.png)

生成提示词的关键约束：

- 眨眼帧：保持人物、服装、发饰、书本、比例、姿势和透明背景不变，仅把双眼改为自然闭眼。
- 挥手帧：保持同一人物和构图，一手拿书，另一手在脸旁轻轻挥手；透明背景，无新增角色或文字。
- 思考帧：保持人物与构图，视线微微上扬，一根手指轻触下巴，另一手拿书；透明背景。
- 阅读帧：保持人物与构图，双手打开原来的书并低头阅读；透明背景。
- 惊慌 A：同一角色被轻轻拎起，睁大眼睛，两只手慌乱地向两侧扬起，双腿一前一后乱踢；保持服装、脸、发色与原画风格，透明背景，无文字。
- 惊慌 B：与惊慌 A 构成连续动作，双臂和双腿交换方向，表情仍然惊慌；保持人物身份、比例、衣饰和画面位置一致，透明背景，无文字。
- 落地发晕：角色刚落地，双膝微屈，双手保持平衡，眼睛眯起，略显晕乎；保持人物身份、服装、比例与画风，透明背景，无文字。
- 伸懒腰：角色困倦地打哈欠，双臂举起伸展；保持人物身份、衣饰、比例与画风，透明背景，无文字。
- 欢呼：角色开心地轻轻跳起，露出高兴的表情，双手庆祝；保持人物身份、衣饰、比例与画风，透明背景，无文字。

图集统一约束：同一角色、衣饰与身体比例；相邻帧采用衔接的姿势，惊慌动作允许头胸配合大幅摆臂作反摆；完整手脚位于独立网格内；透明背景，无文字、网格线、运动模糊或重复肢体。各动作依次经历抬起、经过中间位置、达到顶点、放回的过程。

动作状态分为持续状态（待机、思考、写作）和临时状态（挥手、伸懒腰、欢呼、拖动、落地）。拖动覆盖其它动作；松手后播放落地，再回到最新的工作状态。固定的 190×300 透明画布给角色、白色卡片和脚部留出空间。逐帧切换时清除透明画布，不改变窗口 mask，也不做交叉淡化。X11/XWayland 使用独立的 ShapeInput 控制点击区域，不裁切角色画面。拖动以按下时的窗口内坐标为锚点，切换姿势不会改变抓取偏移；松手后把整个窗口约束在目标屏幕可见区域内。点击角色时在同一窗口上方绘制白色对话卡片。

桌宠的原生窗口与状态机思路参考 [dsh-dafeiyu 的 Qt Helper](https://github.com/QCYTSN/dsh-dafeiyu/blob/main/runtime/helper.py) 和 [动画模型](https://github.com/QCYTSN/dsh-dafeiyu/blob/main/runtime/animation_model.py)。该项目的代码和不同代际的角色素材有不同授权，详见其 [素材授权说明](https://github.com/QCYTSN/dsh-dafeiyu/blob/main/ASSET_LICENSE.md)；本项目使用自己的角色素材。

交互检查：`QT_QPA_PLATFORM=offscreen python tests/smoke_pet.py` 使用真实 Qt 事件循环验证连续切帧、抓取偏移、每张动作的脚部像素和松手后的屏幕边缘。Linux 桌面可用 `PET_REAL_MOUSE=1 python tests/smoke_pet.py` 通过 XTest 实际移动鼠标验收，结束时恢复原鼠标位置。

动作预览可用 `python tools/preview_pet_sequences.py` 重新生成，附加 `--quality pixel` 可查看旧版像素效果；Linux 打包版可用 `python tests/check_packaged_pet.py dist/CharacterCompass/CharacterCompass` 检查真实鼠标拖动、连续画面变化和脚部可见性。

回归检查 `tests/test_pet_assets.py` 使用带红色邻帧碎片的透明图，验证碎片被移除、主体双脚与低透明度边缘得到保留。Qt 离屏检查同时验证所有输出动作帧的四周透明留白。

自动打哈欠／伸懒腰：启动后等待至少 5 分钟，之后每次至少间隔 5 分钟；工作、拖动或其它动作进行中延后到待机时播放。右键手动播放后也会重新计时。动作预览页的循环仅用于逐帧检视。
